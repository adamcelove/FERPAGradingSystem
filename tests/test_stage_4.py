"""
Tests for Stage 4: Semantic Analysis

This module tests FERPA gate enforcement and semantic analysis functionality.
Tests ensure that unanonymized content is blocked from reaching external APIs
and that the FERPAViolationError exception is raised appropriately.

Key test areas:
- FERPA gate blocking unanonymized comments
- FERPA gate blocking comments with remaining PII
- FERPA gate allowing clean anonymized comments
- FERPAViolationError exception handling
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ferpa_feedback.models import (
    StudentComment,
    AnonymizationMapping,
)
from ferpa_feedback.stage_3_anonymize import (
    AnonymizationGate,
    AnonymizationProcessor,
    PIIDetector,
    Anonymizer,
)
from ferpa_feedback.stage_4_semantic import (
    FERPAViolationError,
    FERPAEnforcedClient,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def pii_detector():
    """Create a PIIDetector for testing."""
    return PIIDetector(use_presidio=False)  # Use regex only for test speed


@pytest.fixture
def anonymizer():
    """Create an Anonymizer for testing."""
    return Anonymizer()


@pytest.fixture
def anonymization_processor(pii_detector, anonymizer):
    """Create an AnonymizationProcessor for testing."""
    return AnonymizationProcessor(pii_detector, anonymizer)


@pytest.fixture
def ferpa_gate(anonymization_processor):
    """Create an AnonymizationGate (FERPA gate) for testing."""
    return AnonymizationGate(anonymization_processor)


@pytest.fixture
def comment_unanonymized():
    """Create a comment that has NOT been anonymized (no anonymized_text)."""
    return StudentComment(
        id="ferpa-test-001",
        document_id="doc-001",
        section_index=0,
        student_name="John Smith",
        grade="B+",
        comment_text="John Smith has shown great improvement. "
                     "Contact at john.smith@school.edu.",
        # anonymized_text is None - not anonymized
    )


@pytest.fixture
def comment_with_remaining_pii():
    """Create a comment with PII still present in anonymized_text."""
    return StudentComment(
        id="ferpa-test-002",
        document_id="doc-001",
        section_index=1,
        student_name="Jane Doe",
        grade="A-",
        comment_text="Jane Doe (ID: S12345678) can be reached at jane.doe@school.edu.",
        # anonymized_text still contains PII (improperly anonymized)
        anonymized_text="[STUDENT_NAME_1] (ID: S12345678) can be reached at jane.doe@school.edu.",
        anonymization_mappings=[
            AnonymizationMapping(
                original="Jane Doe",
                placeholder="[STUDENT_NAME_1]",
                entity_type="STUDENT_NAME",
                start_pos=0,
                end_pos=8,
            )
        ],
    )


@pytest.fixture
def comment_clean_anonymized():
    """Create a properly anonymized comment with no remaining PII."""
    return StudentComment(
        id="ferpa-test-003",
        document_id="doc-001",
        section_index=2,
        student_name="Bob Wilson",
        grade="C",
        comment_text="Bob Wilson has improved. Contact bob.wilson@school.edu for details.",
        anonymized_text="[STUDENT_NAME_1] has improved. Contact [EMAIL_1] for details.",
        anonymization_mappings=[
            AnonymizationMapping(
                original="Bob Wilson",
                placeholder="[STUDENT_NAME_1]",
                entity_type="STUDENT_NAME",
                start_pos=0,
                end_pos=10,
            ),
            AnonymizationMapping(
                original="bob.wilson@school.edu",
                placeholder="[EMAIL_1]",
                entity_type="EMAIL",
                start_pos=28,
                end_pos=49,
            ),
        ],
    )


# ============================================================================
# TestFERPAGateEnforcement
# ============================================================================


class TestFERPAGateEnforcement:
    """Tests for FERPA gate enforcement functionality."""

    def test_ferpa_blocks_unanonymized_comment(
        self, ferpa_gate, comment_unanonymized
    ):
        """Test that FERPA gate blocks comments without anonymized_text."""
        # Comment has no anonymized_text - should be blocked
        is_valid = ferpa_gate.validate_for_api(comment_unanonymized)

        assert is_valid is False, (
            "FERPA gate should block comments without anonymized_text"
        )

        # get_safe_text should return None
        safe_text = ferpa_gate.get_safe_text(comment_unanonymized)
        assert safe_text is None, (
            "get_safe_text should return None for unanonymized comment"
        )

    def test_ferpa_blocks_comment_with_remaining_pii(
        self, ferpa_gate, comment_with_remaining_pii
    ):
        """Test that FERPA gate blocks comments with PII still in anonymized text."""
        # Comment has anonymized_text but PII (email, student ID) remains
        is_valid = ferpa_gate.validate_for_api(comment_with_remaining_pii)

        assert is_valid is False, (
            "FERPA gate should block comments with remaining PII in anonymized_text"
        )

        # get_safe_text should return None
        safe_text = ferpa_gate.get_safe_text(comment_with_remaining_pii)
        assert safe_text is None, (
            "get_safe_text should return None for comment with remaining PII"
        )

    def test_ferpa_allows_clean_anonymized_comment(
        self, ferpa_gate, comment_clean_anonymized
    ):
        """Test that FERPA gate allows properly anonymized comments."""
        # Comment is properly anonymized with all PII replaced by placeholders
        is_valid = ferpa_gate.validate_for_api(comment_clean_anonymized)

        assert is_valid is True, (
            "FERPA gate should allow clean anonymized comments"
        )

        # get_safe_text should return the anonymized text
        safe_text = ferpa_gate.get_safe_text(comment_clean_anonymized)
        assert safe_text is not None, (
            "get_safe_text should return text for clean anonymized comment"
        )
        assert safe_text == comment_clean_anonymized.anonymized_text, (
            "get_safe_text should return the anonymized_text field"
        )

    def test_ferpa_raises_violation_error(
        self, ferpa_gate, comment_unanonymized
    ):
        """Test that FERPAEnforcedClient raises FERPAViolationError when gate blocks."""
        # Create FERPA-enforced client with the gate
        client = FERPAEnforcedClient(
            api_key="test-key",
            gate=ferpa_gate,
            enable_zdr=True,
        )

        # Attempting to analyze unanonymized comment should raise FERPAViolationError
        with pytest.raises(FERPAViolationError) as exc_info:
            client.analyze(
                comment=comment_unanonymized,
                prompt="Test prompt: {comment_text}",
            )

        # Verify error message contains comment ID
        assert "ferpa-test-001" in str(exc_info.value), (
            "FERPAViolationError should include comment ID"
        )

    def test_ferpa_enforced_client_requires_gate(self):
        """Test that FERPAEnforcedClient requires a gate to be provided."""
        with pytest.raises(ValueError) as exc_info:
            FERPAEnforcedClient(
                api_key="test-key",
                gate=None,  # Gate is required
            )

        assert "gate" in str(exc_info.value).lower(), (
            "ValueError should mention gate requirement"
        )

    def test_ferpa_gate_validates_placeholders_not_as_pii(
        self, ferpa_gate
    ):
        """Test that FERPA gate doesn't flag placeholder text as PII."""
        # Create a comment with multiple placeholders
        comment = StudentComment(
            id="ferpa-test-004",
            document_id="doc-001",
            section_index=3,
            student_name="Test Student",
            grade="B",
            comment_text="Original text with PII",
            anonymized_text=(
                "[STUDENT_NAME_1] and [EMAIL_1] and [PHONE_1] "
                "are all properly anonymized."
            ),
            anonymization_mappings=[],
        )

        # Gate should recognize placeholders and allow this comment
        is_valid = ferpa_gate.validate_for_api(comment)

        assert is_valid is True, (
            "FERPA gate should not flag placeholder patterns as PII"
        )


# ============================================================================
# Additional FERPA Edge Case Tests
# ============================================================================


class TestFERPAEdgeCases:
    """Test edge cases in FERPA gate enforcement."""

    def test_ferpa_empty_anonymized_text_blocked(self, ferpa_gate):
        """Test FERPA gate blocks empty string anonymized_text.

        An empty string is treated as "no anonymized text" because there's
        nothing useful to send to the API. This is a security-conscious
        default behavior.
        """
        comment = StudentComment(
            id="edge-001",
            document_id="doc-001",
            section_index=0,
            student_name="Test",
            grade="A",
            comment_text="Some text",
            anonymized_text="",  # Empty string is falsy in Python
        )

        # Empty string is treated as no anonymized text - should block
        is_valid = ferpa_gate.validate_for_api(comment)
        assert is_valid is False, (
            "Empty anonymized_text should be blocked (treated as no content)"
        )

    def test_ferpa_gate_detects_partial_pii(self, ferpa_gate):
        """Test FERPA gate detects partial PII in mixed content."""
        comment = StudentComment(
            id="edge-002",
            document_id="doc-001",
            section_index=1,
            student_name="Test Student",
            grade="B",
            comment_text="Text with student@example.com email",
            anonymized_text="[STUDENT_NAME_1] did well. Reach at student@example.com.",
            anonymization_mappings=[],
        )

        # Should block because email is not anonymized
        is_valid = ferpa_gate.validate_for_api(comment)
        assert is_valid is False, (
            "FERPA gate should block comments with any remaining PII"
        )

    def test_ferpa_client_handles_gate_rejection_gracefully(
        self, ferpa_gate
    ):
        """Test that FERPAEnforcedClient handles gate rejection before API call."""
        client = FERPAEnforcedClient(
            api_key="test-key",
            gate=ferpa_gate,
        )

        # Create a comment with remaining PII
        comment = StudentComment(
            id="edge-003",
            document_id="doc-001",
            section_index=0,
            student_name="Test",
            grade="A",
            comment_text="Call 555-123-4567 for info",
            anonymized_text="Call 555-123-4567 for info",  # Phone not anonymized
            anonymization_mappings=[],
        )

        # Should raise FERPAViolationError, not make API call
        with pytest.raises(FERPAViolationError):
            client.analyze(comment, "Test: {comment_text}")
