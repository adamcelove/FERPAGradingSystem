"""
Stage 5: Human Review Queue

Provides a review workflow for flagged comments that need human inspection.
Comments are displayed with de-anonymized text for authorized reviewers only.

Key features:
- In-memory queue for POC (no persistence)
- De-anonymization for human review display
- Accept/reject/modify workflow
- Export of approved comments

This stage is 100% local - all PII handling stays on-premise.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, TYPE_CHECKING
import json

import structlog
from pydantic import BaseModel, Field

from ferpa_feedback.models import (
    ReviewStatus,
    StudentComment,
    TeacherDocument,
)
from ferpa_feedback.stage_3_anonymize import Anonymizer

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger()


class ReviewItem(BaseModel):
    """A comment queued for review with de-anonymized display."""

    comment_id: str = Field(description="Unique identifier for the comment")
    document_id: str = Field(description="Source document identifier")
    student_name: str = Field(description="De-anonymized student name for reviewer")
    grade: str = Field(description="Grade assigned to the student")

    # Display versions
    original_text: str = Field(description="Original with PII (for authorized reviewer only)")
    anonymized_text: str = Field(description="For reference")

    # Analysis results
    grammar_issues_count: int = Field(default=0, description="Number of grammar issues")
    name_match_issues: List[str] = Field(default_factory=list, description="Name matching issues")
    completeness_score: Optional[float] = Field(default=None, description="Completeness score if available")
    consistency_issues: List[str] = Field(default_factory=list, description="Consistency issues found")

    # Review workflow
    review_reasons: List[str] = Field(default_factory=list, description="Why this needs review")
    status: ReviewStatus = Field(default=ReviewStatus.PENDING, description="Current review status")
    reviewer_id: Optional[str] = Field(default=None, description="ID of reviewer")
    reviewed_at: Optional[datetime] = Field(default=None, description="When reviewed")
    reviewer_notes: str = Field(default="", description="Notes from reviewer")


class DeAnonymizer:
    """
    Restores original PII for human review.

    CRITICAL: Only use for authorized human review.
    This class should never be used before data leaves
    the local system.
    """

    def __init__(self, anonymizer: Optional[Anonymizer] = None):
        """
        Initialize de-anonymizer.

        Args:
            anonymizer: The Anonymizer instance with mappings.
                       If None, will use mappings from comment.
        """
        self.anonymizer = anonymizer

    def restore(self, comment: StudentComment) -> str:
        """
        Restore original text from anonymized version.

        CRITICAL: Only use for authorized human review.

        Args:
            comment: StudentComment with anonymized text and mappings

        Returns:
            De-anonymized text with original PII restored
        """
        # If no anonymized text, return original
        if not comment.anonymized_text:
            return comment.comment_text

        # If we have an anonymizer with mappings, use it
        if self.anonymizer:
            return self.anonymizer.deanonymize(comment.anonymized_text)

        # Otherwise, use the comment's own mappings
        result = comment.anonymized_text
        for mapping in comment.anonymization_mappings:
            result = result.replace(mapping.placeholder, mapping.original)

        return result

    def restore_from_mappings(
        self,
        anonymized_text: str,
        mappings: List[dict[str, str]],
    ) -> str:
        """
        Restore text using explicit mappings.

        Args:
            anonymized_text: Text with placeholders
            mappings: List of placeholder -> original mappings

        Returns:
            De-anonymized text
        """
        result = anonymized_text
        for mapping in mappings:
            placeholder = mapping.get("placeholder", "")
            original = mapping.get("original", "")
            if placeholder and original:
                result = result.replace(placeholder, original)
        return result


class ReviewQueue:
    """
    Manages the review queue for flagged comments.

    Uses in-memory storage for POC phase.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize review queue.

        Args:
            storage_path: Path to persist queue state (not used in POC).
        """
        self.storage_path = storage_path
        self._items: dict[str, ReviewItem] = {}
        self._de_anonymizer = DeAnonymizer()

        logger.info("review_queue_initialized")

    def add_document(self, document: TeacherDocument) -> int:
        """
        Add flagged comments from document to queue.

        Only comments with needs_review=True are added.

        Args:
            document: TeacherDocument with processed comments

        Returns:
            Number of items added to queue
        """
        added = 0

        for comment in document.comments:
            if not comment.needs_review:
                continue

            # Create review item
            item = self._create_review_item(comment, document.id)
            self._items[comment.id] = item
            added += 1

            logger.debug(
                "review_item_added",
                comment_id=comment.id,
                reasons=comment.review_reasons,
            )

        logger.info(
            "document_queued_for_review",
            doc_id=document.id,
            items_added=added,
            total_queue_size=len(self._items),
        )

        return added

    def _create_review_item(
        self,
        comment: StudentComment,
        document_id: str,
    ) -> ReviewItem:
        """Create a ReviewItem from a StudentComment."""
        # Extract consistency issues
        consistency_issues = []
        if comment.consistency and not comment.consistency.is_consistent:
            consistency_issues = comment.consistency.conflicting_phrases

        # Extract name match issues
        name_match_issues = []
        if comment.name_match and not comment.name_match.is_match:
            name_match_issues.append(
                f"Expected: {comment.name_match.expected_name}, "
                f"Found: {comment.name_match.extracted_name}"
            )

        # Get completeness score if available
        completeness_score = None
        if comment.completeness:
            completeness_score = comment.completeness.score

        # De-anonymize for reviewer display
        original_text = self._de_anonymizer.restore(comment)

        return ReviewItem(
            comment_id=comment.id,
            document_id=document_id,
            student_name=comment.student_name,
            grade=comment.grade,
            original_text=original_text,
            anonymized_text=comment.anonymized_text or comment.comment_text,
            grammar_issues_count=len(comment.grammar_issues),
            name_match_issues=name_match_issues,
            completeness_score=completeness_score,
            consistency_issues=consistency_issues,
            review_reasons=list(comment.review_reasons),
            status=comment.review_status,
            reviewer_notes=comment.reviewer_notes,
        )

    def get_pending(self, limit: int = 50) -> List[ReviewItem]:
        """
        Get pending review items.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of pending ReviewItems
        """
        pending = [
            item for item in self._items.values()
            if item.status == ReviewStatus.PENDING
        ]

        # Sort by comment_id for consistent ordering
        pending.sort(key=lambda x: x.comment_id)

        return pending[:limit]

    def get_by_id(self, comment_id: str) -> Optional[ReviewItem]:
        """
        Get a specific review item by ID.

        Args:
            comment_id: Comment identifier

        Returns:
            ReviewItem if found, None otherwise
        """
        return self._items.get(comment_id)

    def update_status(
        self,
        comment_id: str,
        status: ReviewStatus,
        reviewer_id: str,
        notes: str = "",
    ) -> None:
        """
        Update review status with audit logging.

        Args:
            comment_id: Comment to update
            status: New review status
            reviewer_id: ID of the reviewer
            notes: Optional notes from reviewer
        """
        if comment_id not in self._items:
            logger.warning(
                "review_update_failed",
                reason="Comment not found",
                comment_id=comment_id,
            )
            return

        item = self._items[comment_id]

        # Create updated item (ReviewItem is mutable for queue management)
        self._items[comment_id] = ReviewItem(
            **{
                **item.model_dump(exclude={"status", "reviewer_id", "reviewed_at", "reviewer_notes"}),
                "status": status,
                "reviewer_id": reviewer_id,
                "reviewed_at": datetime.now(),
                "reviewer_notes": notes,
            }
        )

        logger.info(
            "review_status_updated",
            comment_id=comment_id,
            old_status=item.status.value,
            new_status=status.value,
            reviewer_id=reviewer_id,
        )

    def export_approved(self, format: str = "json") -> str:
        """
        Export approved comments.

        Args:
            format: Export format ("json" supported in POC)

        Returns:
            Exported data as string
        """
        approved = [
            item for item in self._items.values()
            if item.status == ReviewStatus.APPROVED
        ]

        if format == "json":
            data = [item.model_dump(mode="json") for item in approved]
            return json.dumps(data, indent=2, default=str)

        logger.warning(
            "export_format_not_supported",
            format=format,
            supported=["json"],
        )
        return "[]"

    def get_statistics(self) -> dict[str, int]:
        """
        Get queue statistics.

        Returns:
            Dictionary with queue statistics
        """
        total = len(self._items)
        pending = sum(1 for item in self._items.values() if item.status == ReviewStatus.PENDING)
        approved = sum(1 for item in self._items.values() if item.status == ReviewStatus.APPROVED)
        rejected = sum(1 for item in self._items.values() if item.status == ReviewStatus.REJECTED)
        modified = sum(1 for item in self._items.values() if item.status == ReviewStatus.MODIFIED)

        return {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "modified": modified,
        }


class ReviewProcessor:
    """
    Processes documents for human review.

    Orchestrates adding documents to the review queue and
    managing the review workflow.
    """

    def __init__(self, queue: ReviewQueue):
        """
        Initialize review processor.

        Args:
            queue: ReviewQueue instance
        """
        self.queue = queue

    def process_document(self, document: TeacherDocument) -> int:
        """
        Process a document and add flagged comments to review queue.

        Args:
            document: TeacherDocument to process

        Returns:
            Number of comments added to review queue
        """
        return self.queue.add_document(document)


# Factory function
def create_review_processor(
    storage_path: Optional[Path] = None,
    config: Optional[dict[str, Any]] = None,
) -> ReviewQueue:
    """
    Factory function for Stage 5.

    Creates and returns a ReviewQueue instance.

    Args:
        storage_path: Optional path for persistence (not used in POC)
        config: Optional configuration dictionary

    Returns:
        Configured ReviewQueue instance
    """
    config = config or {}

    queue = ReviewQueue(
        storage_path=storage_path or config.get("storage_path"),
    )

    logger.info(
        "review_processor_created",
        storage_path=str(storage_path) if storage_path else None,
    )

    return queue


def create_review_app(queue: ReviewQueue) -> "FastAPI":
    """
    Create FastAPI application for human review UI.

    Provides web endpoints for reviewing flagged comments, updating
    status, and exporting approved comments.

    Args:
        queue: ReviewQueue instance to serve

    Returns:
        FastAPI application instance

    Raises:
        ImportError: If FastAPI is not installed
    """
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError:
        raise ImportError(
            "Review UI requires FastAPI. Install with: pip install ferpa-feedback[review-ui]"
        )

    app = FastAPI(
        title="FERPA Comment Review",
        description="Human review interface for flagged student comments",
        version="0.1.0",
    )

    @app.get("/", response_class=HTMLResponse)  # type: ignore[untyped-decorator]
    async def review_list() -> HTMLResponse:
        """
        Display list of pending comments for review.

        Returns HTML page with review items.
        """
        items = queue.get_pending()
        stats = queue.get_statistics()

        # Build HTML response
        html_items = []
        for item in items:
            reasons_html = "".join(f"<li>{r}</li>" for r in item.review_reasons)
            html_items.append(f"""
            <div class="review-item" id="item-{item.comment_id}">
                <h3>Comment: {item.comment_id}</h3>
                <p><strong>Student:</strong> {item.student_name}</p>
                <p><strong>Grade:</strong> {item.grade}</p>
                <p><strong>Original Text:</strong> {item.original_text}</p>
                <p><strong>Anonymized:</strong> {item.anonymized_text}</p>
                <p><strong>Review Reasons:</strong></p>
                <ul>{reasons_html}</ul>
                <form action="/review/{item.comment_id}" method="post">
                    <label for="status">Status:</label>
                    <select name="status" id="status">
                        <option value="approved">Approve</option>
                        <option value="rejected">Reject</option>
                        <option value="modified">Needs Modification</option>
                    </select>
                    <label for="reviewer_id">Reviewer ID:</label>
                    <input type="text" name="reviewer_id" id="reviewer_id" required>
                    <label for="notes">Notes:</label>
                    <textarea name="notes" id="notes"></textarea>
                    <button type="submit">Submit Review</button>
                </form>
            </div>
            """)

        items_html = "".join(html_items) if html_items else "<p>No pending items for review.</p>"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>FERPA Comment Review</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .stats {{ background: #f0f0f0; padding: 10px; margin-bottom: 20px; }}
                .review-item {{ border: 1px solid #ccc; padding: 15px; margin: 10px 0; }}
                form {{ margin-top: 10px; }}
                label {{ display: block; margin-top: 5px; }}
                input, select, textarea {{ margin-bottom: 10px; width: 100%; max-width: 300px; }}
                button {{ background: #007bff; color: white; padding: 10px 20px; border: none; cursor: pointer; }}
            </style>
        </head>
        <body>
            <h1>FERPA Comment Review</h1>
            <div class="stats">
                <strong>Queue Statistics:</strong>
                Total: {stats['total']} |
                Pending: {stats['pending']} |
                Approved: {stats['approved']} |
                Rejected: {stats['rejected']} |
                Modified: {stats['modified']}
            </div>
            <h2>Pending Reviews</h2>
            {items_html}
            <p><a href="/export">Export Approved Comments (JSON)</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)

    @app.post("/review/{comment_id}")  # type: ignore[untyped-decorator]
    async def submit_review(
        comment_id: str,
        status: str = Query(..., description="Review status: approved, rejected, or modified"),
        reviewer_id: str = Query(..., description="ID of the reviewer"),
        notes: str = Query("", description="Optional reviewer notes"),
    ) -> JSONResponse:
        """
        Submit a review decision for a comment.

        Args:
            comment_id: ID of the comment being reviewed
            status: New review status (approved, rejected, modified)
            reviewer_id: ID of the reviewer submitting the decision
            notes: Optional notes from the reviewer

        Returns:
            JSON response with update confirmation
        """
        # Validate comment exists
        item = queue.get_by_id(comment_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")

        # Convert status string to ReviewStatus enum
        try:
            review_status = ReviewStatus(status.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Must be one of: approved, rejected, modified"
            )

        # Update the status
        queue.update_status(comment_id, review_status, reviewer_id, notes)

        logger.info(
            "review_submitted_via_ui",
            comment_id=comment_id,
            status=status,
            reviewer_id=reviewer_id,
        )

        return JSONResponse(
            content={
                "success": True,
                "comment_id": comment_id,
                "status": status,
                "message": f"Comment {comment_id} marked as {status}",
            }
        )

    @app.get("/export")  # type: ignore[untyped-decorator]
    async def export_approved(
        format: str = Query("json", description="Export format (json supported)"),
    ) -> JSONResponse:
        """
        Export approved comments.

        Args:
            format: Export format (currently only 'json' supported)

        Returns:
            JSON response with exported comments
        """
        export_data = queue.export_approved(format)

        logger.info(
            "export_requested_via_ui",
            format=format,
        )

        # Parse the JSON string back to return as proper JSON response
        try:
            data = json.loads(export_data)
            return JSONResponse(content={"approved_comments": data, "count": len(data)})
        except json.JSONDecodeError:
            return JSONResponse(
                content={"error": "Export failed", "raw_data": export_data},
                status_code=500,
            )

    return app
