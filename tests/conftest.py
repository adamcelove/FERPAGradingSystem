"""
Shared pytest fixtures for ferpa_feedback tests.

This module provides common fixtures used across test modules including:
- Sample comment fixtures
- Sample document fixtures
- Mock roster fixtures
- Test data loading utilities
"""

import json
import sys
from pathlib import Path
from typing import List

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ferpa_feedback.models import (
    AnonymizationMapping,
    ClassRoster,
    CompletenessResult,
    ConfidenceLevel,
    ConsistencyResult,
    GrammarIssue,
    NameMatch,
    ReviewStatus,
    RosterEntry,
    StudentComment,
    TeacherDocument,
)

# ============================================================================
# Path Fixtures
# ============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_comments_path(fixtures_dir: Path) -> Path:
    """Return path to sample comments JSON file."""
    return fixtures_dir / "sample_comments.json"


@pytest.fixture
def test_roster_path(fixtures_dir: Path) -> Path:
    """Return path to test roster CSV file."""
    return fixtures_dir / "test_roster.csv"


# ============================================================================
# Comment Fixtures
# ============================================================================


@pytest.fixture
def sample_comment() -> StudentComment:
    """Create a minimal sample StudentComment for testing."""
    return StudentComment(
        id="test-001",
        document_id="doc-001",
        section_index=0,
        student_name="John Smith",
        grade="B+",
        comment_text="John has shown great improvement in mathematics this term. "
                     "He actively participates in class discussions and completes "
                     "his homework on time.",
    )


@pytest.fixture
def sample_comment_with_pii() -> StudentComment:
    """Create a StudentComment containing PII for anonymization tests."""
    return StudentComment(
        id="test-002",
        document_id="doc-001",
        section_index=1,
        student_name="Jane Doe",
        grade="A-",
        comment_text="Jane Doe (student ID: S12345678) can be reached at jane.doe@school.edu. "
                     "She lives on Oak Street and her parent Michael can be contacted at 555-123-4567.",
    )


@pytest.fixture
def sample_comment_anonymized() -> StudentComment:
    """Create a StudentComment that has been anonymized."""
    return StudentComment(
        id="test-003",
        document_id="doc-001",
        section_index=2,
        student_name="Bob Wilson",
        grade="C",
        comment_text="Bob Wilson needs to improve his study habits.",
        anonymized_text="[STUDENT] needs to improve his study habits.",
        anonymization_mappings=[
            AnonymizationMapping(
                original="Bob Wilson",
                placeholder="[STUDENT]",
                entity_type="PERSON",
                start_pos=0,
                end_pos=10,
            )
        ],
    )


@pytest.fixture
def sample_comment_with_grammar_issues() -> StudentComment:
    """Create a StudentComment with grammar issues detected."""
    return StudentComment(
        id="test-004",
        document_id="doc-001",
        section_index=3,
        student_name="Alice Brown",
        grade="B",
        comment_text="Alice have been working hard on there assignments.",
        grammar_issues=[
            GrammarIssue(
                rule_id="SUBJECT_VERB_AGREEMENT",
                message="The verb 'have' does not agree with the subject 'Alice'.",
                context="Alice have been working",
                offset=6,
                length=4,
                suggestions=["has"],
                confidence=0.95,
            ),
            GrammarIssue(
                rule_id="THEIR_THERE",
                message="Did you mean 'their'?",
                context="on there assignments",
                offset=32,
                length=5,
                suggestions=["their"],
                confidence=0.90,
            ),
        ],
    )


@pytest.fixture
def sample_comment_with_analysis() -> StudentComment:
    """Create a fully analyzed StudentComment with all results populated."""
    return StudentComment(
        id="test-005",
        document_id="doc-002",
        section_index=0,
        student_name="Emily Chen",
        grade="A",
        comment_text="Emily demonstrates exceptional analytical skills.",
        anonymized_text="[STUDENT] demonstrates exceptional analytical skills.",
        anonymization_mappings=[
            AnonymizationMapping(
                original="Emily",
                placeholder="[STUDENT]",
                entity_type="PERSON",
                start_pos=0,
                end_pos=5,
            )
        ],
        grammar_issues=[],
        name_match=NameMatch(
            extracted_name="Emily",
            expected_name="Emily Chen",
            match_score=0.92,
            is_match=True,
            confidence=ConfidenceLevel.HIGH,
            extraction_method="ner",
        ),
        completeness=CompletenessResult(
            is_complete=True,
            score=0.85,
            confidence=ConfidenceLevel.HIGH,
            specificity_score=0.90,
            actionability_score=0.80,
            evidence_score=0.85,
            length_score=0.75,
            tone_score=0.95,
            missing_elements=[],
            explanation="Comment provides specific feedback with appropriate tone.",
        ),
        consistency=ConsistencyResult(
            is_consistent=True,
            confidence=ConfidenceLevel.HIGH,
            grade_sentiment="positive",
            comment_sentiment="positive",
            explanation="Grade A aligns with positive comment about exceptional skills.",
            conflicting_phrases=[],
        ),
        needs_review=False,
        review_reasons=[],
        review_status=ReviewStatus.PENDING,
    )


@pytest.fixture
def sample_comment_needs_review() -> StudentComment:
    """Create a StudentComment flagged for human review."""
    return StudentComment(
        id="test-006",
        document_id="doc-002",
        section_index=1,
        student_name="Tom Johnson",
        grade="A",
        comment_text="Tom has struggled this term and needs improvement in all areas.",
        anonymized_text="[STUDENT] has struggled this term and needs improvement in all areas.",
        anonymization_mappings=[
            AnonymizationMapping(
                original="Tom",
                placeholder="[STUDENT]",
                entity_type="PERSON",
                start_pos=0,
                end_pos=3,
            )
        ],
        name_match=NameMatch(
            extracted_name="Tom",
            expected_name="Tom Johnson",
            match_score=0.88,
            is_match=True,
            confidence=ConfidenceLevel.HIGH,
            extraction_method="ner",
        ),
        consistency=ConsistencyResult(
            is_consistent=False,
            confidence=ConfidenceLevel.HIGH,
            grade_sentiment="positive",
            comment_sentiment="negative",
            explanation="Grade A is inconsistent with negative comment about struggling.",
            conflicting_phrases=["struggled", "needs improvement in all areas"],
        ),
        needs_review=True,
        review_reasons=["Grade-comment inconsistency detected"],
        review_status=ReviewStatus.PENDING,
    )


# ============================================================================
# Document Fixtures
# ============================================================================


@pytest.fixture
def sample_document(sample_comment: StudentComment) -> TeacherDocument:
    """Create a minimal sample TeacherDocument."""
    return TeacherDocument(
        id="doc-001",
        teacher_name="Mrs. Thompson",
        class_name="Math 101",
        term="Fall 2025",
        source_path="/path/to/doc.docx",
        comments=[sample_comment],
    )


@pytest.fixture
def sample_document_with_multiple_comments(
    sample_comment: StudentComment,
    sample_comment_with_pii: StudentComment,
    sample_comment_anonymized: StudentComment,
) -> TeacherDocument:
    """Create a TeacherDocument with multiple comments."""
    return TeacherDocument(
        id="doc-002",
        teacher_name="Mr. Garcia",
        class_name="English 201",
        term="Fall 2025",
        source_path="/path/to/english_doc.docx",
        comments=[
            sample_comment,
            sample_comment_with_pii,
            sample_comment_anonymized,
        ],
    )


# ============================================================================
# Roster Fixtures
# ============================================================================


@pytest.fixture
def mock_roster() -> ClassRoster:
    """Create a mock ClassRoster for testing name matching."""
    return ClassRoster(
        class_id="class-001",
        class_name="Math 101",
        teacher_name="Mrs. Thompson",
        term="Fall 2025",
        students=[
            RosterEntry(
                student_id="S10000001",
                first_name="John",
                last_name="Smith",
                preferred_name=None,
            ),
            RosterEntry(
                student_id="S10000002",
                first_name="Jane",
                last_name="Doe",
                preferred_name="Jenny",
            ),
            RosterEntry(
                student_id="S10000003",
                first_name="Robert",
                last_name="Wilson",
                preferred_name="Bob",
            ),
            RosterEntry(
                student_id="S10000004",
                first_name="Alice",
                last_name="Brown",
                preferred_name=None,
            ),
            RosterEntry(
                student_id="S10000005",
                first_name="Emily",
                last_name="Chen",
                preferred_name=None,
            ),
            RosterEntry(
                student_id="S10000006",
                first_name="Michael",
                last_name="O'Brien",
                preferred_name="Mike",
            ),
            RosterEntry(
                student_id="S10000007",
                first_name="Sarah",
                last_name="Smith-Jones",
                preferred_name=None,
            ),
            RosterEntry(
                student_id="S10000008",
                first_name="Thomas",
                last_name="Johnson",
                preferred_name="Tom",
            ),
        ],
    )


@pytest.fixture
def mock_roster_names(mock_roster: ClassRoster) -> List[str]:
    """Get all name variants from mock roster."""
    return mock_roster.get_all_names()


# ============================================================================
# Data Loading Utilities
# ============================================================================


@pytest.fixture
def load_sample_comments(sample_comments_path: Path) -> List[dict]:
    """Load sample comments from JSON fixture file."""
    if sample_comments_path.exists():
        with open(sample_comments_path) as f:
            return json.load(f)
    return []


# ============================================================================
# Mock API Fixtures
# ============================================================================


@pytest.fixture
def mock_anthropic_response():
    """Create a mock Anthropic API response for semantic analysis tests."""
    return {
        "is_complete": True,
        "score": 0.85,
        "specificity_score": 0.90,
        "actionability_score": 0.80,
        "evidence_score": 0.85,
        "length_score": 0.75,
        "tone_score": 0.95,
        "missing_elements": [],
        "explanation": "The comment provides specific, actionable feedback.",
    }


@pytest.fixture
def mock_consistency_response():
    """Create a mock consistency analysis response."""
    return {
        "is_consistent": True,
        "grade_sentiment": "positive",
        "comment_sentiment": "positive",
        "explanation": "Grade and comment are well aligned.",
        "conflicting_phrases": [],
    }
