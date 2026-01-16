"""Custom Presidio recognizers for educational PII detection.

This module contains custom recognizers for detecting educational-context PII
such as student IDs, grade levels, and school names.
"""

from ferpa_feedback.recognizers.educational import (
    StudentIDRecognizer,
    GradeLevelRecognizer,
    SchoolNameRecognizer,
    PRESIDIO_AVAILABLE,
)

__all__ = [
    "StudentIDRecognizer",
    "GradeLevelRecognizer",
    "SchoolNameRecognizer",
    "PRESIDIO_AVAILABLE",
]
