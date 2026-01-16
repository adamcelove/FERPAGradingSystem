"""
Pipeline Orchestrator

Coordinates all processing stages for the FERPA-compliant feedback system.

Processing flow:
1. Document Ingestion (Stage 0) - Local
2. Grammar/Spelling Check (Stage 1) - Local
3. Name Verification (Stage 2) - Local
4. Anonymization (Stage 3) - Local [FERPA GATE]
5. Semantic Analysis (Stage 4) - External API (anonymized only)
6. Review Queue (Stage 5) - Local

Stages 0-3 are 100% local and handle raw PII.
Stage 4 ONLY receives anonymized text.
Stage 5 de-anonymizes results for human review.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import structlog
import yaml  # type: ignore[import-untyped]

from ferpa_feedback.models import (
    ClassRoster,
    ProcessingResult,
    RosterEntry,
    StudentComment,
    TeacherDocument,
)
from ferpa_feedback.stage_0_ingestion import DocumentParser, RosterLoader
from ferpa_feedback.stage_1_grammar import GrammarChecker, create_grammar_checker
from ferpa_feedback.stage_2_names import NameVerificationProcessor, create_name_processor
from ferpa_feedback.stage_3_anonymize import (
    AnonymizationGate,
    create_anonymization_processor,
)

logger = structlog.get_logger()


class PipelineConfig:
    """Configuration container for the pipeline."""

    def __init__(self, config_path: Path | None = None):
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to settings.yaml
        """
        self.config: dict[str, Any] = {}

        if config_path and config_path.exists():
            with open(config_path) as f:
                self.config = yaml.safe_load(f) or {}
            logger.info("config_loaded", path=str(config_path))
        else:
            logger.warning("using_default_config")

    @property
    def stages_enabled(self) -> dict[str, bool]:
        """Get enabled stages."""
        pipeline_config = self.config.get("pipeline", {})
        if isinstance(pipeline_config, dict):
            stages = pipeline_config.get("stages", {
                "grammar": True,
                "name_matching": True,
                "completeness": True,
                "grade_consistency": True,
            })
            return cast(dict[str, bool], stages)
        return {
            "grammar": True,
            "name_matching": True,
            "completeness": True,
            "grade_consistency": True,
        }

    @property
    def grammar_config(self) -> dict[str, Any]:
        """Get grammar checker configuration."""
        result = self.config.get("grammar", {})
        return cast(dict[str, Any], result)

    @property
    def name_detection_config(self) -> dict[str, Any]:
        """Get name detection configuration."""
        result = self.config.get("name_detection", {})
        return cast(dict[str, Any], result)

    @property
    def anonymization_config(self) -> dict[str, Any]:
        """Get anonymization configuration."""
        result = self.config.get("anonymization", {})
        return cast(dict[str, Any], result)

    @property
    def ferpa_config(self) -> dict[str, Any]:
        """Get FERPA compliance configuration."""
        result = self.config.get("ferpa", {
            "anonymize_before_api": True,
            "log_all_api_calls": True,
        })
        return cast(dict[str, Any], result)


class FeedbackPipeline:
    """
    Main pipeline orchestrator for FERPA-compliant comment processing.

    Ensures all PII handling follows compliance requirements:
    - Raw PII only processed locally
    - External API calls only receive anonymized text
    - Full audit logging of all operations
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        roster: ClassRoster | None = None,
    ):
        """
        Initialize the pipeline.

        Args:
            config: Pipeline configuration
            roster: Class roster for name matching/anonymization
        """
        self.config = config or PipelineConfig()
        self.roster = roster

        # Initialize local processing stages
        self._init_local_stages()

        # Initialize FERPA gate
        self._init_ferpa_gate()

        logger.info(
            "pipeline_initialized",
            stages_enabled=self.config.stages_enabled,
        )

    def _init_local_stages(self) -> None:
        """Initialize stages that process raw PII locally."""
        # Stage 0: Document parsing
        self.document_parser = DocumentParser()

        # Stage 1: Grammar checking
        self.grammar_checker: GrammarChecker | None = None
        if self.config.stages_enabled.get("grammar", True):
            self.grammar_checker = create_grammar_checker(self.config.grammar_config)

        # Stage 2: Name verification
        self.name_processor: NameVerificationProcessor | None = None
        if self.config.stages_enabled.get("name_matching", True):
            self.name_processor = create_name_processor(
                roster=self.roster,
                config=self.config.name_detection_config,
            )

        # Stage 3: Anonymization
        self.anonymization_processor = create_anonymization_processor(
            roster=self.roster,
            config=self.config.anonymization_config,
        )

    def _init_ferpa_gate(self) -> None:
        """Initialize the FERPA compliance gate."""
        self.ferpa_gate = AnonymizationGate(self.anonymization_processor)

        # Verify FERPA settings
        if not self.config.ferpa_config.get("anonymize_before_api", True):
            logger.critical(
                "FERPA_VIOLATION_RISK",
                message="anonymize_before_api is disabled - this may violate FERPA",
            )
            raise ValueError(
                "CRITICAL: anonymize_before_api must be True for FERPA compliance"
            )

    def set_roster(self, roster: ClassRoster) -> None:
        """
        Update the class roster.

        Args:
            roster: New class roster
        """
        self.roster = roster

        # Update processors that use roster
        if self.name_processor:
            self.name_processor.extractor.set_roster(roster)

        self.anonymization_processor.detector.set_roster(roster)

        logger.info("roster_updated", student_count=len(roster.students))

    def load_roster_from_csv(self, csv_path: Path, class_name: str = "") -> None:
        """
        Load roster from CSV file.

        Args:
            csv_path: Path to CSV file
            class_name: Name of the class
        """
        roster_data = RosterLoader.from_csv(csv_path)

        students = [
            RosterEntry(
                student_id=r["student_id"],
                first_name=r["first_name"],
                last_name=r["last_name"],
                preferred_name=r.get("preferred_name"),
            )
            for r in roster_data
        ]

        roster = ClassRoster(
            class_id=str(uuid.uuid4()),
            class_name=class_name,
            teacher_name="",
            term="",
            students=students,
        )

        self.set_roster(roster)

    def process_document(
        self,
        file_path: Path,
        document_id: str | None = None,
    ) -> TeacherDocument:
        """
        Process a single document through all local stages.

        Args:
            file_path: Path to document file
            document_id: Optional document ID

        Returns:
            Processed document with all local analysis complete
        """
        start_time = datetime.now()
        document_id = document_id or str(uuid.uuid4())

        logger.info("processing_document", path=str(file_path), doc_id=document_id)

        # Stage 0: Parse document
        document = self.document_parser.parse_docx(file_path, document_id)
        logger.info("stage_0_complete", comments=len(document.comments))

        # Stage 1: Grammar check
        if self.grammar_checker:
            document = self.grammar_checker.check_document(document)
            logger.info(
                "stage_1_complete",
                grammar_issues=document.grammar_issues_count,
            )

        # Stage 2: Name verification
        if self.name_processor:
            document = self.name_processor.process_document(document)
            logger.info(
                "stage_2_complete",
                name_mismatches=document.name_mismatches_count,
            )

        # Stage 3: Anonymization
        document = self.anonymization_processor.process_document(document)

        # Verify anonymization
        verification = self.anonymization_processor.verify_anonymization(document)
        if not verification["is_clean"]:
            logger.error(
                "anonymization_verification_failed",
                issues=verification["issues"],
            )
            # In production, you might want to halt here

        logger.info("stage_3_complete", verified=verification["is_clean"])

        # Update document metadata
        processing_time = (datetime.now() - start_time).total_seconds()
        document = TeacherDocument(
            **{
                **document.model_dump(exclude={"processed_at", "processing_duration_seconds"}),
                "processed_at": datetime.now(),
                "processing_duration_seconds": processing_time,
            }
        )

        logger.info(
            "local_processing_complete",
            doc_id=document_id,
            duration_seconds=processing_time,
            needs_review=document.needs_review_count,
        )

        return document

    def get_api_ready_comments(
        self,
        document: TeacherDocument,
    ) -> list[tuple[StudentComment, str]]:
        """
        Get comments that are safe to send to external API.

        Uses the FERPA gate to verify each comment is properly anonymized.

        Args:
            document: Processed document

        Returns:
            List of (comment, anonymized_text) tuples that passed the gate
        """
        api_ready: list[tuple[StudentComment, str]] = []
        blocked = 0

        for comment in document.comments:
            safe_text = self.ferpa_gate.get_safe_text(comment)
            if safe_text:
                api_ready.append((comment, safe_text))
            else:
                blocked += 1
                logger.warning(
                    "comment_blocked_by_ferpa_gate",
                    comment_id=comment.id,
                )

        logger.info(
            "api_ready_comments",
            ready=len(api_ready),
            blocked=blocked,
        )

        return api_ready

    def process_batch(
        self,
        file_paths: list[Path],
        roster_path: Path | None = None,
    ) -> ProcessingResult:
        """
        Process a batch of documents.

        Args:
            file_paths: List of document paths
            roster_path: Optional path to roster CSV

        Returns:
            ProcessingResult with all documents
        """
        batch_id = str(uuid.uuid4())
        start_time = datetime.now()

        logger.info(
            "batch_processing_started",
            batch_id=batch_id,
            document_count=len(file_paths),
        )

        # Load roster if provided
        if roster_path:
            self.load_roster_from_csv(roster_path)

        documents: list[TeacherDocument] = []
        for path in file_paths:
            try:
                doc = self.process_document(path)
                documents.append(doc)
            except Exception as e:
                logger.error(
                    "document_processing_failed",
                    path=str(path),
                    error=str(e),
                )
                # Continue with other documents

        result = ProcessingResult(
            batch_id=batch_id,
            started_at=start_time,
            completed_at=datetime.now(),
            documents=documents,
        )

        logger.info(
            "batch_processing_complete",
            batch_id=batch_id,
            total_documents=result.total_documents,
            total_comments=result.total_comments,
            total_grammar_issues=result.total_grammar_issues,
            total_name_mismatches=result.total_name_mismatches,
            total_needing_review=result.total_needing_review,
        )

        return result


# Convenience function for CLI usage
def create_pipeline(
    config_path: str | None = None,
    roster_path: str | None = None,
) -> FeedbackPipeline:
    """
    Create a configured pipeline.

    Args:
        config_path: Path to settings.yaml
        roster_path: Path to roster CSV

    Returns:
        Configured FeedbackPipeline
    """
    config = PipelineConfig(Path(config_path) if config_path else None)
    pipeline = FeedbackPipeline(config=config)

    if roster_path:
        pipeline.load_roster_from_csv(Path(roster_path))

    return pipeline
