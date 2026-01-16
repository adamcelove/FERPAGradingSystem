"""
Stage 4: Semantic Analysis

This stage performs semantic analysis on comments using Claude API,
including completeness and consistency checks.

CRITICAL: This stage MUST only receive anonymized text. The
FERPAEnforcedClient ensures the FERPA gate is checked before
every API call.

Key features:
- FERPA gate enforcement before all API calls
- Zero Data Retention (ZDR) headers for compliance
- Completeness analysis (specificity, actionability, etc.)
- Grade-comment consistency detection
- Stub implementations for POC (real API integration in Phase 2)
"""

from typing import Optional

import structlog

from ferpa_feedback.models import (
    CompletenessResult,
    ConfidenceLevel,
    ConsistencyResult,
    StudentComment,
    TeacherDocument,
)
from ferpa_feedback.stage_3_anonymize import AnonymizationGate

logger = structlog.get_logger()


class FERPAViolationError(Exception):
    """
    Raised when attempting to send PII to external API.

    This exception indicates a critical compliance failure where
    text that has not been properly anonymized would have been
    sent to an external API.
    """
    pass


class FERPAEnforcedClient:
    """
    Anthropic client that enforces FERPA gate before all calls.

    This wrapper ensures no PII can reach the Claude API by requiring
    an AnonymizationGate and validating text before every request.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        gate: Optional[AnonymizationGate] = None,
        enable_zdr: bool = True,
    ):
        """
        Initialize FERPA-enforced client.

        Args:
            api_key: Anthropic API key (or from env ANTHROPIC_API_KEY).
            gate: FERPA anonymization gate (required).
            enable_zdr: Include zero data retention headers.

        Raises:
            ValueError: If gate is not provided.
        """
        if gate is None:
            raise ValueError("FERPA gate is required for API client")

        self.gate = gate
        self.enable_zdr = enable_zdr
        self._api_key = api_key
        self._client = None  # Lazy load

        logger.info(
            "ferpa_client_initialized",
            enable_zdr=enable_zdr,
        )

    @property
    def client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
                logger.info("anthropic_client_loaded")
            except ImportError:
                logger.warning("anthropic_not_installed")
                # Will raise in analyze() if called
        return self._client

    def analyze(
        self,
        comment: StudentComment,
        prompt: str,
        max_tokens: int = 1000,
    ) -> dict:
        """
        Send anonymized text to API with FERPA enforcement.

        Args:
            comment: The comment to analyze (must be anonymized).
            prompt: The analysis prompt.
            max_tokens: Maximum tokens in response.

        Returns:
            API response as dictionary.

        Raises:
            FERPAViolationError: If comment fails FERPA gate.
            ImportError: If anthropic is not installed.
        """
        safe_text = self.gate.get_safe_text(comment)
        if safe_text is None:
            raise FERPAViolationError(
                f"Comment {comment.id} blocked by FERPA gate"
            )

        logger.info(
            "api_call_authorized",
            comment_id=comment.id,
        )

        # Build headers
        extra_headers = {}
        if self.enable_zdr:
            extra_headers["anthropic-beta"] = "zero-data-retention-2024-08-01"

        # Make API call (stub for POC - returns empty dict)
        # Real implementation would call Claude API here
        if self.client is None:
            logger.warning(
                "api_call_skipped",
                reason="anthropic_not_available",
                comment_id=comment.id,
            )
            return {}

        # Stub: Return empty response for POC
        # Phase 2 will implement real API calls
        return {}


class CompletenessAnalyzer:
    """
    Analyzes comment completeness using rubric and LLM.

    Evaluates comments against criteria:
    - Specificity: Does it mention specific behaviors/work?
    - Actionability: Does it provide actionable feedback?
    - Evidence: Is there evidence supporting the assessment?
    - Length: Is it appropriately detailed?
    - Tone: Is the tone professional and constructive?

    Stub implementation returns default scores for POC.
    """

    def __init__(
        self,
        client: Optional[FERPAEnforcedClient] = None,
        rubric_path: Optional[str] = None,
    ):
        """
        Initialize completeness analyzer.

        Args:
            client: FERPA-enforced API client (optional for stub).
            rubric_path: Path to completeness_rubric.yaml.
        """
        self.client = client
        self.rubric_path = rubric_path

        logger.info("completeness_analyzer_initialized")

    def analyze(self, comment: StudentComment) -> CompletenessResult:
        """
        Analyze completeness of a single comment.

        Stub implementation returns default values.
        Phase 2 will implement real analysis with Claude API.

        Args:
            comment: The comment to analyze.

        Returns:
            CompletenessResult with scores and assessment.
        """
        # Stub: Return default completeness result
        # Real implementation would use self.client to call Claude API

        logger.debug(
            "completeness_analysis_stub",
            comment_id=comment.id,
        )

        return CompletenessResult(
            is_complete=True,
            score=0.5,
            confidence=ConfidenceLevel.UNKNOWN,
            specificity_score=0.5,
            actionability_score=0.5,
            evidence_score=0.5,
            length_score=0.5,
            tone_score=0.5,
            missing_elements=[],
            explanation="Stub analysis - full implementation pending",
        )


class ConsistencyAnalyzer:
    """
    Analyzes grade-comment consistency.

    Detects misalignment between assigned grades and comment sentiment.
    For example, a low grade with only positive comments may indicate
    a copy-paste error or misassignment.

    Stub implementation returns default values for POC.
    """

    def __init__(self, client: Optional[FERPAEnforcedClient] = None):
        """
        Initialize consistency analyzer.

        Args:
            client: FERPA-enforced API client (optional for stub).
        """
        self.client = client

        logger.info("consistency_analyzer_initialized")

    def analyze(
        self,
        comment: StudentComment,
        grade: str,
    ) -> ConsistencyResult:
        """
        Check if comment sentiment aligns with grade.

        Stub implementation returns default values.
        Phase 2 will implement real analysis with Claude API.

        Args:
            comment: The student comment.
            grade: The assigned grade (e.g., "A+", "C-", "72%").

        Returns:
            ConsistencyResult with alignment assessment.
        """
        # Stub: Return default consistency result
        # Real implementation would use self.client to call Claude API

        logger.debug(
            "consistency_analysis_stub",
            comment_id=comment.id,
            grade=grade,
        )

        return ConsistencyResult(
            is_consistent=True,
            confidence=ConfidenceLevel.UNKNOWN,
            grade_sentiment="neutral",
            comment_sentiment="neutral",
            explanation="Stub analysis - full implementation pending",
            conflicting_phrases=[],
        )


class SemanticAnalysisProcessor:
    """
    Main processor for Stage 4 semantic analysis.

    Orchestrates completeness and consistency analysis for comments,
    ensuring FERPA gate is validated before any API calls.
    """

    def __init__(
        self,
        completeness_analyzer: CompletenessAnalyzer,
        consistency_analyzer: ConsistencyAnalyzer,
        ferpa_gate: AnonymizationGate,
    ):
        """
        Initialize semantic analysis processor.

        Args:
            completeness_analyzer: Analyzer for comment completeness.
            consistency_analyzer: Analyzer for grade-comment consistency.
            ferpa_gate: FERPA compliance gate.
        """
        self.completeness_analyzer = completeness_analyzer
        self.consistency_analyzer = consistency_analyzer
        self.ferpa_gate = ferpa_gate

        logger.info("semantic_processor_initialized")

    def process_comment(self, comment: StudentComment) -> StudentComment:
        """
        Run semantic analysis on a single comment.

        CRITICAL: This method verifies FERPA gate before any API calls.

        Args:
            comment: Comment to analyze (must be anonymized).

        Returns:
            Comment with completeness and consistency results.
        """
        # Double-check FERPA gate before any analysis
        if not self.ferpa_gate.validate_for_api(comment):
            logger.error(
                "ferpa_gate_blocked_stage4",
                comment_id=comment.id,
            )
            return comment  # Return unmodified

        # Run completeness analysis
        completeness = self.completeness_analyzer.analyze(comment)

        # Run consistency analysis
        consistency = self.consistency_analyzer.analyze(comment, comment.grade)

        logger.debug(
            "semantic_analysis_complete",
            comment_id=comment.id,
            is_complete=completeness.is_complete,
            is_consistent=consistency.is_consistent,
        )

        # Return new comment with analysis results
        return StudentComment(
            **{
                **comment.model_dump(exclude={"completeness", "consistency"}),
                "completeness": completeness,
                "consistency": consistency,
            }
        )

    def process_document(self, document: TeacherDocument) -> TeacherDocument:
        """
        Process all comments in document through semantic analysis.

        Args:
            document: Document with anonymized comments.

        Returns:
            Document with semantic analysis results.
        """
        logger.info(
            "semantic_analysis_document",
            doc_id=document.id,
            comment_count=len(document.comments),
        )

        processed_comments = []
        analyzed_count = 0
        blocked_count = 0

        for comment in document.comments:
            processed = self.process_comment(comment)
            processed_comments.append(processed)

            # Track statistics
            if processed.completeness is not None:
                analyzed_count += 1
            else:
                blocked_count += 1

        logger.info(
            "semantic_analysis_document_complete",
            doc_id=document.id,
            analyzed=analyzed_count,
            blocked=blocked_count,
        )

        return TeacherDocument(
            **{
                **document.model_dump(exclude={"comments"}),
                "comments": processed_comments,
            }
        )


def create_semantic_processor(
    config: Optional[dict] = None,
    ferpa_gate: Optional[AnonymizationGate] = None,
) -> SemanticAnalysisProcessor:
    """
    Factory function for Stage 4 semantic analysis processor.

    Args:
        config: Configuration dictionary with API settings.
        ferpa_gate: FERPA compliance gate (required).

    Returns:
        Configured SemanticAnalysisProcessor.

    Raises:
        ValueError: If ferpa_gate is not provided.
    """
    if ferpa_gate is None:
        raise ValueError("FERPA gate is required for semantic processor")

    config = config or {}

    # Create FERPA-enforced client
    api_key = config.get("api_key")
    enable_zdr = config.get("enable_zdr", True)

    client = FERPAEnforcedClient(
        api_key=api_key,
        gate=ferpa_gate,
        enable_zdr=enable_zdr,
    )

    # Create analyzers
    completeness_analyzer = CompletenessAnalyzer(
        client=client,
        rubric_path=config.get("rubric_path"),
    )

    consistency_analyzer = ConsistencyAnalyzer(client=client)

    # Create processor
    return SemanticAnalysisProcessor(
        completeness_analyzer=completeness_analyzer,
        consistency_analyzer=consistency_analyzer,
        ferpa_gate=ferpa_gate,
    )
