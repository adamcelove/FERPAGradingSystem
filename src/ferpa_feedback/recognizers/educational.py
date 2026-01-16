"""Custom Presidio recognizers for educational PII detection.

This module implements custom PatternRecognizer subclasses for detecting
educational-context PII such as student IDs, grade levels, and school names.

These recognizers extend Presidio's capabilities to better handle FERPA-protected
data in student feedback systems.
"""

from typing import Any, List, Optional, TYPE_CHECKING

PRESIDIO_AVAILABLE = False
_PatternRecognizerBase: Any = None

try:
    from presidio_analyzer import Pattern, PatternRecognizer
    PRESIDIO_AVAILABLE = True
    _PatternRecognizerBase = PatternRecognizer
except ImportError:
    pass

if not PRESIDIO_AVAILABLE:
    # Provide stub classes when presidio is not installed
    class Pattern:  # type: ignore[no-redef]
        """Stub Pattern class when presidio is not installed."""
        def __init__(
            self,
            name: str,
            regex: str,
            score: float
        ) -> None:
            self.name = name
            self.regex = regex
            self.score = score

    class _StubPatternRecognizer:
        """Stub PatternRecognizer class when presidio is not installed."""
        def __init__(
            self,
            supported_entity: str,
            patterns: Optional[List[Any]] = None,
            context: Optional[List[str]] = None,
            **kwargs: object
        ) -> None:
            self.supported_entity = supported_entity
            self.patterns = patterns or []
            self.context = context or []

    _PatternRecognizerBase = _StubPatternRecognizer


class StudentIDRecognizer(_PatternRecognizerBase):  # type: ignore[misc]
    """Recognizer for detecting student ID patterns.

    Detects patterns like:
    - "Student ID: 123456789"
    - "student-id: 12345678"
    - "S12345678" (bare student ID with S prefix)

    The recognizer uses context words to boost confidence when
    terms like "student", "id", or "number" appear nearby.
    """

    PATTERNS = [
        Pattern(
            name="student_id_prefix",
            regex=r"\b[Ss]tudent[\s_-]?[Ii][Dd][:\s]*(\d{6,9})\b",
            score=0.9
        ),
        Pattern(
            name="student_id_bare",
            regex=r"\b[Ss]\d{7,9}\b",
            score=0.7
        ),
    ]

    def __init__(self) -> None:
        """Initialize the StudentIDRecognizer with predefined patterns."""
        super().__init__(
            supported_entity="STUDENT_ID",
            patterns=self.PATTERNS,
            context=["student", "id", "number"]
        )


class GradeLevelRecognizer(_PatternRecognizerBase):  # type: ignore[misc]
    """Recognizer for detecting grade level mentions.

    Detects patterns like:
    - "5th grade", "10th grader"
    - "freshman", "sophomore", "junior", "senior"

    Uses lower confidence scores since grade levels may be
    intentional and not always considered PII.
    """

    PATTERNS = [
        Pattern(
            name="grade_level",
            regex=r"\b(1[0-2]|[1-9])(?:st|nd|rd|th)?\s*[Gg]rad(?:e|er)\b",
            score=0.6
        ),
        Pattern(
            name="freshman_etc",
            regex=r"\b(?:[Ff]reshman|[Ss]ophomore|[Jj]unior|[Ss]enior)\b",
            score=0.5
        ),
    ]

    def __init__(self) -> None:
        """Initialize the GradeLevelRecognizer with predefined patterns."""
        super().__init__(
            supported_entity="GRADE_LEVEL",
            patterns=self.PATTERNS,
            context=["grade", "year", "class"]
        )


class SchoolNameRecognizer(_PatternRecognizerBase):  # type: ignore[misc]
    """Recognizer for detecting school names.

    This recognizer is configurable with custom school name patterns
    specific to the organization using the system. Schools should provide
    their own patterns matching their school names and common variations.

    Example patterns:
    - r"\\bLincoln\\s+(?:High|Elementary|Middle)\\s+School\\b"
    - r"\\bWashington\\s+Academy\\b"
    """

    def __init__(self, school_patterns: Optional[List[str]] = None) -> None:
        """Initialize the SchoolNameRecognizer with configurable patterns.

        Args:
            school_patterns: List of regex patterns to match school names.
                            If None, uses a default pattern for common formats.
        """
        if school_patterns is None:
            # Default patterns for common school name formats
            school_patterns = [
                r"\b\w+\s+(?:High|Elementary|Middle|Primary|Secondary)\s+School\b",
                r"\b\w+\s+(?:Academy|Institute|Preparatory)\b",
            ]

        patterns = [
            Pattern(
                name=f"school_{i}",
                regex=p,
                score=0.8
            )
            for i, p in enumerate(school_patterns)
        ]

        super().__init__(
            supported_entity="SCHOOL_NAME",
            patterns=patterns,
            context=["school", "attend", "enrolled"]
        )


__all__ = [
    "StudentIDRecognizer",
    "GradeLevelRecognizer",
    "SchoolNameRecognizer",
    "PRESIDIO_AVAILABLE",
]
