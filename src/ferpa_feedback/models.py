"""
Core data models for the FERPA-compliant feedback system.

All data structures are defined here to ensure consistent typing
across the pipeline stages.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ConfidenceLevel(str, Enum):
    """Confidence levels for pipeline decisions."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ReviewStatus(str, Enum):
    """Status of a flagged item in the review queue."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class GrammarIssue(BaseModel):
    """A grammar, spelling, or punctuation issue detected by LanguageTool."""
    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(description="LanguageTool rule identifier")
    message: str = Field(description="Human-readable error description")
    context: str = Field(description="Text surrounding the error")
    offset: int = Field(description="Character offset in original text")
    length: int = Field(description="Length of the erroneous text")
    suggestions: list[str] = Field(default_factory=list, description="Suggested corrections")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")


class NameMatch(BaseModel):
    """Result of matching an extracted name to the expected student."""
    model_config = ConfigDict(frozen=True)

    extracted_name: str = Field(description="Name found in the comment text")
    expected_name: str = Field(description="Expected student name for this section")
    match_score: float = Field(ge=0.0, le=1.0, description="Fuzzy match similarity")
    is_match: bool = Field(description="Whether the names match sufficiently")
    confidence: ConfidenceLevel = Field(description="Confidence in the match result")
    extraction_method: str = Field(description="How the name was extracted (ner, roster, pronoun)")


class AnonymizationMapping(BaseModel):
    """Bidirectional mapping for anonymization/de-anonymization."""
    model_config = ConfigDict(frozen=True)

    original: str = Field(description="Original PII value")
    placeholder: str = Field(description="Anonymized placeholder")
    entity_type: str = Field(description="Type of entity (PERSON, EMAIL, etc.)")
    start_pos: int = Field(description="Start position in original text")
    end_pos: int = Field(description="End position in original text")


class CompletenessResult(BaseModel):
    """Result of the completeness analysis for a comment."""
    model_config = ConfigDict(frozen=True)

    is_complete: bool = Field(description="Whether the comment is considered complete")
    score: float = Field(ge=0.0, le=1.0, description="Overall completeness score")
    confidence: ConfidenceLevel = Field(description="Confidence in the assessment")

    # Individual criterion scores
    specificity_score: float = Field(ge=0.0, le=1.0)
    actionability_score: float = Field(ge=0.0, le=1.0)
    evidence_score: float = Field(ge=0.0, le=1.0)
    length_score: float = Field(ge=0.0, le=1.0)
    tone_score: float = Field(ge=0.0, le=1.0)

    missing_elements: list[str] = Field(default_factory=list, description="What would make it complete")
    explanation: str = Field(default="", description="LLM explanation of the assessment")


class ConsistencyResult(BaseModel):
    """Result of the grade-comment consistency check."""
    model_config = ConfigDict(frozen=True)

    is_consistent: bool = Field(description="Whether grade and comment align")
    confidence: ConfidenceLevel = Field(description="Confidence in the assessment")
    grade_sentiment: str = Field(description="Expected sentiment based on grade")
    comment_sentiment: str = Field(description="Detected sentiment of comment")
    explanation: str = Field(default="", description="LLM explanation of the assessment")

    # Specific issues found
    conflicting_phrases: list[str] = Field(default_factory=list)


class StudentComment(BaseModel):
    """A single student comment record with all analysis results."""
    model_config = ConfigDict(frozen=True)

    # Identifiers
    id: str = Field(description="Unique identifier for this comment")
    document_id: str = Field(description="Source document identifier")
    section_index: int = Field(description="Position in the document")

    # Raw data (PII - handle carefully)
    student_name: str = Field(description="Expected student name from section header")
    grade: str = Field(description="Grade assigned to the student")
    comment_text: str = Field(description="Original comment text")

    # Anonymized version (safe for external API)
    anonymized_text: str | None = Field(default=None, description="PII-redacted comment")
    anonymization_mappings: list[AnonymizationMapping] = Field(default_factory=list)

    # Analysis results
    grammar_issues: list[GrammarIssue] = Field(default_factory=list)
    name_match: NameMatch | None = Field(default=None)
    completeness: CompletenessResult | None = Field(default=None)
    consistency: ConsistencyResult | None = Field(default=None)

    # Review tracking
    needs_review: bool = Field(default=False)
    review_reasons: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = Field(default=ReviewStatus.PENDING)
    reviewer_notes: str = Field(default="")


class TeacherDocument(BaseModel):
    """A complete teacher document containing multiple student comments."""

    # Metadata
    id: str = Field(description="Document identifier")
    teacher_name: str = Field(description="Teacher who created the document")
    class_name: str = Field(description="Class/course name")
    term: str = Field(description="Academic term")

    # Processing metadata
    source_path: str = Field(description="Original file path or Google Drive ID")
    processed_at: datetime | None = Field(default=None)
    processing_duration_seconds: float | None = Field(default=None)

    # Comments
    comments: list[StudentComment] = Field(default_factory=list)

    # Summary statistics
    @property
    def total_comments(self) -> int:
        return len(self.comments)

    @property
    def grammar_issues_count(self) -> int:
        return sum(len(c.grammar_issues) for c in self.comments)

    @property
    def name_mismatches_count(self) -> int:
        return sum(1 for c in self.comments if c.name_match and not c.name_match.is_match)

    @property
    def incomplete_comments_count(self) -> int:
        return sum(1 for c in self.comments if c.completeness and not c.completeness.is_complete)

    @property
    def inconsistent_grades_count(self) -> int:
        return sum(1 for c in self.comments if c.consistency and not c.consistency.is_consistent)

    @property
    def needs_review_count(self) -> int:
        return sum(1 for c in self.comments if c.needs_review)


class ProcessingResult(BaseModel):
    """Overall result of processing a batch of documents."""

    # Batch metadata
    batch_id: str
    started_at: datetime
    completed_at: datetime | None = None

    # Documents processed
    documents: list[TeacherDocument] = Field(default_factory=list)

    # Aggregate statistics
    @property
    def total_documents(self) -> int:
        return len(self.documents)

    @property
    def total_comments(self) -> int:
        return sum(d.total_comments for d in self.documents)

    @property
    def total_grammar_issues(self) -> int:
        return sum(d.grammar_issues_count for d in self.documents)

    @property
    def total_name_mismatches(self) -> int:
        return sum(d.name_mismatches_count for d in self.documents)

    @property
    def total_incomplete(self) -> int:
        return sum(d.incomplete_comments_count for d in self.documents)

    @property
    def total_inconsistent(self) -> int:
        return sum(d.inconsistent_grades_count for d in self.documents)

    @property
    def total_needing_review(self) -> int:
        return sum(d.needs_review_count for d in self.documents)


class RosterEntry(BaseModel):
    """A single student in a class roster."""
    model_config = ConfigDict(frozen=True)

    student_id: str
    first_name: str
    last_name: str
    preferred_name: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        if self.preferred_name:
            return f"{self.preferred_name} {self.last_name}"
        return self.full_name

    @property
    def all_name_variants(self) -> list[str]:
        """All possible ways this student's name might appear."""
        variants = [
            self.full_name,
            self.first_name,
            self.last_name,
            f"{self.last_name}, {self.first_name}",
        ]
        if self.preferred_name:
            variants.extend([
                self.preferred_name,
                f"{self.preferred_name} {self.last_name}",
            ])
        return variants


class ClassRoster(BaseModel):
    """Complete roster for a class."""

    class_id: str
    class_name: str
    teacher_name: str
    term: str
    students: list[RosterEntry] = Field(default_factory=list)

    def get_all_names(self) -> list[str]:
        """Get all possible student name variants for matching."""
        names = []
        for student in self.students:
            names.extend(student.all_name_variants)
        return names

    def find_student(self, name: str) -> RosterEntry | None:
        """Find a student by any name variant."""
        name_lower = name.lower().strip()
        for student in self.students:
            if any(v.lower() == name_lower for v in student.all_name_variants):
                return student
        return None
