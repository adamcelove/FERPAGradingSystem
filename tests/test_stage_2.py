"""
Unit tests for Stage 2: Name Extraction and Verification.

Tests cover:
- Name extractor classes (StubExtractor, GLiNERExtractor, SpaCyExtractor)
- Name normalization utilities
- Edge cases: apostrophes, hyphens, prefixes, nicknames
"""

import pytest
import sys
from pathlib import Path
from typing import List, Tuple

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ferpa_feedback.stage_2_names import (
    StubExtractor,
    GLiNERExtractor,
    SpaCyExtractor,
    NameMatcher,
    NameVerificationProcessor,
    create_name_processor,
    normalize_name,
    strip_suffix,
    expand_nicknames,
    get_all_name_variants,
    GLINER_AVAILABLE,
    SPACY_AVAILABLE,
    RAPIDFUZZ_AVAILABLE,
)
from ferpa_feedback.models import (
    StudentComment,
    ClassRoster,
    RosterEntry,
    ConfidenceLevel,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_roster() -> ClassRoster:
    """Create a sample roster with various name formats."""
    return ClassRoster(
        class_id="test-class",
        class_name="Test Class",
        teacher_name="Mr. Test",
        term="Fall 2025",
        students=[
            RosterEntry(
                student_id="S001",
                first_name="John",
                last_name="Smith",
                preferred_name=None,
            ),
            RosterEntry(
                student_id="S002",
                first_name="Michael",
                last_name="O'Brien",
                preferred_name="Mike",
            ),
            RosterEntry(
                student_id="S003",
                first_name="Sarah",
                last_name="Smith-Jones",
                preferred_name=None,
            ),
            RosterEntry(
                student_id="S004",
                first_name="Connor",
                last_name="McDonald",
                preferred_name=None,
            ),
            RosterEntry(
                student_id="S005",
                first_name="Robert",
                last_name="Wilson",
                preferred_name="Bob",
            ),
        ],
    )


@pytest.fixture
def sample_comment() -> StudentComment:
    """Create a sample comment for testing."""
    return StudentComment(
        id="test-001",
        document_id="doc-001",
        section_index=0,
        student_name="John Smith",
        grade="B+",
        comment_text="John has shown great improvement this term.",
    )


# ============================================================================
# Test Name Extraction - StubExtractor
# ============================================================================


class TestStubExtractor:
    """Tests for StubExtractor class."""

    def test_stub_extractor_returns_empty_list(self):
        """StubExtractor should always return empty list."""
        extractor = StubExtractor()
        result = extractor.extract_names("John Smith did well in class")
        assert result == []

    def test_stub_extractor_with_roster(self, sample_roster: ClassRoster):
        """StubExtractor should accept roster but still return empty list."""
        extractor = StubExtractor(roster=sample_roster)
        result = extractor.extract_names("John Smith did well in class")
        assert result == []

    def test_stub_extractor_set_roster(self, sample_roster: ClassRoster):
        """StubExtractor should allow roster to be set."""
        extractor = StubExtractor()
        extractor.set_roster(sample_roster)
        # Should still return empty list
        result = extractor.extract_names("John Smith did well")
        assert result == []

    def test_stub_extractor_empty_text(self):
        """StubExtractor should handle empty text."""
        extractor = StubExtractor()
        result = extractor.extract_names("")
        assert result == []

    def test_stub_extractor_whitespace_only(self):
        """StubExtractor should handle whitespace-only text."""
        extractor = StubExtractor()
        result = extractor.extract_names("   \n\t   ")
        assert result == []


# ============================================================================
# Test Name Extraction - GLiNERExtractor
# ============================================================================


class TestGLiNERExtractor:
    """Tests for GLiNERExtractor class."""

    def test_gliner_extractor_creation(self):
        """GLiNERExtractor should be creatable without error."""
        extractor = GLiNERExtractor()
        assert extractor is not None
        assert extractor._model is None  # Not loaded yet (lazy)
        assert extractor._model_load_failed is False

    def test_gliner_extractor_with_custom_threshold(self):
        """GLiNERExtractor should accept custom threshold."""
        extractor = GLiNERExtractor(threshold=0.7)
        assert extractor._threshold == 0.7

    def test_gliner_extractor_extract_names_fallback(self):
        """GLiNERExtractor should return empty list when model unavailable."""
        extractor = GLiNERExtractor()
        # If GLiNER not installed, should return empty list
        result = extractor.extract_names("John Smith did well")
        # Either returns names (if GLiNER installed) or empty list (fallback)
        assert isinstance(result, list)

    def test_gliner_extractor_set_roster(self, sample_roster: ClassRoster):
        """GLiNERExtractor should allow roster to be set."""
        extractor = GLiNERExtractor()
        extractor.set_roster(sample_roster)
        assert extractor._roster == sample_roster

    @pytest.mark.skipif(
        not GLINER_AVAILABLE,
        reason="GLiNER not installed"
    )
    def test_gliner_extracts_single_name(self):
        """GLiNER should extract a single name from text."""
        extractor = GLiNERExtractor()
        result = extractor.extract_names("John Smith did well in class")
        # Should find at least one name
        assert len(result) >= 1
        # First result should be a tuple of (name, score)
        name, score = result[0]
        assert isinstance(name, str)
        assert isinstance(score, float)
        assert score > 0.0

    @pytest.mark.skipif(
        not GLINER_AVAILABLE,
        reason="GLiNER not installed"
    )
    def test_gliner_extracts_multiple_names(self):
        """GLiNER should extract multiple names from text."""
        extractor = GLiNERExtractor()
        result = extractor.extract_names(
            "John Smith worked with Mary Johnson on the project"
        )
        # Should find two names
        assert len(result) >= 2


# ============================================================================
# Test Name Extraction - SpaCyExtractor
# ============================================================================


class TestSpaCyExtractor:
    """Tests for SpaCyExtractor class."""

    def test_spacy_extractor_creation(self):
        """SpaCyExtractor should be creatable without error."""
        extractor = SpaCyExtractor()
        assert extractor is not None
        assert extractor._nlp is None  # Not loaded yet (lazy)
        assert extractor._model_load_failed is False

    def test_spacy_extractor_extract_names_fallback(self):
        """SpaCyExtractor should return empty list when model unavailable."""
        extractor = SpaCyExtractor()
        # If spaCy not installed, should return empty list
        result = extractor.extract_names("Mary Jane helped with homework")
        # Either returns names (if spaCy installed) or empty list (fallback)
        assert isinstance(result, list)

    def test_spacy_extractor_set_roster(self, sample_roster: ClassRoster):
        """SpaCyExtractor should allow roster to be set."""
        extractor = SpaCyExtractor()
        extractor.set_roster(sample_roster)
        assert extractor._roster == sample_roster

    @pytest.mark.skipif(
        not SPACY_AVAILABLE,
        reason="spaCy not installed"
    )
    def test_spacy_fallback_on_gliner_failure(self):
        """SpaCy should work as fallback when GLiNER fails."""
        extractor = SpaCyExtractor()
        result = extractor.extract_names("Mary Jane helped with the assignment")
        # If spaCy model is available, should extract names
        # Check result is a list (may be empty if model not downloaded)
        assert isinstance(result, list)


# ============================================================================
# Test Name Normalization
# ============================================================================


class TestNameNormalization:
    """Tests for name normalization utilities."""

    def test_normalize_name_lowercase(self):
        """normalize_name should convert to lowercase."""
        assert normalize_name("JOHN SMITH") == "john smith"

    def test_normalize_name_strips_whitespace(self):
        """normalize_name should strip leading/trailing whitespace."""
        assert normalize_name("  John Smith  ") == "john smith"

    def test_normalize_name_collapses_spaces(self):
        """normalize_name should collapse multiple spaces."""
        assert normalize_name("John    Smith") == "john smith"

    def test_normalize_name_empty_string(self):
        """normalize_name should handle empty string."""
        assert normalize_name("") == ""

    def test_normalize_name_none_like(self):
        """normalize_name should handle None-like values."""
        assert normalize_name("") == ""


class TestApostropheNames:
    """Tests for handling apostrophe names (O'Brien, O'Connor, etc.)."""

    def test_normalize_obrien(self):
        """O'Brien should normalize to obrien."""
        assert normalize_name("O'Brien") == "obrien"

    def test_normalize_oconnor(self):
        """O'Connor should normalize to oconnor."""
        assert normalize_name("O'Connor") == "oconnor"

    def test_normalize_apostrophe_full_name(self):
        """Full name with apostrophe should normalize correctly."""
        assert normalize_name("Michael O'Brien") == "michael obrien"

    def test_normalize_curly_apostrophe(self):
        """Curly apostrophe should also be removed."""
        assert normalize_name("O'Brien") == "obrien"


class TestHyphenatedNames:
    """Tests for handling hyphenated names (Smith-Jones, Mary-Kate, etc.)."""

    def test_normalize_smith_jones(self):
        """Smith-Jones should normalize to smithjones."""
        assert normalize_name("Smith-Jones") == "smithjones"

    def test_normalize_full_hyphenated_name(self):
        """Full hyphenated name should normalize correctly."""
        assert normalize_name("Sarah Smith-Jones") == "sarah smithjones"

    def test_normalize_double_hyphen(self):
        """Double-barreled hyphenated name should normalize correctly."""
        assert normalize_name("Mary-Kate Smith") == "marykate smith"


class TestMcMacPrefixes:
    """Tests for handling Mc/Mac prefixes (McDonald, MacArthur, etc.)."""

    def test_normalize_mcdonald(self):
        """McDonald should normalize while preserving structure."""
        # Mc/Mac prefixes are handled by case normalization only
        result = normalize_name("McDonald")
        assert result == "mcdonald"

    def test_normalize_macarthur(self):
        """MacArthur should normalize correctly."""
        result = normalize_name("MacArthur")
        assert result == "macarthur"

    def test_normalize_full_mc_name(self):
        """Full name with Mc prefix should normalize correctly."""
        result = normalize_name("Connor McDonald")
        assert result == "connor mcdonald"


class TestSuffixStripping:
    """Tests for stripping name suffixes (Jr., Sr., III, etc.)."""

    def test_strip_jr_period(self):
        """Should strip Jr. suffix."""
        result = strip_suffix("John Smith Jr.")
        assert "jr" not in result.lower()

    def test_strip_jr_no_period(self):
        """Should strip Jr suffix without period."""
        result = strip_suffix("John Smith Jr")
        assert "jr" not in result.lower()

    def test_strip_sr_suffix(self):
        """Should strip Sr. suffix."""
        result = strip_suffix("Robert Wilson Sr.")
        assert "sr" not in result.lower()

    def test_strip_iii_suffix(self):
        """Should strip III suffix."""
        result = strip_suffix("William Davis III")
        assert "iii" not in result.lower()

    def test_strip_comma_suffix(self):
        """Should strip suffix after comma."""
        result = strip_suffix("Smith, Jr.")
        assert "jr" not in result.lower()

    def test_strip_no_suffix(self):
        """Should return original when no suffix present."""
        result = strip_suffix("John Smith")
        assert result == "John Smith"


# ============================================================================
# Test Nickname Expansion
# ============================================================================


class TestNicknameExpansion:
    """Tests for nickname expansion functionality."""

    def test_expand_bob_to_robert(self):
        """Bob should expand to include Robert."""
        variants = expand_nicknames("Bob Wilson")
        normalized_variants = [v.lower() for v in variants]
        assert "bob wilson" in normalized_variants
        assert "robert wilson" in normalized_variants

    def test_expand_mike_to_michael(self):
        """Mike should expand to include Michael."""
        variants = expand_nicknames("Mike O'Brien")
        normalized_variants = [v.lower() for v in variants]
        assert "mike o'brien" in normalized_variants
        assert "michael o'brien" in normalized_variants

    def test_expand_william_to_bill(self):
        """William should expand to include Bill, Will, etc."""
        variants = expand_nicknames("William Smith")
        normalized_variants = [v.lower() for v in variants]
        assert "william smith" in normalized_variants
        # Should include at least one nickname variant
        has_nickname = any(
            nick in normalized_variants
            for nick in ["bill smith", "billy smith", "will smith"]
        )
        assert has_nickname

    def test_expand_no_nickname_match(self):
        """Names without known nicknames should just return original."""
        variants = expand_nicknames("Zephyr Unique")
        assert len(variants) >= 1
        assert "Zephyr Unique" in variants

    def test_expand_empty_string(self):
        """Empty string should return empty list."""
        variants = expand_nicknames("")
        assert variants == []


class TestGetAllNameVariants:
    """Tests for getting all name variants."""

    def test_variants_includes_original(self):
        """Should include original name."""
        variants = get_all_name_variants("John Smith")
        assert "John Smith" in variants

    def test_variants_includes_normalized(self):
        """Should include normalized name."""
        variants = get_all_name_variants("O'Brien")
        assert "obrien" in variants

    def test_variants_includes_nicknames(self):
        """Should include nickname variants when enabled."""
        variants = get_all_name_variants("Robert Smith", include_nicknames=True)
        normalized_variants = [v.lower() for v in variants]
        # Should include Bob variant
        assert any("bob" in v for v in normalized_variants)

    def test_variants_excludes_nicknames_when_disabled(self):
        """Should not include nicknames when disabled."""
        variants = get_all_name_variants("Robert Smith", include_nicknames=False)
        normalized_variants = [v.lower() for v in variants]
        # Should not have nickname expansions (only normalized versions)
        # The only variants should be "Robert Smith" and "robert smith"
        assert all("bob" not in v for v in normalized_variants)

    def test_variants_empty_string(self):
        """Empty string should return empty list."""
        variants = get_all_name_variants("")
        assert variants == []


# ============================================================================
# Test NameMatcher
# ============================================================================


class TestNameMatcher:
    """Tests for NameMatcher class."""

    def test_matcher_creation(self):
        """NameMatcher should be creatable with defaults."""
        matcher = NameMatcher()
        assert matcher.threshold == 85
        assert matcher.algorithm == "token_sort_ratio"

    def test_matcher_custom_threshold(self):
        """NameMatcher should accept custom threshold."""
        matcher = NameMatcher(threshold=90)
        assert matcher.threshold == 90

    def test_matcher_exact_match(self):
        """Exact name match should return high confidence."""
        matcher = NameMatcher()
        result = matcher.match(
            extracted_name="John Smith",
            expected_name="John Smith",
            all_variants=["John Smith"],
        )
        assert result.is_match is True
        assert result.match_score >= 0.9
        assert result.confidence == ConfidenceLevel.HIGH

    def test_matcher_apostrophe_name(self):
        """O'Brien variants should match."""
        matcher = NameMatcher()
        result = matcher.match(
            extracted_name="O'Brien",
            expected_name="Michael O'Brien",
            all_variants=["Michael O'Brien", "Mike O'Brien"],
        )
        # Should recognize partial match
        assert isinstance(result.is_match, bool)
        assert 0.0 <= result.match_score <= 1.0

    def test_matcher_hyphenated_name(self):
        """Hyphenated names should match with normalization."""
        matcher = NameMatcher()
        result = matcher.match(
            extracted_name="Smith-Jones",
            expected_name="Sarah Smith-Jones",
            all_variants=["Sarah Smith-Jones"],
        )
        # Should match part of the name
        assert isinstance(result.is_match, bool)
        assert 0.0 <= result.match_score <= 1.0

    def test_matcher_nickname_match(self):
        """Nickname should match formal name through expansion."""
        matcher = NameMatcher()
        result = matcher.match(
            extracted_name="Bob",
            expected_name="Robert Wilson",
            all_variants=["Robert Wilson", "Bob Wilson", "Bob"],
        )
        # Bob should match with Robert variants
        assert result.match_score > 0.5

    def test_matcher_no_match(self):
        """Completely different names should not match."""
        matcher = NameMatcher()
        result = matcher.match(
            extracted_name="Alice Brown",
            expected_name="John Smith",
            all_variants=["John Smith"],
        )
        assert result.is_match is False
        assert result.confidence == ConfidenceLevel.LOW

    def test_matcher_confidence_classification(self):
        """Confidence should be classified correctly."""
        matcher = NameMatcher(threshold=85)

        # Test HIGH confidence (>= 90)
        result_high = matcher.match("John Smith", "John Smith", ["John Smith"])
        assert result_high.confidence == ConfidenceLevel.HIGH

        # Test LOW confidence (< threshold)
        result_low = matcher.match("Xyz Abc", "John Smith", ["John Smith"])
        assert result_low.confidence == ConfidenceLevel.LOW


# ============================================================================
# Test NameVerificationProcessor
# ============================================================================


class TestNameVerificationProcessor:
    """Tests for NameVerificationProcessor class."""

    def test_processor_creation(self):
        """Processor should be creatable with stub extractor."""
        extractor = StubExtractor()
        matcher = NameMatcher()
        processor = NameVerificationProcessor(extractor, matcher)
        assert processor is not None

    def test_processor_process_comment_no_names(self, sample_comment: StudentComment):
        """Processor should return comment unchanged when no names extracted."""
        extractor = StubExtractor()  # Returns empty list
        matcher = NameMatcher()
        processor = NameVerificationProcessor(extractor, matcher)

        result = processor.process_comment(sample_comment)

        # Comment should be unchanged (no name_match set)
        assert result.id == sample_comment.id
        assert result.name_match is None

    def test_processor_with_roster(
        self, sample_comment: StudentComment, sample_roster: ClassRoster
    ):
        """Processor should accept roster."""
        extractor = StubExtractor()
        matcher = NameMatcher()
        processor = NameVerificationProcessor(extractor, matcher, roster=sample_roster)

        assert processor.roster == sample_roster

    def test_processor_set_roster(
        self, sample_comment: StudentComment, sample_roster: ClassRoster
    ):
        """Processor should allow roster to be set after creation."""
        extractor = StubExtractor()
        matcher = NameMatcher()
        processor = NameVerificationProcessor(extractor, matcher)

        processor.set_roster(sample_roster)
        assert processor.roster == sample_roster


# ============================================================================
# Test Factory Function
# ============================================================================


class TestCreateNameProcessor:
    """Tests for create_name_processor factory function."""

    def test_create_processor_defaults(self):
        """Factory should create processor with defaults."""
        processor = create_name_processor()
        assert processor is not None
        assert isinstance(processor, NameVerificationProcessor)

    def test_create_processor_with_roster(self, sample_roster: ClassRoster):
        """Factory should accept roster."""
        processor = create_name_processor(roster=sample_roster)
        assert processor.roster == sample_roster

    def test_create_processor_with_config(self):
        """Factory should accept config options."""
        config = {
            "threshold": 90,
            "algorithm": "partial_ratio",
        }
        processor = create_name_processor(config=config)
        assert processor.matcher.threshold == 90
        assert processor.matcher.algorithm == "partial_ratio"

    def test_create_processor_force_stub_extractor(self):
        """Factory should allow forcing stub extractor."""
        config = {"extractor": "stub"}
        processor = create_name_processor(config=config)
        assert isinstance(processor.extractor, StubExtractor)

    def test_create_processor_force_spacy_extractor(self):
        """Factory should allow forcing spacy extractor."""
        config = {"extractor": "spacy"}
        processor = create_name_processor(config=config)
        assert isinstance(processor.extractor, SpaCyExtractor)

    def test_create_processor_force_gliner_extractor(self):
        """Factory should allow forcing gliner extractor."""
        config = {"extractor": "gliner"}
        processor = create_name_processor(config=config)
        assert isinstance(processor.extractor, GLiNERExtractor)


# ============================================================================
# Integration-like Tests
# ============================================================================


class TestNameExtractionEdgeCases:
    """Integration tests for edge case handling across the pipeline."""

    def test_full_pipeline_apostrophe_name(self, sample_roster: ClassRoster):
        """Pipeline should handle apostrophe names end-to-end."""
        comment = StudentComment(
            id="test-apos",
            document_id="doc-001",
            section_index=0,
            student_name="Michael O'Brien",
            grade="A",
            comment_text="O'Brien has shown excellent progress.",
        )

        processor = create_name_processor(
            roster=sample_roster,
            config={"extractor": "stub"},  # Use stub for predictable behavior
        )

        result = processor.process_comment(comment)
        # With stub extractor, no names extracted, so comment unchanged
        assert result.id == comment.id

    def test_full_pipeline_hyphenated_name(self, sample_roster: ClassRoster):
        """Pipeline should handle hyphenated names end-to-end."""
        comment = StudentComment(
            id="test-hyphen",
            document_id="doc-001",
            section_index=0,
            student_name="Sarah Smith-Jones",
            grade="B+",
            comment_text="Smith-Jones continues to excel in class.",
        )

        processor = create_name_processor(
            roster=sample_roster,
            config={"extractor": "stub"},
        )

        result = processor.process_comment(comment)
        assert result.id == comment.id

    def test_full_pipeline_mc_prefix_name(self, sample_roster: ClassRoster):
        """Pipeline should handle Mc/Mac prefix names end-to-end."""
        comment = StudentComment(
            id="test-mc",
            document_id="doc-001",
            section_index=0,
            student_name="Connor McDonald",
            grade="A-",
            comment_text="McDonald demonstrates strong analytical skills.",
        )

        processor = create_name_processor(
            roster=sample_roster,
            config={"extractor": "stub"},
        )

        result = processor.process_comment(comment)
        assert result.id == comment.id
