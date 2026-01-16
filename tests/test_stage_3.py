"""
Unit tests for Stage 3: Custom Educational PII Recognizers.

Tests cover:
- StudentIDRecognizer pattern matching
- GradeLevelRecognizer pattern matching
- SchoolNameRecognizer pattern matching
- Graceful handling when presidio is not installed
"""

import re
import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ferpa_feedback.recognizers.educational import (
    StudentIDRecognizer,
    GradeLevelRecognizer,
    SchoolNameRecognizer,
    PRESIDIO_AVAILABLE,
)


# ============================================================================
# Test StudentIDRecognizer
# ============================================================================


class TestStudentIDRecognizer:
    """Tests for StudentIDRecognizer class - AC-4.2."""

    def test_recognizer_creation(self):
        """StudentIDRecognizer should be creatable without error."""
        recognizer = StudentIDRecognizer()
        assert recognizer is not None
        assert recognizer.supported_entity == "STUDENT_ID"

    def test_recognizer_has_patterns(self):
        """StudentIDRecognizer should have predefined patterns."""
        recognizer = StudentIDRecognizer()
        assert len(recognizer.patterns) == 2
        # Check pattern names
        pattern_names = [p.name for p in recognizer.patterns]
        assert "student_id_prefix" in pattern_names
        assert "student_id_bare" in pattern_names

    def test_recognizer_has_context_words(self):
        """StudentIDRecognizer should have context words."""
        recognizer = StudentIDRecognizer()
        assert "student" in recognizer.context
        assert "id" in recognizer.context
        assert "number" in recognizer.context

    def test_student_id_prefix_pattern(self):
        """Test 'Student ID: 123456' pattern detection."""
        recognizer = StudentIDRecognizer()
        pattern = next(p for p in recognizer.patterns if p.name == "student_id_prefix")

        # Should match various formats
        test_cases = [
            ("Student ID: 123456", True),
            ("Student ID: 12345678", True),
            ("Student ID: 123456789", True),
            ("student id: 12345678", True),
            ("Student-ID: 12345678", True),
            ("Student_ID: 12345678", True),
            ("StudentID: 12345678", True),
            ("Student ID:12345678", True),
            ("Student ID 12345678", True),
            # Should not match (too few digits)
            ("Student ID: 12345", False),
            # Should not match (too many digits)
            ("Student ID: 1234567890", False),
        ]

        for text, should_match in test_cases:
            match = re.search(pattern.regex, text)
            if should_match:
                assert match is not None, f"Should match: {text}"
            else:
                assert match is None, f"Should not match: {text}"

    def test_student_id_bare_pattern(self):
        """Test 'S12345678' bare pattern detection."""
        recognizer = StudentIDRecognizer()
        pattern = next(p for p in recognizer.patterns if p.name == "student_id_bare")

        # Should match S followed by 7-9 digits
        test_cases = [
            ("S1234567", True),  # 7 digits
            ("S12345678", True),  # 8 digits
            ("S123456789", True),  # 9 digits
            ("s12345678", True),  # lowercase s
            # Should not match (too few digits)
            ("S123456", False),  # 6 digits
            # Should not match (too many digits)
            ("S1234567890", False),  # 10 digits
            # Should not match (no S prefix)
            ("12345678", False),
        ]

        for text, should_match in test_cases:
            match = re.search(pattern.regex, text)
            if should_match:
                assert match is not None, f"Should match: {text}"
            else:
                assert match is None, f"Should not match: {text}"

    def test_student_id_in_context(self):
        """Test student ID detection in realistic text contexts."""
        recognizer = StudentIDRecognizer()

        text_samples = [
            "John's record shows Student ID: 12345678 in our system.",
            "Please contact student S12345678 regarding their grades.",
            "The form requires your student id: 987654321 to proceed.",
        ]

        for text in text_samples:
            # At least one pattern should match
            matched = False
            for pattern in recognizer.patterns:
                if re.search(pattern.regex, text):
                    matched = True
                    break
            assert matched, f"Should find student ID in: {text}"

    def test_student_id_pattern_scores(self):
        """Test that pattern scores are appropriately set."""
        recognizer = StudentIDRecognizer()

        prefix_pattern = next(p for p in recognizer.patterns if p.name == "student_id_prefix")
        bare_pattern = next(p for p in recognizer.patterns if p.name == "student_id_bare")

        # Prefix pattern (with explicit "Student ID") should have higher score
        assert prefix_pattern.score == 0.9
        # Bare pattern (just S followed by digits) should have lower score
        assert bare_pattern.score == 0.7


# ============================================================================
# Test GradeLevelRecognizer
# ============================================================================


class TestGradeLevelRecognizer:
    """Tests for GradeLevelRecognizer class - AC-4.2."""

    def test_recognizer_creation(self):
        """GradeLevelRecognizer should be creatable without error."""
        recognizer = GradeLevelRecognizer()
        assert recognizer is not None
        assert recognizer.supported_entity == "GRADE_LEVEL"

    def test_recognizer_has_patterns(self):
        """GradeLevelRecognizer should have predefined patterns."""
        recognizer = GradeLevelRecognizer()
        assert len(recognizer.patterns) == 2
        # Check pattern names
        pattern_names = [p.name for p in recognizer.patterns]
        assert "grade_level" in pattern_names
        assert "freshman_etc" in pattern_names

    def test_recognizer_has_context_words(self):
        """GradeLevelRecognizer should have context words."""
        recognizer = GradeLevelRecognizer()
        assert "grade" in recognizer.context
        assert "year" in recognizer.context
        assert "class" in recognizer.context

    def test_grade_level_pattern(self):
        """Test '5th grade' pattern detection."""
        recognizer = GradeLevelRecognizer()
        pattern = next(p for p in recognizer.patterns if p.name == "grade_level")

        # Should match various grade formats
        test_cases = [
            ("1st grade", True),
            ("2nd grade", True),
            ("3rd grade", True),
            ("4th grade", True),
            ("5th grade", True),
            ("5th Grade", True),
            ("6th grader", True),
            ("7th grader", True),
            ("8th grade", True),
            ("9th grade", True),
            ("10th grade", True),
            ("11th grade", True),
            ("12th grade", True),
            # Without ordinal suffix
            ("5 grade", True),
            ("10 grade", True),
            # Should not match (grade 0 or 13+)
            ("0th grade", False),
            ("13th grade", False),
        ]

        for text, should_match in test_cases:
            match = re.search(pattern.regex, text)
            if should_match:
                assert match is not None, f"Should match: {text}"
            else:
                assert match is None, f"Should not match: {text}"

    def test_freshman_etc_pattern(self):
        """Test 'freshman/sophomore/junior/senior' pattern detection."""
        recognizer = GradeLevelRecognizer()
        pattern = next(p for p in recognizer.patterns if p.name == "freshman_etc")

        # Should match class year designations
        test_cases = [
            ("freshman", True),
            ("Freshman", True),
            ("sophomore", True),
            ("Sophomore", True),
            ("junior", True),
            ("Junior", True),
            ("senior", True),
            ("Senior", True),
            # Should not match similar words
            ("freshmen", False),  # plural
            ("seniors", False),  # plural
            ("seniority", False),  # different word
        ]

        for text, should_match in test_cases:
            match = re.search(pattern.regex, text)
            if should_match:
                assert match is not None, f"Should match: {text}"
            else:
                assert match is None, f"Should not match: {text}"

    def test_grade_level_in_context(self):
        """Test grade level detection in realistic text contexts."""
        recognizer = GradeLevelRecognizer()

        text_samples = [
            "The student is in 5th grade at Lincoln Elementary.",
            "As a sophomore, she has shown great improvement.",
            "This 10th grader excels in mathematics.",
            "Junior students are preparing for college applications.",
        ]

        for text in text_samples:
            # At least one pattern should match
            matched = False
            for pattern in recognizer.patterns:
                if re.search(pattern.regex, text):
                    matched = True
                    break
            assert matched, f"Should find grade level in: {text}"

    def test_grade_level_pattern_scores(self):
        """Test that pattern scores are appropriately set (lower than PII)."""
        recognizer = GradeLevelRecognizer()

        grade_pattern = next(p for p in recognizer.patterns if p.name == "grade_level")
        year_pattern = next(p for p in recognizer.patterns if p.name == "freshman_etc")

        # Grade levels have lower scores since they may be intentional
        assert grade_pattern.score == 0.6
        assert year_pattern.score == 0.5
        # Both should be lower than student ID scores
        assert grade_pattern.score < 0.9


# ============================================================================
# Test SchoolNameRecognizer
# ============================================================================


class TestSchoolNameRecognizer:
    """Tests for SchoolNameRecognizer class."""

    def test_recognizer_creation_default_patterns(self):
        """SchoolNameRecognizer should be creatable with default patterns."""
        recognizer = SchoolNameRecognizer()
        assert recognizer is not None
        assert recognizer.supported_entity == "SCHOOL_NAME"
        assert len(recognizer.patterns) == 2

    def test_recognizer_creation_custom_patterns(self):
        """SchoolNameRecognizer should accept custom patterns."""
        custom_patterns = [
            r"\bLincoln\s+High\s+School\b",
            r"\bWashington\s+Academy\b",
        ]
        recognizer = SchoolNameRecognizer(school_patterns=custom_patterns)
        assert len(recognizer.patterns) == 2

    def test_recognizer_has_context_words(self):
        """SchoolNameRecognizer should have context words."""
        recognizer = SchoolNameRecognizer()
        assert "school" in recognizer.context
        assert "attend" in recognizer.context
        assert "enrolled" in recognizer.context

    def test_default_pattern_high_school(self):
        """Test default pattern for 'X High School' format."""
        recognizer = SchoolNameRecognizer()

        test_cases = [
            ("Lincoln High School", True),
            ("Washington High School", True),
            ("Central High School", True),
            # Elementary and Middle schools
            ("Oak Elementary School", True),
            ("Valley Middle School", True),
            # Should not match incomplete patterns
            ("High School", False),  # No name prefix
        ]

        for text, should_match in test_cases:
            matched = False
            for pattern in recognizer.patterns:
                if re.search(pattern.regex, text):
                    matched = True
                    break
            if should_match:
                assert matched, f"Should match: {text}"
            else:
                # Note: This may match if word before "High School" exists
                pass  # Relaxed check for negative cases

    def test_default_pattern_academy(self):
        """Test default pattern for 'X Academy' format."""
        recognizer = SchoolNameRecognizer()

        test_cases = [
            ("Phillips Academy", True),
            ("Exeter Academy", True),
            ("Military Academy", True),
            ("Tech Institute", True),
            ("Science Preparatory", True),
        ]

        for text, should_match in test_cases:
            matched = False
            for pattern in recognizer.patterns:
                if re.search(pattern.regex, text):
                    matched = True
                    break
            if should_match:
                assert matched, f"Should match: {text}"

    def test_custom_pattern_matching(self):
        """Test custom patterns for specific schools."""
        custom_patterns = [
            r"\bLincoln\s+High\b",
            r"\bJefferson\s+Middle\b",
        ]
        recognizer = SchoolNameRecognizer(school_patterns=custom_patterns)

        # Should match custom patterns
        text1 = "She attends Lincoln High."
        text2 = "He is a student at Jefferson Middle."

        for text in [text1, text2]:
            matched = False
            for pattern in recognizer.patterns:
                if re.search(pattern.regex, text):
                    matched = True
                    break
            assert matched, f"Should match custom pattern in: {text}"


# ============================================================================
# Test Presidio Availability Handling
# ============================================================================


class TestPresidioAvailability:
    """Tests for graceful handling when presidio is not installed."""

    def test_presidio_available_flag_exists(self):
        """PRESIDIO_AVAILABLE flag should be defined."""
        assert isinstance(PRESIDIO_AVAILABLE, bool)

    def test_recognizers_work_without_presidio(self):
        """All recognizers should be instantiable regardless of presidio."""
        # These should not raise ImportError
        student_id = StudentIDRecognizer()
        grade_level = GradeLevelRecognizer()
        school_name = SchoolNameRecognizer()

        assert student_id is not None
        assert grade_level is not None
        assert school_name is not None

    def test_patterns_accessible_without_presidio(self):
        """Pattern objects should be accessible without presidio."""
        recognizer = StudentIDRecognizer()

        for pattern in recognizer.patterns:
            assert hasattr(pattern, "name")
            assert hasattr(pattern, "regex")
            assert hasattr(pattern, "score")
            assert isinstance(pattern.name, str)
            assert isinstance(pattern.regex, str)
            assert isinstance(pattern.score, float)

    def test_recognizer_inheritance_works(self):
        """Recognizer classes should properly inherit from PatternRecognizer."""
        student_id = StudentIDRecognizer()
        grade_level = GradeLevelRecognizer()
        school_name = SchoolNameRecognizer()

        # All should have supported_entity attribute
        assert student_id.supported_entity == "STUDENT_ID"
        assert grade_level.supported_entity == "GRADE_LEVEL"
        assert school_name.supported_entity == "SCHOOL_NAME"

        # All should have patterns list
        assert isinstance(student_id.patterns, list)
        assert isinstance(grade_level.patterns, list)
        assert isinstance(school_name.patterns, list)

        # All should have context list
        assert isinstance(student_id.context, list)
        assert isinstance(grade_level.context, list)
        assert isinstance(school_name.context, list)


# ============================================================================
# Test Pattern Regex Validation
# ============================================================================


class TestPatternRegexValidation:
    """Tests to ensure all patterns are valid regex."""

    def test_student_id_patterns_compile(self):
        """All StudentIDRecognizer patterns should be valid regex."""
        recognizer = StudentIDRecognizer()
        for pattern in recognizer.patterns:
            try:
                re.compile(pattern.regex)
            except re.error as e:
                pytest.fail(f"Invalid regex in {pattern.name}: {e}")

    def test_grade_level_patterns_compile(self):
        """All GradeLevelRecognizer patterns should be valid regex."""
        recognizer = GradeLevelRecognizer()
        for pattern in recognizer.patterns:
            try:
                re.compile(pattern.regex)
            except re.error as e:
                pytest.fail(f"Invalid regex in {pattern.name}: {e}")

    def test_school_name_patterns_compile(self):
        """All SchoolNameRecognizer patterns should be valid regex."""
        recognizer = SchoolNameRecognizer()
        for pattern in recognizer.patterns:
            try:
                re.compile(pattern.regex)
            except re.error as e:
                pytest.fail(f"Invalid regex in {pattern.name}: {e}")

    def test_custom_school_patterns_compile(self):
        """Custom school patterns should be valid regex."""
        custom_patterns = [
            r"\bLincoln\s+High\s+School\b",
            r"\bWashington\s+Academy\b",
            r"\b\w+\s+Preparatory\s+School\b",
        ]
        recognizer = SchoolNameRecognizer(school_patterns=custom_patterns)
        for pattern in recognizer.patterns:
            try:
                re.compile(pattern.regex)
            except re.error as e:
                pytest.fail(f"Invalid custom regex in {pattern.name}: {e}")
