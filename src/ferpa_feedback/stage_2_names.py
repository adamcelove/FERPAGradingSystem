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

import re
from typing import Any, Optional, Protocol, List, Tuple, Dict, Union

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

# Try to import spacy, fall back to stub if unavailable
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False


# Nickname expansion table for common name variations
# Maps nickname -> formal name(s)
NICKNAME_MAP: Dict[str, List[str]] = {
    # William variants
    "bill": ["william"],
    "billy": ["william"],
    "will": ["william"],
    "willy": ["william"],
    # Robert variants
    "bob": ["robert"],
    "bobby": ["robert"],
    "rob": ["robert"],
    "robbie": ["robert"],
    # Richard variants
    "dick": ["richard"],
    "rick": ["richard"],
    "ricky": ["richard"],
    "rich": ["richard"],
    # James variants
    "jim": ["james"],
    "jimmy": ["james"],
    "jamie": ["james"],
    # Michael variants
    "mike": ["michael"],
    "mikey": ["michael"],
    "mick": ["michael"],
    # Elizabeth variants
    "liz": ["elizabeth"],
    "lizzy": ["elizabeth"],
    "beth": ["elizabeth"],
    "betty": ["elizabeth"],
    "eliza": ["elizabeth"],
    # Katherine/Catherine variants
    "kate": ["katherine", "catherine"],
    "katie": ["katherine", "catherine"],
    "kathy": ["katherine", "catherine"],
    "cathy": ["katherine", "catherine"],
    "kat": ["katherine", "catherine"],
    # Jennifer variants
    "jen": ["jennifer"],
    "jenny": ["jennifer"],
    # Margaret variants
    "maggie": ["margaret"],
    "meg": ["margaret"],
    "peggy": ["margaret"],
    # Edward variants
    "ed": ["edward"],
    "eddie": ["edward"],
    "ted": ["edward", "theodore"],
    "teddy": ["edward", "theodore"],
    # Alexander variants
    "alex": ["alexander", "alexandra"],
    "al": ["alexander", "albert", "alfred"],
    "xander": ["alexander"],
    # Daniel variants
    "dan": ["daniel"],
    "danny": ["daniel"],
    # Joseph variants
    "joe": ["joseph"],
    "joey": ["joseph"],
    # Christopher variants
    "chris": ["christopher", "christine", "christina"],
    # Anthony variants
    "tony": ["anthony"],
    # Nicholas variants
    "nick": ["nicholas"],
    "nicky": ["nicholas"],
    # Matthew variants
    "matt": ["matthew"],
    "matty": ["matthew"],
    # Thomas variants
    "tom": ["thomas"],
    "tommy": ["thomas"],
    # Patrick variants
    "pat": ["patrick", "patricia"],
    "patty": ["patricia"],
    # Rebecca variants
    "becky": ["rebecca"],
    "becca": ["rebecca"],
    # Samantha/Samuel variants
    "sam": ["samuel", "samantha"],
    "sammy": ["samuel", "samantha"],
    # Timothy variants
    "tim": ["timothy"],
    "timmy": ["timothy"],
    # Andrew variants
    "andy": ["andrew"],
    "drew": ["andrew"],
    # David variants
    "dave": ["david"],
    "davy": ["david"],
    # Gregory variants
    "greg": ["gregory"],
    # Jonathan variants
    "john": ["jonathan", "johnathan"],
    "jon": ["jonathan", "johnathan"],
    "johnny": ["jonathan", "johnathan", "john"],
    # Stephen/Steven variants
    "steve": ["steven", "stephen"],
    "stevie": ["steven", "stephen"],
    # Benjamin variants
    "ben": ["benjamin"],
    "benny": ["benjamin"],
    # Charles variants
    "charlie": ["charles"],
    "chuck": ["charles"],
    # Victoria variants
    "vicky": ["victoria"],
    "tori": ["victoria"],
    # Deborah variants
    "deb": ["deborah", "debra"],
    "debbie": ["deborah", "debra"],
}

# Reverse mapping: formal name -> nicknames
FORMAL_TO_NICKNAMES: Dict[str, List[str]] = {}
for nickname, formal_names in NICKNAME_MAP.items():
    for formal_name in formal_names:
        if formal_name not in FORMAL_TO_NICKNAMES:
            FORMAL_TO_NICKNAMES[formal_name] = []
        if nickname not in FORMAL_TO_NICKNAMES[formal_name]:
            FORMAL_TO_NICKNAMES[formal_name].append(nickname)

# Common name suffixes to strip
NAME_SUFFIXES = [
    "jr.", "jr", "junior",
    "sr.", "sr", "senior",
    "iii", "ii", "iv", "v",
    "3rd", "2nd", "4th", "5th",
    "esq.", "esq",
    "phd", "ph.d.", "ph.d",
    "md", "m.d.", "m.d",
]


def normalize_name(name: str) -> str:
    """
    Normalize a name for comparison.

    Handles:
    - Case normalization (lowercase)
    - Apostrophe removal (O'Brien -> obrien)
    - Hyphen handling (Smith-Jones -> smithjones for comparison)
    - Suffix stripping (Jr., Sr., III, etc.)
    - Extra whitespace removal

    Args:
        name: The name to normalize.

    Returns:
        Normalized name string for comparison.
    """
    if not name:
        return ""

    # Convert to lowercase
    normalized = name.lower().strip()

    # Strip suffixes (must be done before other transformations)
    normalized = strip_suffix(normalized)

    # Remove apostrophes (O'Brien -> obrien)
    normalized = normalized.replace("'", "").replace("'", "")

    # Remove hyphens (Smith-Jones -> smithjones)
    normalized = normalized.replace("-", "")

    # Collapse multiple spaces to single space
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def strip_suffix(name: str) -> str:
    """
    Strip common name suffixes (Jr., Sr., III, etc.).

    Args:
        name: Name possibly containing a suffix.

    Returns:
        Name with suffix removed.
    """
    if not name:
        return ""

    name_lower = name.lower().strip()

    for suffix in NAME_SUFFIXES:
        # Check if name ends with suffix (with possible comma before)
        patterns = [
            f", {suffix}$",  # "Smith, Jr."
            f" {suffix}$",   # "Smith Jr."
            f",{suffix}$",   # "Smith,Jr." (no space)
        ]
        for pattern in patterns:
            if re.search(pattern, name_lower):
                # Remove the suffix pattern from the original name (preserve case of remaining)
                result = re.sub(pattern, "", name_lower, flags=re.IGNORECASE)
                return result.strip()

    return name


def expand_nicknames(name: str) -> List[str]:
    """
    Expand a name to include nickname variants.

    Given a name, returns a list including:
    - The original name
    - Formal name(s) if the input is a nickname
    - Nicknames if the input is a formal name

    Args:
        name: The name to expand.

    Returns:
        List of name variants including the original.
    """
    if not name:
        return []

    variants = [name]
    name_lower = name.lower().strip()

    # Split name into tokens for multi-word names
    tokens = name_lower.split()

    # Try to expand the first name (first token)
    if tokens:
        first_name = tokens[0]

        # Check if it's a nickname -> get formal names
        if first_name in NICKNAME_MAP:
            for formal_name in NICKNAME_MAP[first_name]:
                # Replace first token with formal name, keep rest of name
                expanded_tokens = [formal_name] + tokens[1:]
                variants.append(" ".join(expanded_tokens))

        # Check if it's a formal name -> get nicknames
        if first_name in FORMAL_TO_NICKNAMES:
            for nickname in FORMAL_TO_NICKNAMES[first_name]:
                # Replace first token with nickname, keep rest of name
                expanded_tokens = [nickname] + tokens[1:]
                variants.append(" ".join(expanded_tokens))

    return variants


def get_all_name_variants(name: str, include_nicknames: bool = True) -> List[str]:
    """
    Get all variants of a name for matching.

    Includes:
    - Original name
    - Normalized name (apostrophes, hyphens removed)
    - Suffix-stripped name
    - Nickname expansions (if enabled)

    Args:
        name: The name to expand.
        include_nicknames: Whether to include nickname expansions.

    Returns:
        List of all name variants.
    """
    if not name:
        return []

    variants = set()

    # Add original
    variants.add(name)

    # Add normalized version
    variants.add(normalize_name(name))

    # Add suffix-stripped version
    stripped = strip_suffix(name)
    if stripped != name:
        variants.add(stripped)
        variants.add(normalize_name(stripped))

    # Add nickname expansions
    if include_nicknames:
        for expanded in expand_nicknames(name):
            variants.add(expanded)
            variants.add(normalize_name(expanded))

    # Remove empty strings
    return [v for v in variants if v]


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


class SpaCyExtractor:
    """spaCy-based name extractor using NER for PERSON entities.

    Used as a fallback when GLiNER is not available or fails.
    Uses lazy loading for the model to avoid expensive initialization
    until actually needed.
    """

    def __init__(
        self,
        model_name: str = "en_core_web_trf",
        roster: Optional[ClassRoster] = None,
    ) -> None:
        """
        Initialize spaCy extractor.

        Args:
            model_name: spaCy model name (default: en_core_web_trf for transformer-based NER)
            roster: Optional class roster for context-aware extraction
        """
        self._model_name = model_name
        self._roster: Optional[ClassRoster] = roster
        self._nlp: Optional["spacy.language.Language"] = None
        self._model_load_failed = False

    def _load_model(self) -> bool:
        """
        Lazy load the spaCy model.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        if self._nlp is not None:
            return True

        if self._model_load_failed:
            return False

        if not SPACY_AVAILABLE:
            self._model_load_failed = True
            return False

        try:
            self._nlp = spacy.load(self._model_name)
            return True
        except OSError:
            # Model not downloaded - try smaller model as fallback
            try:
                self._nlp = spacy.load("en_core_web_sm")
                return True
            except OSError:
                self._model_load_failed = True
                return False
        except Exception:
            # Any other error - fall back to stub behavior
            self._model_load_failed = True
            return False

    def extract_names(self, text: str) -> List[Tuple[str, float]]:
        """
        Extract PERSON entities from text using spaCy NER.

        Args:
            text: Input text to extract names from.

        Returns:
            List of (name, confidence) tuples for detected PERSON entities.
            Returns empty list if model is not available or loading fails.
        """
        if not self._load_model():
            # Fall back to stub behavior
            return []

        if self._nlp is None:
            return []

        try:
            doc = self._nlp(text)
            results: List[Tuple[str, float]] = []

            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    # spaCy doesn't provide confidence scores by default
                    # Use a fixed score of 0.8 as a reasonable default
                    results.append((ent.text, 0.8))

            return results
        except Exception:
            # If NER fails, return empty list
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

        Handles edge cases:
        - Apostrophes (O'Brien, O'Connor)
        - Hyphens (Smith-Jones, Mary-Kate)
        - Prefix capitalization (McDonald, MacArthur) - case-insensitive
        - Suffixes (Jr., Sr., III) - stripped before matching
        - Nicknames (Bill/William, Bob/Robert) - expanded variants

        Args:
            extracted_name: Name found in comment text.
            expected_name: Expected student name from header.
            all_variants: All name variants for the expected student.

        Returns:
            NameMatch with similarity score and confidence level.
        """
        # Expand variants to include normalized versions and nicknames
        expanded_variants = set()
        for variant in all_variants:
            expanded_variants.update(get_all_name_variants(variant, include_nicknames=True))

        # Also get variants for the extracted name
        extracted_variants = get_all_name_variants(extracted_name, include_nicknames=True)

        # Calculate best match score across all variant combinations
        best_score = 0.0

        if RAPIDFUZZ_AVAILABLE:
            # Compare all extracted variants against all expected variants
            for extracted_var in extracted_variants:
                for expected_var in expanded_variants:
                    if self.algorithm == "token_sort_ratio":
                        score = fuzz.token_sort_ratio(extracted_var, expected_var)
                    elif self.algorithm == "partial_ratio":
                        score = fuzz.partial_ratio(extracted_var, expected_var)
                    else:
                        # Default to token_sort_ratio
                        score = fuzz.token_sort_ratio(extracted_var, expected_var)

                    if score > best_score:
                        best_score = score

                    # Early exit if perfect match found
                    if best_score >= 100:
                        break
                if best_score >= 100:
                    break
        else:
            # Stub: simple normalized comparison
            extracted_normalized = normalize_name(extracted_name)
            for variant in expanded_variants:
                variant_normalized = normalize_name(variant)
                if extracted_normalized == variant_normalized:
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
            ConfidenceLevel based on score thresholds:
            - HIGH: score >= 90
            - MEDIUM: score >= threshold (default 85)
            - LOW: score < threshold
        """
        if score >= 90:
            return ConfidenceLevel.HIGH
        elif score >= self.threshold:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW


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
    config: Optional[Dict[str, Any]] = None,
) -> NameVerificationProcessor:
    """
    Factory function for creating a NameVerificationProcessor.

    Matches the existing stage patterns (create_* factory functions).

    Uses fallback pattern for extractor selection:
    1. GLiNER (if available and model loads)
    2. spaCy (if available and model loads)
    3. Stub (always works, returns empty list)

    Args:
        roster: Optional class roster for context-aware name matching.
        config: Optional configuration dict with keys:
            - threshold: int (default 85) - minimum match score
            - algorithm: str (default "token_sort_ratio") - rapidfuzz algorithm
            - extractor: str (optional) - force specific extractor ("gliner", "spacy", "stub")

    Returns:
        Configured NameVerificationProcessor instance.
    """
    # Parse config
    if config is None:
        config = {}

    threshold = config.get("threshold", 85)
    algorithm = config.get("algorithm", "token_sort_ratio")
    forced_extractor = config.get("extractor")

    # Create extractor with fallback pattern: GLiNER -> spaCy -> Stub
    extractor: NameExtractor

    if forced_extractor == "stub":
        extractor = StubExtractor(roster=roster)
    elif forced_extractor == "spacy":
        extractor = SpaCyExtractor(roster=roster)
    elif forced_extractor == "gliner":
        extractor = GLiNERExtractor(roster=roster)
    else:
        # Auto-select with fallback pattern
        if GLINER_AVAILABLE:
            extractor = GLiNERExtractor(roster=roster)
        elif SPACY_AVAILABLE:
            extractor = SpaCyExtractor(roster=roster)
        else:
            extractor = StubExtractor(roster=roster)

    matcher = NameMatcher(threshold=threshold, algorithm=algorithm)

    return NameVerificationProcessor(
        extractor=extractor,
        matcher=matcher,
        roster=roster,
    )
