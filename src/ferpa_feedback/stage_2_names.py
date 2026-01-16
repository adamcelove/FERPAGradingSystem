"""
Stage 2: Name Verification

Detects when a comment mentions a different student than the one it is assigned to,
preventing comments from being sent to the wrong student.

This module provides:
- NameExtractor protocol and StubExtractor for name extraction
- NameMatcher for fuzzy name matching using rapidfuzz
- NameVerificationProcessor for processing comments and documents
- create_name_processor factory function
"""

from typing import Optional, Protocol, List, Tuple

from ferpa_feedback.models import (
    ClassRoster,
    ConfidenceLevel,
    NameMatch,
    StudentComment,
    TeacherDocument,
)

# Try to import rapidfuzz, fall back to stub if unavailable
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

# Try to import GLiNER, fall back to stub if unavailable
try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False


class NameExtractor(Protocol):
    """Protocol for name extraction backends."""

    def extract_names(self, text: str) -> List[Tuple[str, float]]:
        """
        Extract names from text with confidence scores.

        Returns:
            List of (name, confidence) tuples.
        """
        ...

    def set_roster(self, roster: ClassRoster) -> None:
        """Update roster for context-aware extraction."""
        ...


class StubExtractor:
    """Stub name extractor that returns empty list.

    Used as a placeholder until GLiNER/spaCy extractors are implemented.
    """

    def __init__(self, roster: Optional[ClassRoster] = None) -> None:
        self._roster: Optional[ClassRoster] = roster

    def extract_names(self, text: str) -> List[Tuple[str, float]]:
        """Return empty list - stub implementation."""
        return []

    def set_roster(self, roster: ClassRoster) -> None:
        """Update roster for context-aware extraction."""
        self._roster = roster


class GLiNERExtractor:
    """GLiNER-based name extractor using NER for PERSON entities.

    Uses lazy loading for the model to avoid expensive initialization
    until actually needed. Falls back to stub if GLiNER is not available
    or model loading fails.
    """

    def __init__(
        self,
        model_name: str = "urchade/gliner_base",
        threshold: float = 0.5,
        roster: Optional[ClassRoster] = None,
    ) -> None:
        """
        Initialize GLiNER extractor.

        Args:
            model_name: GLiNER model name (default: urchade/gliner_base)
            threshold: Minimum confidence threshold for entity detection (0.0-1.0)
            roster: Optional class roster for context-aware extraction
        """
        self._model_name = model_name
        self._threshold = threshold
        self._roster: Optional[ClassRoster] = roster
        self._model: Optional["GLiNER"] = None
        self._model_load_failed = False

    def _load_model(self) -> bool:
        """
        Lazy load the GLiNER model.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        if self._model is not None:
            return True

        if self._model_load_failed:
            return False

        if not GLINER_AVAILABLE:
            self._model_load_failed = True
            return False

        try:
            self._model = GLiNER.from_pretrained(self._model_name)
            return True
        except Exception:
            # Model loading failed - fall back to stub behavior
            self._model_load_failed = True
            return False

    def extract_names(self, text: str) -> List[Tuple[str, float]]:
        """
        Extract PERSON entities from text using GLiNER.

        Args:
            text: Input text to extract names from.

        Returns:
            List of (name, confidence) tuples for detected PERSON entities.
            Returns empty list if model is not available or loading fails.
        """
        if not self._load_model():
            # Fall back to stub behavior
            return []

        if self._model is None:
            return []

        try:
            # GLiNER predict_entities expects labels list and text
            labels = ["person"]
            entities = self._model.predict_entities(text, labels, threshold=self._threshold)

            # Extract name and score from each entity
            results: List[Tuple[str, float]] = []
            for entity in entities:
                name = entity.get("text", "")
                score = entity.get("score", 0.0)
                if name:
                    results.append((name, float(score)))

            return results
        except Exception:
            # If prediction fails, return empty list
            return []

    def set_roster(self, roster: ClassRoster) -> None:
        """Update roster for context-aware extraction."""
        self._roster = roster


class NameMatcher:
    """Fuzzy matching of extracted names to roster using rapidfuzz."""

    def __init__(
        self,
        threshold: int = 85,
        algorithm: str = "token_sort_ratio",
    ) -> None:
        """
        Initialize name matcher.

        Args:
            threshold: Minimum similarity score (0-100) for a match.
            algorithm: rapidfuzz algorithm (token_sort_ratio, partial_ratio, etc.)
        """
        self.threshold = threshold
        self.algorithm = algorithm

    def match(
        self,
        extracted_name: str,
        expected_name: str,
        all_variants: List[str],
    ) -> NameMatch:
        """
        Match an extracted name against expected student.

        Args:
            extracted_name: Name found in comment text.
            expected_name: Expected student name from header.
            all_variants: All name variants for the expected student.

        Returns:
            NameMatch with similarity score and confidence level.
        """
        # Calculate best match score across all variants
        best_score = 0.0

        if RAPIDFUZZ_AVAILABLE:
            for variant in all_variants:
                if self.algorithm == "token_sort_ratio":
                    score = fuzz.token_sort_ratio(extracted_name, variant)
                elif self.algorithm == "partial_ratio":
                    score = fuzz.partial_ratio(extracted_name, variant)
                else:
                    # Default to token_sort_ratio
                    score = fuzz.token_sort_ratio(extracted_name, variant)

                if score > best_score:
                    best_score = score
        else:
            # Stub: simple case-insensitive exact match
            extracted_lower = extracted_name.lower().strip()
            for variant in all_variants:
                if extracted_lower == variant.lower().strip():
                    best_score = 100.0
                    break

        # Normalize score to 0-1 range
        normalized_score = best_score / 100.0
        is_match = best_score >= self.threshold
        confidence = self._classify_confidence(best_score)

        return NameMatch(
            extracted_name=extracted_name,
            expected_name=expected_name,
            match_score=normalized_score,
            is_match=is_match,
            confidence=confidence,
            extraction_method="stub",  # Will be updated by actual extractors
        )

    def _classify_confidence(self, score: float) -> ConfidenceLevel:
        """Map similarity score to confidence level.

        Args:
            score: Similarity score (0-100)

        Returns:
            ConfidenceLevel based on score thresholds
        """
        if score >= 95:
            return ConfidenceLevel.HIGH
        elif score >= 80:
            return ConfidenceLevel.MEDIUM
        elif score >= 60:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.UNKNOWN


class NameVerificationProcessor:
    """Main processor for Stage 2 - Name Verification."""

    def __init__(
        self,
        extractor: NameExtractor,
        matcher: NameMatcher,
        roster: Optional[ClassRoster] = None,
    ) -> None:
        """
        Initialize the name verification processor.

        Args:
            extractor: Name extraction backend (GLiNER, spaCy, or Stub)
            matcher: Fuzzy name matcher
            roster: Optional class roster for context-aware processing
        """
        self.extractor = extractor
        self.matcher = matcher
        self.roster: Optional[ClassRoster] = roster

        if roster is not None:
            self.extractor.set_roster(roster)

    def set_roster(self, roster: ClassRoster) -> None:
        """Update the roster for name verification."""
        self.roster = roster
        self.extractor.set_roster(roster)

    def process_comment(self, comment: StudentComment) -> StudentComment:
        """
        Verify name usage in a single comment.

        Returns new StudentComment with name_match populated.
        Frozen Pydantic models require returning new instances.
        """
        # Extract names from comment text
        extracted_names = self.extractor.extract_names(comment.comment_text)

        # If no names extracted, return comment unchanged (no name_match)
        if not extracted_names:
            return comment

        # Get name variants for matching
        # If we have a roster, try to find the student's variants
        all_variants: List[str] = [comment.student_name]

        if self.roster is not None:
            student = self.roster.find_student(comment.student_name)
            if student is not None:
                all_variants = student.all_name_variants

        # Match first extracted name against expected student
        # (Future enhancement: check all extracted names)
        first_name, confidence = extracted_names[0]

        name_match = self.matcher.match(
            extracted_name=first_name,
            expected_name=comment.student_name,
            all_variants=all_variants,
        )

        # Return new StudentComment with name_match populated
        # Use model_copy for frozen Pydantic models
        return comment.model_copy(update={"name_match": name_match})

    def process_document(self, document: TeacherDocument) -> TeacherDocument:
        """
        Process all comments in a document.

        Returns new TeacherDocument with all comments processed.
        """
        processed_comments = [
            self.process_comment(comment) for comment in document.comments
        ]

        # TeacherDocument is not frozen, so we can update in place
        # But for consistency, create a new instance
        return TeacherDocument(
            id=document.id,
            teacher_name=document.teacher_name,
            class_name=document.class_name,
            term=document.term,
            source_path=document.source_path,
            processed_at=document.processed_at,
            processing_duration_seconds=document.processing_duration_seconds,
            comments=processed_comments,
        )


def create_name_processor(
    roster: Optional[ClassRoster] = None,
    config: Optional[dict] = None,
) -> NameVerificationProcessor:
    """
    Factory function for creating a NameVerificationProcessor.

    Matches the existing stage patterns (create_* factory functions).

    Args:
        roster: Optional class roster for context-aware name matching.
        config: Optional configuration dict with keys:
            - threshold: int (default 85) - minimum match score
            - algorithm: str (default "token_sort_ratio") - rapidfuzz algorithm

    Returns:
        Configured NameVerificationProcessor instance.
    """
    # Parse config
    if config is None:
        config = {}

    threshold = config.get("threshold", 85)
    algorithm = config.get("algorithm", "token_sort_ratio")

    # Create components
    # For now, use StubExtractor - GLiNERExtractor will be added in task 1.3.2
    extractor = StubExtractor(roster=roster)
    matcher = NameMatcher(threshold=threshold, algorithm=algorithm)

    return NameVerificationProcessor(
        extractor=extractor,
        matcher=matcher,
        roster=roster,
    )
