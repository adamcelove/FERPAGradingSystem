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


# ============================================================================
# TestSemanticAnalysis
# ============================================================================


class TestSemanticAnalysis:
    """Tests for semantic analysis with mocked Claude API."""

    @pytest.fixture
    def mock_anthropic_client(self):
        """Create a mock for the Anthropic client.

        Returns a mock that can be configured to return specific responses
        for completeness and consistency analysis.
        """
        mock_client = MagicMock()

        # Create a mock response structure
        def create_mock_response(text_content):
            mock_response = MagicMock()
            mock_content_block = MagicMock()
            mock_content_block.text = text_content
            mock_response.content = [mock_content_block]
            mock_response.model = "claude-sonnet-4-20250514"
            return mock_response

        mock_client.messages.create = MagicMock(
            side_effect=lambda **kwargs: create_mock_response(
                # Default response, can be overridden in individual tests
                '{"specificity_score": 0.8, "actionability_score": 0.7, '
                '"evidence_score": 0.9, "length_score": 0.6, "tone_score": 0.85, '
                '"missing_elements": [], "explanation": "Mock response"}'
            )
        )
        mock_client._create_mock_response = create_mock_response
        return mock_client

    @pytest.fixture
    def ferpa_enforced_client_with_mock(
        self, mock_anthropic_client, ferpa_gate
    ):
        """Create a FERPAEnforcedClient with mocked Anthropic client."""
        client = FERPAEnforcedClient(
            api_key="test-key",
            gate=ferpa_gate,
            enable_zdr=True,
        )
        # Inject the mock client
        client._client = mock_anthropic_client
        return client

    def test_completeness_scoring(
        self,
        mock_anthropic_client,
        ferpa_enforced_client_with_mock,
        comment_clean_anonymized,
    ):
        """Test that CompletenessAnalyzer correctly scores comments with mocked API."""
        from ferpa_feedback.stage_4_semantic import CompletenessAnalyzer
        from ferpa_feedback.models import ConfidenceLevel

        # Configure mock response for completeness analysis
        completeness_response = (
            '{"specificity_score": 0.85, "actionability_score": 0.75, '
            '"evidence_score": 0.90, "length_score": 0.70, "tone_score": 0.80, '
            '"missing_elements": ["more examples"], '
            '"explanation": "Good feedback but could use more specific examples"}'
        )
        mock_anthropic_client.messages.create = MagicMock(
            return_value=mock_anthropic_client._create_mock_response(
                completeness_response
            )
        )

        # Create analyzer with the mocked client
        analyzer = CompletenessAnalyzer(
            client=ferpa_enforced_client_with_mock,
            rubric_path=None,
        )

        # Analyze the comment
        result = analyzer.analyze(comment_clean_anonymized)

        # Verify the result structure
        assert result is not None
        assert result.specificity_score == 0.85
        assert result.actionability_score == 0.75
        assert result.evidence_score == 0.90
        assert result.length_score == 0.70
        assert result.tone_score == 0.80

        # Verify overall score calculation (weighted average)
        # specificity * 0.25 + actionability * 0.25 + evidence * 0.20 + length * 0.15 + tone * 0.15
        expected_score = (
            0.85 * 0.25 +
            0.75 * 0.25 +
            0.90 * 0.20 +
            0.70 * 0.15 +
            0.80 * 0.15
        )
        assert abs(result.score - expected_score) < 0.01

        # Verify is_complete based on threshold (>= 0.6)
        assert result.is_complete is True

        # Verify missing elements were captured
        assert "more examples" in result.missing_elements

        # Verify explanation was captured
        assert "specific examples" in result.explanation

        # Verify API was called
        mock_anthropic_client.messages.create.assert_called_once()

    def test_completeness_scoring_low_score(
        self,
        mock_anthropic_client,
        ferpa_enforced_client_with_mock,
        comment_clean_anonymized,
    ):
        """Test that CompletenessAnalyzer correctly identifies incomplete comments."""
        from ferpa_feedback.stage_4_semantic import CompletenessAnalyzer

        # Configure mock response for a low-scoring comment
        low_score_response = (
            '{"specificity_score": 0.3, "actionability_score": 0.2, '
            '"evidence_score": 0.1, "length_score": 0.4, "tone_score": 0.5, '
            '"missing_elements": ["specific examples", "actionable feedback", "evidence"], '
            '"explanation": "Comment is too vague and lacks actionable guidance"}'
        )
        mock_anthropic_client.messages.create = MagicMock(
            return_value=mock_anthropic_client._create_mock_response(
                low_score_response
            )
        )

        analyzer = CompletenessAnalyzer(
            client=ferpa_enforced_client_with_mock,
        )

        result = analyzer.analyze(comment_clean_anonymized)

        # With low scores, overall should be below 0.6 threshold
        assert result.is_complete is False
        assert result.score < 0.6

        # Verify missing elements captured
        assert len(result.missing_elements) == 3

    def test_consistency_detection_consistent(
        self,
        mock_anthropic_client,
        ferpa_enforced_client_with_mock,
        comment_clean_anonymized,
    ):
        """Test that ConsistencyAnalyzer detects consistent grade-comment pairs."""
        from ferpa_feedback.stage_4_semantic import ConsistencyAnalyzer
        from ferpa_feedback.models import ConfidenceLevel

        # Configure mock response for consistent analysis
        # Comment has grade "C" and should have constructive sentiment
        consistent_response = (
            '{"is_consistent": true, "grade_sentiment": "neutral", '
            '"comment_sentiment": "neutral", "conflicting_phrases": [], '
            '"explanation": "The comment provides constructive feedback appropriate for a C grade"}'
        )
        mock_anthropic_client.messages.create = MagicMock(
            return_value=mock_anthropic_client._create_mock_response(
                consistent_response
            )
        )

        analyzer = ConsistencyAnalyzer(
            client=ferpa_enforced_client_with_mock,
        )

        result = analyzer.analyze(
            comment_clean_anonymized,
            grade=comment_clean_anonymized.grade,
        )

        # Verify consistency detected
        assert result.is_consistent is True
        assert result.grade_sentiment == "neutral"
        assert result.comment_sentiment == "neutral"
        assert len(result.conflicting_phrases) == 0

        # When sentiments match, confidence should be HIGH
        assert result.confidence == ConfidenceLevel.HIGH

    def test_consistency_detection_inconsistent(
        self,
        mock_anthropic_client,
        ferpa_enforced_client_with_mock,
        comment_clean_anonymized,
    ):
        """Test that ConsistencyAnalyzer detects misaligned grade-comment pairs."""
        from ferpa_feedback.stage_4_semantic import ConsistencyAnalyzer
        from ferpa_feedback.models import ConfidenceLevel

        # Configure mock response for inconsistent analysis
        # A failing grade with overly positive comments
        inconsistent_response = (
            '{"is_consistent": false, "grade_sentiment": "negative", '
            '"comment_sentiment": "positive", '
            '"conflicting_phrases": ["excellent work", "outstanding performance"], '
            '"explanation": "Comment is overly positive for a failing grade"}'
        )
        mock_anthropic_client.messages.create = MagicMock(
            return_value=mock_anthropic_client._create_mock_response(
                inconsistent_response
            )
        )

        analyzer = ConsistencyAnalyzer(
            client=ferpa_enforced_client_with_mock,
        )

        # Analyze with a failing grade
        result = analyzer.analyze(
            comment_clean_anonymized,
            grade="F",
        )

        # Verify inconsistency detected
        assert result.is_consistent is False
        assert result.grade_sentiment == "negative"
        assert result.comment_sentiment == "positive"
        assert len(result.conflicting_phrases) == 2
        assert "excellent work" in result.conflicting_phrases

        # Clear misalignment should have HIGH confidence
        assert result.confidence == ConfidenceLevel.HIGH

    def test_consistency_detection_ambiguous(
        self,
        mock_anthropic_client,
        ferpa_enforced_client_with_mock,
        comment_clean_anonymized,
    ):
        """Test that ConsistencyAnalyzer handles ambiguous sentiment with MEDIUM confidence."""
        from ferpa_feedback.stage_4_semantic import ConsistencyAnalyzer
        from ferpa_feedback.models import ConfidenceLevel

        # Configure mock response with mixed/ambiguous sentiment
        ambiguous_response = (
            '{"is_consistent": true, "grade_sentiment": "mixed", '
            '"comment_sentiment": "neutral", "conflicting_phrases": [], '
            '"explanation": "Grade and comment have ambiguous alignment"}'
        )
        mock_anthropic_client.messages.create = MagicMock(
            return_value=mock_anthropic_client._create_mock_response(
                ambiguous_response
            )
        )

        analyzer = ConsistencyAnalyzer(
            client=ferpa_enforced_client_with_mock,
        )

        result = analyzer.analyze(
            comment_clean_anonymized,
            grade="B-",
        )

        # Ambiguous sentiment should result in MEDIUM confidence
        assert result.is_consistent is True
        assert result.confidence == ConfidenceLevel.MEDIUM

    def test_semantic_analyzer_without_client_returns_stub(
        self,
        comment_clean_anonymized,
    ):
        """Test that analyzers return stub results when no client is provided."""
        from ferpa_feedback.stage_4_semantic import (
            CompletenessAnalyzer,
            ConsistencyAnalyzer,
        )
        from ferpa_feedback.models import ConfidenceLevel

        # Create analyzers without client
        completeness_analyzer = CompletenessAnalyzer(client=None)
        consistency_analyzer = ConsistencyAnalyzer(client=None)

        # Analyze should return stub results
        completeness = completeness_analyzer.analyze(comment_clean_anonymized)
        consistency = consistency_analyzer.analyze(
            comment_clean_anonymized,
            grade=comment_clean_anonymized.grade,
        )

        # Verify stub results
        assert completeness.confidence == ConfidenceLevel.UNKNOWN
        assert completeness.explanation == "API unavailable - using stub analysis"

        assert consistency.confidence == ConfidenceLevel.UNKNOWN
        assert consistency.explanation == "API unavailable - using stub analysis"

    def test_semantic_analyzer_handles_malformed_json(
        self,
        mock_anthropic_client,
        ferpa_enforced_client_with_mock,
        comment_clean_anonymized,
    ):
        """Test that analyzers handle malformed JSON responses gracefully."""
        from ferpa_feedback.stage_4_semantic import CompletenessAnalyzer
        from ferpa_feedback.models import ConfidenceLevel

        # Configure mock to return malformed JSON
        mock_anthropic_client.messages.create = MagicMock(
            return_value=mock_anthropic_client._create_mock_response(
                "This is not valid JSON at all"
            )
        )

        analyzer = CompletenessAnalyzer(
            client=ferpa_enforced_client_with_mock,
        )

        result = analyzer.analyze(comment_clean_anonymized)

        # Should fall back to stub result
        assert result.confidence == ConfidenceLevel.UNKNOWN
        assert "stub" in result.explanation.lower() or "unavailable" in result.explanation.lower()

    def test_semantic_analyzer_handles_markdown_json(
        self,
        mock_anthropic_client,
        ferpa_enforced_client_with_mock,
        comment_clean_anonymized,
    ):
        """Test that analyzers correctly parse JSON wrapped in markdown code blocks."""
        from ferpa_feedback.stage_4_semantic import CompletenessAnalyzer

        # Configure mock to return JSON in markdown code block
        markdown_response = (
            '```json\n'
            '{"specificity_score": 0.9, "actionability_score": 0.85, '
            '"evidence_score": 0.8, "length_score": 0.75, "tone_score": 0.9, '
            '"missing_elements": [], "explanation": "Excellent feedback"}\n'
            '```'
        )
        mock_anthropic_client.messages.create = MagicMock(
            return_value=mock_anthropic_client._create_mock_response(
                markdown_response
            )
        )

        analyzer = CompletenessAnalyzer(
            client=ferpa_enforced_client_with_mock,
        )

        result = analyzer.analyze(comment_clean_anonymized)

        # Should successfully parse the markdown-wrapped JSON
        assert result.specificity_score == 0.9
        assert result.actionability_score == 0.85
        assert "Excellent feedback" in result.explanation
