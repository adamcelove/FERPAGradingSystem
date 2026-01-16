"""
Stage 3: PII Anonymization

This is the CRITICAL FERPA COMPLIANCE GATE.

Before any text is sent to an external API (Stage 4), it MUST pass
through this anonymization layer. All personally identifiable
information is replaced with placeholders.

Key features:
- Bidirectional mapping (can restore original after API processing)
- Roster-aware detection (catches all known student names)
- NER fallback (catches unknown names like parents, siblings)
- Email, phone, SSN detection
- Consistent placeholder assignment within documents

This stage is 100% local - no external API calls.
"""

from __future__ import annotations

import re
from re import Pattern
from typing import Any

import structlog

from ferpa_feedback.models import (
    AnonymizationMapping,
    ClassRoster,
    StudentComment,
    TeacherDocument,
)

logger = structlog.get_logger()


def create_enhanced_analyzer(
    roster: ClassRoster | None = None,
    school_patterns: list[str] | None = None,
    score_threshold: float = 0.3,  # Low threshold for high recall
) -> Any | None:
    """
    Create an enhanced Presidio analyzer with custom educational recognizers.

    This factory function creates an AnalyzerEngine configured with:
    - Standard Presidio recognizers (PERSON, EMAIL_ADDRESS, etc.)
    - Custom educational recognizers (StudentID, GradeLevel, SchoolName)
    - Low score threshold for high recall (prefer false positives over misses)

    Args:
        roster: Optional class roster (reserved for future roster-aware recognizers)
        school_patterns: Optional list of regex patterns for school names
        score_threshold: Minimum confidence score for detections (default 0.3)

    Returns:
        Configured AnalyzerEngine with custom recognizers registered,
        or None if presidio is not available
    """
    try:
        from presidio_analyzer import AnalyzerEngine
    except ImportError:
        logger.warning("presidio_analyzer not installed, enhanced analyzer unavailable")
        return None

    from ferpa_feedback.recognizers.educational import (
        PRESIDIO_AVAILABLE,
        GradeLevelRecognizer,
        SchoolNameRecognizer,
        StudentIDRecognizer,
    )

    # Only register recognizers if presidio is truly available
    if not PRESIDIO_AVAILABLE:
        logger.warning("presidio recognizers not available, using basic analyzer")
        return AnalyzerEngine()

    # Create analyzer engine
    analyzer = AnalyzerEngine()

    # Register custom educational recognizers
    analyzer.registry.add_recognizer(StudentIDRecognizer())
    analyzer.registry.add_recognizer(GradeLevelRecognizer())

    # Add school name recognizer with custom patterns if provided
    if school_patterns:
        analyzer.registry.add_recognizer(SchoolNameRecognizer(school_patterns))
    else:
        analyzer.registry.add_recognizer(SchoolNameRecognizer())

    logger.info(
        "enhanced_analyzer_created",
        score_threshold=score_threshold,
        has_school_patterns=school_patterns is not None,
    )

    return analyzer


class PIIDetector:
    """
    Detects personally identifiable information in text.

    Combines:
    1. Roster-based detection (known students)
    2. Presidio NER (unknown names, emails, phones, etc.)
    3. Regex patterns (structured PII like SSN, student IDs)
    """

    # Regex patterns for structured PII
    PATTERNS = {
        "EMAIL": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        "PHONE": re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
        "SSN": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        # Matches "Student ID: 12345678" or "student-id: 123456789"
        "STUDENT_ID": re.compile(r'\b[Ss]tudent[\s_-]?[Ii][Dd][:\s]*\d{6,9}\b'),
        # Matches bare student ID with S prefix like "S12345678"
        "STUDENT_ID_BARE": re.compile(r'\b[Ss]\d{7,9}\b'),
        "DATE": re.compile(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b'),
    }

    def __init__(
        self,
        roster: ClassRoster | None = None,
        use_presidio: bool = True,
        use_custom_recognizers: bool = True,
        school_patterns: list[str] | None = None,
        score_threshold: float = 0.3,  # Low threshold for high recall
    ):
        """
        Initialize PII detector.

        Args:
            roster: Class roster for known-name detection
            use_presidio: Whether to use Presidio for NER
            use_custom_recognizers: Whether to use custom educational recognizers
            school_patterns: Optional list of regex patterns for school names
            score_threshold: Minimum confidence score for Presidio detections
        """
        self.roster = roster
        self.use_presidio = use_presidio
        self.use_custom_recognizers = use_custom_recognizers
        self.school_patterns = school_patterns
        self.score_threshold = score_threshold
        self._presidio_analyzer = None
        self._roster_patterns: list[tuple[Pattern[str], str]] = []

        if roster:
            self._build_roster_patterns()

        logger.info(
            "pii_detector_initialized",
            use_presidio=use_presidio,
            use_custom_recognizers=use_custom_recognizers,
            score_threshold=score_threshold,
        )

    @property
    def presidio_analyzer(self) -> Any | None:
        """Lazy-load Presidio analyzer with optional custom recognizers."""
        if self._presidio_analyzer is None and self.use_presidio:
            if self.use_custom_recognizers:
                # Use enhanced analyzer with custom educational recognizers
                enhanced = create_enhanced_analyzer(
                    roster=self.roster,
                    school_patterns=self.school_patterns,
                    score_threshold=self.score_threshold,
                )
                if enhanced is not None:
                    self._presidio_analyzer = enhanced
                    logger.info("enhanced_presidio_analyzer_loaded")
                else:
                    # Presidio not available, disable
                    self.use_presidio = False
                    logger.info("presidio_unavailable_disabled")
            else:
                # Use default analyzer without custom recognizers
                try:
                    from presidio_analyzer import AnalyzerEngine
                    self._presidio_analyzer = AnalyzerEngine()
                    logger.info("presidio_analyzer_loaded")
                except ImportError:
                    self.use_presidio = False
                    logger.info("presidio_unavailable_disabled")
        return self._presidio_analyzer

    def _build_roster_patterns(self) -> None:
        """Build regex patterns for all roster names."""
        self._roster_patterns = []

        if not self.roster:
            return

        for student in self.roster.students:
            for variant in student.all_name_variants:
                # Create word-boundary pattern
                pattern = re.compile(
                    r'\b' + re.escape(variant) + r'\b',
                    re.IGNORECASE,
                )
                self._roster_patterns.append((pattern, student.full_name))

        logger.debug("roster_patterns_built", count=len(self._roster_patterns))

    def set_roster(self, roster: ClassRoster) -> None:
        """Update roster and rebuild patterns."""
        self.roster = roster
        self._build_roster_patterns()

    def detect(self, text: str) -> list[dict[str, Any]]:
        """
        Detect all PII in text.

        Args:
            text: Text to analyze

        Returns:
            List of detected PII with positions and types
        """
        detections = []

        # 1. Roster-based detection (highest priority)
        for pattern, canonical_name in self._roster_patterns:
            for match in pattern.finditer(text):
                detections.append({
                    "text": match.group(),
                    "canonical": canonical_name,
                    "start": match.start(),
                    "end": match.end(),
                    "type": "STUDENT_NAME",
                    "source": "roster",
                    "confidence": 0.99,
                })

        # 2. Regex patterns for structured PII
        for entity_type, pattern in self.PATTERNS.items():
            for match in pattern.finditer(text):
                detections.append({
                    "text": match.group(),
                    "canonical": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                    "type": entity_type,
                    "source": "regex",
                    "confidence": 0.95,
                })

        # 3. Presidio NER for unknown names and custom educational entities
        if self.use_presidio and self.presidio_analyzer:
            # Include custom educational entity types when custom recognizers enabled
            entities = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "DATE_TIME"]
            if self.use_custom_recognizers:
                entities.extend(["STUDENT_ID", "GRADE_LEVEL", "SCHOOL_NAME"])

            presidio_results = self.presidio_analyzer.analyze(
                text,
                entities=entities,
                language="en",
                score_threshold=self.score_threshold,
            )

            for result in presidio_results:
                # Skip if already detected by roster or regex
                already_detected = any(
                    d["start"] <= result.start < d["end"] or
                    d["start"] < result.end <= d["end"]
                    for d in detections
                )

                if not already_detected:
                    detected_text = text[result.start:result.end]
                    detections.append({
                        "text": detected_text,
                        "canonical": detected_text,
                        "start": result.start,
                        "end": result.end,
                        "type": result.entity_type,
                        "source": "presidio",
                        "confidence": result.score,
                    })

        # Sort by position (for consistent replacement order)
        def get_start(x: dict[str, Any]) -> int:
            start_val = x.get("start", 0)
            return int(start_val) if start_val is not None else 0
        detections.sort(key=get_start)

        return detections


class Anonymizer:
    """
    Replaces PII with consistent placeholders.

    Maintains bidirectional mapping for de-anonymization after
    external API processing.
    """

    def __init__(self, placeholder_format: str = "[{entity_type}_{index}]"):
        """
        Initialize anonymizer.

        Args:
            placeholder_format: Format string for placeholders
        """
        self.placeholder_format = placeholder_format
        self._entity_counters: dict[str, int] = {}
        self._mappings: dict[str, str] = {}  # canonical -> placeholder
        self._reverse_mappings: dict[str, str] = {}  # placeholder -> canonical

    def reset(self) -> None:
        """Reset all mappings (call between documents)."""
        self._entity_counters = {}
        self._mappings = {}
        self._reverse_mappings = {}

    def _get_placeholder(self, entity_type: str, canonical_text: str) -> str:
        """Get or create placeholder for an entity."""
        # Check if we already have a mapping for this canonical text
        key = f"{entity_type}:{canonical_text.lower()}"

        if key in self._mappings:
            return self._mappings[key]

        # Create new placeholder
        if entity_type not in self._entity_counters:
            self._entity_counters[entity_type] = 0

        self._entity_counters[entity_type] += 1
        placeholder = self.placeholder_format.format(
            entity_type=entity_type,
            index=self._entity_counters[entity_type],
        )

        self._mappings[key] = placeholder
        self._reverse_mappings[placeholder] = canonical_text

        return placeholder

    def anonymize(
        self,
        text: str,
        detections: list[dict[str, Any]],
    ) -> tuple[str, list[AnonymizationMapping]]:
        """
        Anonymize text by replacing detected PII.

        Args:
            text: Original text
            detections: List of PII detections

        Returns:
            Tuple of (anonymized_text, mappings)
        """
        if not detections:
            return text, []

        mappings = []
        result = text
        offset = 0  # Track position shifts due to replacements

        for detection in detections:
            placeholder = self._get_placeholder(
                detection["type"],
                detection["canonical"],
            )

            # Calculate adjusted positions
            start = detection["start"] + offset
            end = detection["end"] + offset

            # Create mapping record
            mapping = AnonymizationMapping(
                original=detection["text"],
                placeholder=placeholder,
                entity_type=detection["type"],
                start_pos=detection["start"],
                end_pos=detection["end"],
            )
            mappings.append(mapping)

            # Perform replacement
            result = result[:start] + placeholder + result[end:]

            # Update offset
            offset += len(placeholder) - (end - start)

        return result, mappings

    def deanonymize(self, text: str) -> str:
        """
        Restore original PII from placeholders.

        Args:
            text: Anonymized text

        Returns:
            De-anonymized text
        """
        result = text

        # Replace in reverse order of placeholder length to avoid partial replacements
        for placeholder, original in sorted(
            self._reverse_mappings.items(),
            key=lambda x: -len(x[0]),
        ):
            result = result.replace(placeholder, original)

        return result

    def get_all_mappings(self) -> dict[str, str]:
        """Get all placeholder -> original mappings."""
        return dict(self._reverse_mappings)


class AnonymizationProcessor:
    """
    Processes documents through the anonymization pipeline.
    """

    def __init__(
        self,
        detector: PIIDetector,
        anonymizer: Anonymizer,
    ):
        """
        Initialize processor.

        Args:
            detector: PII detection engine
            anonymizer: Anonymization engine
        """
        self.detector = detector
        self.anonymizer = anonymizer

    def process_comment(self, comment: StudentComment) -> StudentComment:
        """
        Anonymize a single comment.

        Args:
            comment: Comment to anonymize

        Returns:
            Comment with anonymized_text and mappings populated
        """
        # Detect PII
        detections = self.detector.detect(comment.comment_text)

        # Anonymize
        anonymized_text, mappings = self.anonymizer.anonymize(
            comment.comment_text,
            detections,
        )

        logger.debug(
            "comment_anonymized",
            comment_id=comment.id,
            pii_count=len(detections),
            entities=[d["type"] for d in detections],
        )

        return StudentComment(
            **{
                **comment.model_dump(exclude={"anonymized_text", "anonymization_mappings"}),
                "anonymized_text": anonymized_text,
                "anonymization_mappings": mappings,
            }
        )

    def process_document(self, document: TeacherDocument) -> TeacherDocument:
        """
        Anonymize all comments in a document.

        Args:
            document: Document to process

        Returns:
            Document with all comments anonymized
        """
        logger.info(
            "anonymizing_document",
            doc_id=document.id,
            comment_count=len(document.comments),
        )

        # Reset anonymizer for new document (consistent placeholders within doc)
        self.anonymizer.reset()

        processed_comments = []
        total_pii = 0

        for comment in document.comments:
            processed = self.process_comment(comment)
            processed_comments.append(processed)
            total_pii += len(processed.anonymization_mappings)

        logger.info(
            "document_anonymized",
            doc_id=document.id,
            total_pii_replaced=total_pii,
        )

        return TeacherDocument(
            **{
                **document.model_dump(exclude={"comments"}),
                "comments": processed_comments,
            }
        )

    def verify_anonymization(self, document: TeacherDocument) -> dict[str, Any]:
        """
        Verify that a document is properly anonymized.

        Returns a report of any potential PII that may have been missed.

        Args:
            document: Anonymized document to verify

        Returns:
            Verification report
        """
        issues = []

        for comment in document.comments:
            if not comment.anonymized_text:
                issues.append({
                    "comment_id": comment.id,
                    "issue": "Missing anonymized text",
                })
                continue

            # Re-scan anonymized text for any remaining PII
            remaining = self.detector.detect(comment.anonymized_text)

            # Filter out placeholders (they look like [ENTITY_N])
            real_pii = [
                d for d in remaining
                if not re.match(r'\[[A-Z_]+_\d+\]', d["text"])
            ]

            if real_pii:
                issues.append({
                    "comment_id": comment.id,
                    "issue": "Potential PII in anonymized text",
                    "detected": str(real_pii),
                })

        return {
            "document_id": document.id,
            "is_clean": len(issues) == 0,
            "issues": issues,
        }


class AnonymizationGate:
    """
    Enforces anonymization before any external API access.

    This is the FERPA compliance gate. No text should reach
    external APIs without passing through this gate.
    """

    def __init__(self, processor: AnonymizationProcessor):
        """
        Initialize gate.

        Args:
            processor: Anonymization processor
        """
        self.processor = processor

    def validate_for_api(self, comment: StudentComment) -> bool:
        """
        Check if a comment is safe to send to external API.

        Args:
            comment: Comment to validate

        Returns:
            True if safe, False if PII detected
        """
        if not comment.anonymized_text:
            logger.error(
                "api_gate_blocked",
                reason="No anonymized text",
                comment_id=comment.id,
            )
            return False

        # Verify no PII in anonymized text
        remaining = self.processor.detector.detect(comment.anonymized_text)

        # Filter out placeholders
        real_pii = [
            d for d in remaining
            if not re.match(r'\[[A-Z_]+_\d+\]', d["text"])
        ]

        if real_pii:
            logger.error(
                "api_gate_blocked",
                reason="PII detected in anonymized text",
                comment_id=comment.id,
                pii_types=[p["type"] for p in real_pii],
            )
            return False

        return True

    def get_safe_text(self, comment: StudentComment) -> str | None:
        """
        Get text that is safe to send to external API.

        Args:
            comment: Comment to get safe text from

        Returns:
            Anonymized text if safe, None if not
        """
        if self.validate_for_api(comment):
            return comment.anonymized_text
        return None


# Factory function
def create_anonymization_processor(
    roster: ClassRoster | None = None,
    config: dict[str, Any] | None = None,
) -> AnonymizationProcessor:
    """
    Create configured anonymization processor.

    Args:
        roster: Class roster for name detection
        config: Configuration dictionary

    Returns:
        Configured processor
    """
    config = config or {}

    detector = PIIDetector(
        roster=roster,
        use_presidio=config.get("presidio", {}).get("enabled", True),
    )

    anonymizer = Anonymizer(
        placeholder_format=config.get("placeholder_format", "[{entity_type}_{index}]"),
    )

    return AnonymizationProcessor(detector, anonymizer)
