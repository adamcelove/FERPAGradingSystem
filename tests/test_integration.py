"""
Integration Tests for FERPA Pipeline

This module tests the full pipeline integration including:
- Full pipeline with sample document processing
- Pipeline with roster integration
- FERPA gate integration across stages
- Critical compliance test: no PII reaches API (NFR-6)

These tests verify that all stages work together correctly and
that FERPA compliance is maintained throughout the pipeline.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ferpa_feedback.models import (
    AnonymizationMapping,
    ClassRoster,
    RosterEntry,
    StudentComment,
    TeacherDocument,
)
from ferpa_feedback.pipeline import (
    FeedbackPipeline,
    PipelineConfig,
    create_pipeline,
)
from ferpa_feedback.stage_3_anonymize import (
    AnonymizationGate,
    AnonymizationProcessor,
    Anonymizer,
    PIIDetector,
    create_anonymization_processor,
)
from ferpa_feedback.stage_4_semantic import (
    CompletenessAnalyzer,
    ConsistencyAnalyzer,
    FERPAEnforcedClient,
    FERPAViolationError,
    SemanticAnalysisProcessor,
    create_semantic_processor,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_roster() -> ClassRoster:
    """Create a sample class roster for integration tests."""
    return ClassRoster(
        class_id="int-class-001",
        class_name="Integration Test Class",
        teacher_name="Dr. Integration",
        term="Test Term 2026",
        students=[
            RosterEntry(
                student_id="S10001001",
                first_name="John",
                last_name="Smith",
                preferred_name=None,
            ),
            RosterEntry(
                student_id="S10001002",
                first_name="Jane",
                last_name="Doe",
                preferred_name="Jenny",
            ),
            RosterEntry(
                student_id="S10001003",
                first_name="Robert",
                last_name="Wilson",
                preferred_name="Bob",
            ),
        ],
    )


@pytest.fixture
def sample_document_with_pii() -> TeacherDocument:
    """Create a sample document containing PII for testing full pipeline."""
    return TeacherDocument(
        id="int-doc-001",
        teacher_name="Dr. Integration",
        class_name="Integration Test Class",
        term="Test Term 2026",
        source_path="/path/to/integration_test.docx",
        comments=[
            StudentComment(
                id="int-comment-001",
                document_id="int-doc-001",
                section_index=0,
                student_name="John Smith",
                grade="B+",
                comment_text="John Smith has shown excellent progress this term. "
                             "He can be reached at john.smith@school.edu.",
            ),
            StudentComment(
                id="int-comment-002",
                document_id="int-doc-001",
                section_index=1,
                student_name="Jane Doe",
                grade="A-",
                comment_text="Jane Doe demonstrates strong analytical skills. "
                             "Student ID: S10001002. Contact: 555-123-4567.",
            ),
        ],
    )


@pytest.fixture
def anonymized_document() -> TeacherDocument:
    """Create a properly anonymized document for testing."""
    return TeacherDocument(
        id="int-doc-002",
        teacher_name="Dr. Integration",
        class_name="Integration Test Class",
        term="Test Term 2026",
        source_path="/path/to/anonymized_test.docx",
        comments=[
            StudentComment(
                id="int-comment-003",
                document_id="int-doc-002",
                section_index=0,
                student_name="John Smith",
                grade="B+",
                comment_text="John Smith has shown excellent progress this term. "
                             "He can be reached at john.smith@school.edu.",
                anonymized_text="[STUDENT_NAME_1] has shown excellent progress this term. "
                               "He can be reached at [EMAIL_1].",
                anonymization_mappings=[
                    AnonymizationMapping(
                        original="John Smith",
                        placeholder="[STUDENT_NAME_1]",
                        entity_type="STUDENT_NAME",
                        start_pos=0,
                        end_pos=10,
                    ),
                    AnonymizationMapping(
                        original="john.smith@school.edu",
                        placeholder="[EMAIL_1]",
                        entity_type="EMAIL",
                        start_pos=67,
                        end_pos=88,
                    ),
                ],
            ),
            StudentComment(
                id="int-comment-004",
                document_id="int-doc-002",
                section_index=1,
                student_name="Jane Doe",
                grade="A-",
                comment_text="Jane Doe demonstrates strong analytical skills. "
                             "Student ID: S10001002. Contact: 555-123-4567.",
                anonymized_text="[STUDENT_NAME_2] demonstrates strong analytical skills. "
                               "[STUDENT_ID_1]. Contact: [PHONE_1].",
                anonymization_mappings=[
                    AnonymizationMapping(
                        original="Jane Doe",
                        placeholder="[STUDENT_NAME_2]",
                        entity_type="STUDENT_NAME",
                        start_pos=0,
                        end_pos=8,
                    ),
                    AnonymizationMapping(
                        original="Student ID: S10001002",
                        placeholder="[STUDENT_ID_1]",
                        entity_type="STUDENT_ID",
                        start_pos=48,
                        end_pos=69,
                    ),
                    AnonymizationMapping(
                        original="555-123-4567",
                        placeholder="[PHONE_1]",
                        entity_type="PHONE",
                        start_pos=80,
                        end_pos=92,
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def pii_detector():
    """Create a PIIDetector for integration tests."""
    return PIIDetector(use_presidio=False)  # Use regex only for test speed


@pytest.fixture
def anonymizer():
    """Create an Anonymizer for integration tests."""
    return Anonymizer()


@pytest.fixture
def anonymization_processor(pii_detector, anonymizer):
    """Create an AnonymizationProcessor for integration tests."""
    return AnonymizationProcessor(pii_detector, anonymizer)


@pytest.fixture
def ferpa_gate(anonymization_processor):
    """Create an AnonymizationGate (FERPA gate) for integration tests."""
    return AnonymizationGate(anonymization_processor)


# ============================================================================
# TestPipelineIntegration
# ============================================================================


class TestPipelineIntegration:
    """Integration tests for the full FERPA pipeline."""

    def test_full_pipeline_with_sample_document(
        self,
        sample_document_with_pii,
        sample_roster,
    ):
        """Test full pipeline processing with a sample document containing PII.

        This test verifies that:
        1. Pipeline can be instantiated
        2. Document can be processed through stages 0-3 (local)
        3. Anonymization is applied to comments containing PII
        4. FERPA gate can verify which comments are API-ready
        """
        # Create pipeline configuration
        config = PipelineConfig()

        # Create pipeline with roster
        pipeline = FeedbackPipeline(config=config, roster=sample_roster)

        # Verify pipeline initialization
        assert pipeline.document_parser is not None
        assert pipeline.grammar_checker is not None
        assert pipeline.name_processor is not None
        assert pipeline.anonymization_processor is not None
        assert pipeline.ferpa_gate is not None

        # Process comments through anonymization (simulating stage 3)
        processed_comments = []
        for comment in sample_document_with_pii.comments:
            processed = pipeline.anonymization_processor.process_comment(comment)
            processed_comments.append(processed)

        # Verify anonymization was applied
        for processed in processed_comments:
            assert processed.anonymized_text is not None, (
                "Each comment should have anonymized_text after processing"
            )
            assert len(processed.anonymization_mappings) > 0, (
                "Comments with PII should have anonymization mappings"
            )

    def test_pipeline_with_roster(self, sample_roster):
        """Test pipeline integration with class roster.

        Verifies that:
        1. Roster is properly set in the pipeline
        2. Name processor receives roster for matching
        3. Anonymization processor uses roster for detection
        """
        config = PipelineConfig()
        pipeline = FeedbackPipeline(config=config, roster=sample_roster)

        # Verify roster is set
        assert pipeline.roster is not None
        assert pipeline.roster.class_id == "int-class-001"
        assert len(pipeline.roster.students) == 3

        # Verify roster is passed to processors
        # The name processor extractor should have the roster
        if hasattr(pipeline.name_processor.extractor, 'roster'):
            assert pipeline.name_processor.extractor.roster == sample_roster

    def test_ferpa_gate_integration(
        self,
        sample_document_with_pii,
        sample_roster,
    ):
        """Test FERPA gate integration in the pipeline.

        Verifies that:
        1. FERPA gate correctly identifies unanonymized comments
        2. FERPA gate allows properly anonymized comments
        3. API-ready comments list only includes safe comments
        """
        config = PipelineConfig()
        pipeline = FeedbackPipeline(config=config, roster=sample_roster)

        # First, verify unanonymized comments are blocked
        for comment in sample_document_with_pii.comments:
            safe_text = pipeline.ferpa_gate.get_safe_text(comment)
            assert safe_text is None, (
                "FERPA gate should block unanonymized comments"
            )

        # Process comments through anonymization
        processed_doc = pipeline.anonymization_processor.process_document(
            sample_document_with_pii
        )

        # Verify processed comments pass the gate
        for comment in processed_doc.comments:
            safe_text = pipeline.ferpa_gate.get_safe_text(comment)
            assert safe_text is not None, (
                "FERPA gate should allow properly anonymized comments"
            )
            # Verify no raw PII in safe_text
            assert "john.smith@school.edu" not in safe_text
            assert "555-123-4567" not in safe_text
            assert "S10001002" not in safe_text

    def test_no_pii_reaches_api(
        self,
        sample_document_with_pii,
        sample_roster,
        ferpa_gate,
    ):
        """Critical compliance test: verify no PII reaches external API (NFR-6).

        This is the most important integration test for FERPA compliance.
        It verifies that:
        1. PII is detected in original comments
        2. PII is anonymized before API calls
        3. FERPA gate blocks any text that still contains PII
        4. FERPAEnforcedClient raises FERPAViolationError for blocked content
        5. Only anonymized text is ever sent to the API
        """
        # Define PII patterns to check for
        # Note: Names are detected via roster, structured PII via regex patterns
        pii_patterns = [
            "john.smith@school.edu",
            "555-123-4567",
            "S10001002",
            "John Smith",
            "Jane Doe",
        ]

        # Create FERPAEnforcedClient
        client = FERPAEnforcedClient(
            api_key="test-key",
            gate=ferpa_gate,
            enable_zdr=True,
        )

        # Test 1: Unanonymized comments should be blocked
        for comment in sample_document_with_pii.comments:
            # FERPA gate should block
            assert ferpa_gate.get_safe_text(comment) is None, (
                "FERPA gate must block unanonymized comments"
            )

            # FERPAEnforcedClient should raise error
            with pytest.raises(FERPAViolationError):
                client.analyze(comment, "Test prompt: {comment_text}")

        # Test 2: Process comments through anonymization WITH ROSTER
        # The roster is critical for name detection (without Presidio)
        pii_detector = PIIDetector(roster=sample_roster, use_presidio=False)
        anonymizer = Anonymizer()
        processor = AnonymizationProcessor(pii_detector, anonymizer)
        processed_doc = processor.process_document(sample_document_with_pii)

        # Test 3: Verify PII is removed from anonymized text
        for comment in processed_doc.comments:
            anonymized_text = comment.anonymized_text
            assert anonymized_text is not None, "Comment should be anonymized"

            for pii in pii_patterns:
                assert pii not in anonymized_text, (
                    f"PII '{pii}' should not appear in anonymized text"
                )

        # Test 4: Create new gate with fresh processor for clean verification
        fresh_gate = AnonymizationGate(processor)
        FERPAEnforcedClient(
            api_key="test-key",
            gate=fresh_gate,
            enable_zdr=True,
        )

        # Test 5: Verify anonymized comments pass the gate
        for comment in processed_doc.comments:
            safe_text = fresh_gate.get_safe_text(comment)
            assert safe_text is not None, (
                "Anonymized comments should pass FERPA gate"
            )

            # Double-check no PII in safe_text
            for pii in pii_patterns:
                assert pii not in safe_text, (
                    f"PII '{pii}' must not appear in API-ready text"
                )

    def test_pipeline_instantiation_without_errors(self):
        """Test that pipeline can be instantiated without errors.

        This is a basic smoke test to ensure all components
        can be loaded and initialized correctly.
        """
        config = PipelineConfig()
        pipeline = FeedbackPipeline(config=config)

        # Verify all core components are initialized
        assert pipeline.config is not None
        assert pipeline.document_parser is not None
        assert pipeline.anonymization_processor is not None
        assert pipeline.ferpa_gate is not None

    def test_api_ready_comments_filtering(
        self,
        sample_document_with_pii,
    ):
        """Test that get_api_ready_comments correctly filters comments.

        Verifies that:
        1. Unanonymized comments are not returned
        2. Properly anonymized comments are returned
        3. The returned tuples contain (comment, safe_text)
        """
        config = PipelineConfig()
        pipeline = FeedbackPipeline(config=config)

        # Unanonymized document should have no API-ready comments
        api_ready = pipeline.get_api_ready_comments(sample_document_with_pii)
        assert len(api_ready) == 0, (
            "Unanonymized comments should not be API-ready"
        )

        # Process document through anonymization
        processed_doc = pipeline.anonymization_processor.process_document(
            sample_document_with_pii
        )

        # Now comments should be API-ready
        api_ready = pipeline.get_api_ready_comments(processed_doc)
        assert len(api_ready) == len(processed_doc.comments), (
            "All properly anonymized comments should be API-ready"
        )

        # Verify tuple structure
        for comment, safe_text in api_ready:
            assert isinstance(comment, StudentComment)
            assert isinstance(safe_text, str)
            assert safe_text == comment.anonymized_text


class TestSemanticAnalysisIntegration:
    """Integration tests for Stage 4 semantic analysis with FERPA gate."""

    def test_semantic_processor_requires_ferpa_gate(self):
        """Test that create_semantic_processor requires FERPA gate."""
        with pytest.raises(ValueError) as exc_info:
            create_semantic_processor(config={}, ferpa_gate=None)

        assert "gate" in str(exc_info.value).lower()

    def test_semantic_processor_with_mocked_api(
        self,
        anonymized_document,
        ferpa_gate,
    ):
        """Test semantic processor integration with mocked API.

        Verifies that:
        1. Semantic processor can be created with FERPA gate
        2. Processor correctly validates comments through gate
        3. Analysis is performed only on clean anonymized comments
        """
        # Create mock for Anthropic client
        mock_client = MagicMock()

        def create_mock_response(text_content):
            mock_response = MagicMock()
            mock_content_block = MagicMock()
            mock_content_block.text = text_content
            mock_response.content = [mock_content_block]
            mock_response.model = "claude-sonnet-4-20250514"
            return mock_response

        mock_client.messages.create = MagicMock(
            side_effect=lambda **kwargs: create_mock_response(
                '{"specificity_score": 0.8, "actionability_score": 0.7, '
                '"evidence_score": 0.9, "length_score": 0.6, "tone_score": 0.85, '
                '"missing_elements": [], "explanation": "Good feedback"}'
            )
        )

        # Create FERPA-enforced client
        ferpa_client = FERPAEnforcedClient(
            api_key="test-key",
            gate=ferpa_gate,
            enable_zdr=True,
        )
        ferpa_client._client = mock_client

        # Create analyzers
        completeness_analyzer = CompletenessAnalyzer(client=ferpa_client)
        consistency_analyzer = ConsistencyAnalyzer(client=ferpa_client)

        # Create semantic processor
        processor = SemanticAnalysisProcessor(
            completeness_analyzer=completeness_analyzer,
            consistency_analyzer=consistency_analyzer,
            ferpa_gate=ferpa_gate,
        )

        # Process a clean anonymized comment
        comment = anonymized_document.comments[0]
        processor.process_comment(comment)

        # Verify analysis was performed (API was called)
        assert mock_client.messages.create.called

    def test_semantic_processor_blocks_pii_comments(
        self,
        sample_document_with_pii,
        ferpa_gate,
    ):
        """Test that semantic processor blocks comments with PII.

        Verifies that:
        1. Comments without anonymized_text are blocked
        2. Processor returns original comment unchanged
        3. No API calls are made for blocked comments
        """
        # Create mock client
        mock_client = MagicMock()

        # Create FERPA-enforced client
        ferpa_client = FERPAEnforcedClient(
            api_key="test-key",
            gate=ferpa_gate,
            enable_zdr=True,
        )
        ferpa_client._client = mock_client

        # Create analyzers
        completeness_analyzer = CompletenessAnalyzer(client=ferpa_client)
        consistency_analyzer = ConsistencyAnalyzer(client=ferpa_client)

        # Create semantic processor
        processor = SemanticAnalysisProcessor(
            completeness_analyzer=completeness_analyzer,
            consistency_analyzer=consistency_analyzer,
            ferpa_gate=ferpa_gate,
        )

        # Try to process unanonymized comment
        comment = sample_document_with_pii.comments[0]
        processed = processor.process_comment(comment)

        # Comment should be returned unchanged (blocked by gate)
        assert processed.completeness is None
        assert processed.consistency is None

        # No API calls should have been made
        assert not mock_client.messages.create.called


class TestEndToEndCompliance:
    """End-to-end compliance tests for FERPA requirements."""

    def test_pii_never_leaves_local_processing(self):
        """Verify PII is contained within local processing stages.

        This test creates a complete workflow and verifies that
        at no point is PII accessible for external API calls.

        Note: We use names that don't conflict with placeholder patterns.
        E.g., "Alex Chen" won't appear in "[STUDENT_NAME_1]" placeholders.
        """
        # Create a roster with the student name for proper name detection
        # Using names that won't conflict with placeholder patterns
        roster = ClassRoster(
            class_id="compliance-class-001",
            class_name="Compliance Test",
            teacher_name="Dr. Compliance",
            term="2026",
            students=[
                RosterEntry(
                    student_id="S99999999",
                    first_name="Alex",
                    last_name="Chen",
                    preferred_name=None,
                ),
            ],
        )

        # Create document with various PII types
        document = TeacherDocument(
            id="compliance-doc-001",
            teacher_name="Dr. Compliance",
            class_name="Compliance Test",
            term="2026",
            source_path="/test/path.docx",
            comments=[
                StudentComment(
                    id="pii-test-001",
                    document_id="compliance-doc-001",
                    section_index=0,
                    student_name="Alex Chen",
                    grade="A",
                    comment_text=(
                        "Alex Chen (SSN: 123-45-6789) has excelled. "
                        "Contact at alex@email.com or 555-999-8888. "
                        "Student ID: S99999999."
                    ),
                ),
            ],
        )

        # Define all PII that must be protected
        protected_pii = [
            "Alex Chen",
            "Alex",
            "Chen",
            "123-45-6789",
            "alex@email.com",
            "555-999-8888",
            "S99999999",
        ]

        # Process through anonymization WITH ROSTER (required for name detection)
        processor = create_anonymization_processor(roster=roster)
        processed = processor.process_document(document)

        # Create FERPA gate
        gate = AnonymizationGate(processor)

        # For each comment, verify the safe text has no PII
        for comment in processed.comments:
            safe_text = gate.get_safe_text(comment)
            assert safe_text is not None, "Anonymized comment should pass gate"

            for pii in protected_pii:
                assert pii not in safe_text, (
                    f"PII '{pii}' must never appear in API-safe text"
                )

    def test_ferpa_violation_error_prevents_api_access(
        self, ferpa_gate
    ):
        """Test that FERPAViolationError is raised for any PII leakage attempt.

        This is a critical safety test ensuring that even if code attempts
        to bypass the gate, an exception is raised.
        """
        # Create a comment with PII (not anonymized)
        pii_comment = StudentComment(
            id="violation-test-001",
            document_id="doc-001",
            section_index=0,
            student_name="Test User",
            grade="B",
            comment_text="Test User can be reached at test@email.com",
            # No anonymized_text - this should trigger violation
        )

        client = FERPAEnforcedClient(
            api_key="test-key",
            gate=ferpa_gate,
            enable_zdr=True,
        )

        # Must raise FERPAViolationError
        with pytest.raises(FERPAViolationError) as exc_info:
            client.analyze(pii_comment, "Analyze: {comment_text}")

        # Error message should include comment ID for debugging
        assert "violation-test-001" in str(exc_info.value)

    def test_zdr_headers_enabled_by_default(self, ferpa_gate):
        """Test that Zero Data Retention headers are enabled by default."""
        client = FERPAEnforcedClient(
            api_key="test-key",
            gate=ferpa_gate,
            # enable_zdr defaults to True
        )

        assert client.enable_zdr is True, (
            "ZDR headers should be enabled by default for FERPA compliance"
        )


class TestPipelineConfiguration:
    """Tests for pipeline configuration and initialization."""

    def test_pipeline_config_defaults(self):
        """Test that PipelineConfig has sensible defaults."""
        config = PipelineConfig()

        # Verify FERPA-safe defaults
        assert config.ferpa_config.get("anonymize_before_api", False) is True, (
            "anonymize_before_api must default to True"
        )

    def test_pipeline_refuses_unsafe_config(self):
        """Test that pipeline refuses to run with unsafe configuration.

        The pipeline should raise an error if anonymize_before_api is disabled.
        """
        # Create a config that disables anonymization before API
        unsafe_config = PipelineConfig()
        unsafe_config.config = {
            "ferpa": {
                "anonymize_before_api": False,  # UNSAFE!
            }
        }

        # Pipeline should refuse to initialize with unsafe config
        with pytest.raises(ValueError) as exc_info:
            FeedbackPipeline(config=unsafe_config)

        assert "FERPA" in str(exc_info.value) or "anonymize" in str(exc_info.value)

    def test_create_pipeline_helper(self):
        """Test the create_pipeline convenience function."""
        pipeline = create_pipeline()

        assert pipeline is not None
        assert isinstance(pipeline, FeedbackPipeline)
        assert pipeline.ferpa_gate is not None
