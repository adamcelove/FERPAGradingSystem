"""Cloud Run HTTP handler for Google Drive processing.

This module provides a FastAPI application for processing Google Drive documents
in a serverless Cloud Run environment. It exposes HTTP endpoints for triggering
document processing and health checks.

The handler uses Workload Identity Federation for authentication when running
on GCP, falling back to OAuth2 for local development.

Example:
    # Run locally for testing
    uvicorn ferpa_feedback.gdrive.cloud_handler:app --reload

    # Or via python
    python -m ferpa_feedback.gdrive.cloud_handler
"""

import os
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ferpa_feedback.gdrive.auth import OAuth2Authenticator, WorkloadIdentityAuthenticator
from ferpa_feedback.gdrive.config import DriveConfig
from ferpa_feedback.gdrive.processor import DriveProcessor, ProcessingSummary
from ferpa_feedback.pipeline import FeedbackPipeline

logger = structlog.get_logger()

# FastAPI application
app = FastAPI(
    title="FERPA Feedback Pipeline - Google Drive Processor",
    description="Process teacher feedback documents from Google Drive",
    version="1.0.0",
)


class ProcessRequest(BaseModel):
    """Request model for document processing.

    Attributes:
        root_folder_id: Google Drive folder ID to process.
        target_patterns: Optional list of folder name patterns to filter.
        dry_run: If True, list files without processing.
        output_local_path: Optional local path for output (testing only).
    """

    root_folder_id: str = Field(
        ...,
        description="Google Drive folder ID to process",
        min_length=1,
    )
    target_patterns: Optional[List[str]] = Field(
        default=None,
        description="Folder name patterns to filter (e.g., 'September*')",
    )
    dry_run: bool = Field(
        default=False,
        description="If True, list files without processing",
    )
    output_local_path: Optional[str] = Field(
        default=None,
        description="Local path for output (testing only, ignored in production)",
    )


class ProcessResponse(BaseModel):
    """Response model for processing results.

    Attributes:
        success: Whether the processing completed without errors.
        started_at: When processing started.
        completed_at: When processing completed.
        duration_seconds: Total processing time in seconds.
        total_documents: Number of documents found.
        successful: Number of documents successfully processed.
        failed: Number of documents that failed.
        success_rate: Percentage of documents processed successfully.
        grammar_issues_found: Total grammar issues detected.
        pii_instances_replaced: Total PII instances anonymized.
        uploads_completed: Number of successful uploads.
        errors: List of error details.
        message: Summary message.
    """

    success: bool
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    total_documents: int
    successful: int
    failed: int
    success_rate: float
    grammar_issues_found: int
    pii_instances_replaced: int
    uploads_completed: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    message: str


class HealthResponse(BaseModel):
    """Response model for health check.

    Attributes:
        status: Health status (healthy, degraded, unhealthy).
        timestamp: Current timestamp.
        version: Application version.
        auth_method: Authentication method in use.
    """

    status: str
    timestamp: datetime
    version: str
    auth_method: str


def _get_authenticator() -> Any:
    """Get appropriate authenticator based on environment.

    Returns Workload Identity Federation when running on GCP (detected by
    presence of K_SERVICE environment variable), otherwise OAuth2 for
    local development.

    Returns:
        DriveAuthenticator instance.

    Raises:
        RuntimeError: If authentication configuration is invalid.
    """
    # Check if running on Cloud Run
    if os.environ.get("K_SERVICE"):
        # Use Workload Identity Federation on GCP
        logger.info("using_workload_identity_auth")
        config = DriveConfig()
        wif = config.auth.workload_identity

        if not all([wif.project_id, wif.pool_id, wif.provider_id, wif.service_account_email]):
            raise RuntimeError(
                "Workload Identity Federation not configured. "
                "Set all wif_* environment variables or configure in settings.yaml"
            )

        return WorkloadIdentityAuthenticator(
            project_id=wif.project_id,
            pool_id=wif.pool_id,
            provider_id=wif.provider_id,
            service_account_email=wif.service_account_email,
        )
    else:
        # Use OAuth2 for local development
        logger.info("using_oauth2_auth")
        from pathlib import Path

        client_secrets_path = Path(
            os.environ.get("GOOGLE_CLIENT_SECRETS", "client_secrets.json")
        )
        return OAuth2Authenticator(client_secrets_path=client_secrets_path)


def _create_processor() -> DriveProcessor:
    """Create and configure a DriveProcessor instance.

    Returns:
        Configured DriveProcessor.

    Raises:
        RuntimeError: If processor creation fails.
    """
    try:
        authenticator = _get_authenticator()
        pipeline = FeedbackPipeline()
        config = DriveConfig()

        return DriveProcessor(
            authenticator=authenticator,
            pipeline=pipeline,
            config=config,
        )
    except Exception as e:
        logger.error("processor_creation_failed", error=str(e))
        raise RuntimeError(f"Failed to create processor: {e}") from e


def _summary_to_response(summary: ProcessingSummary) -> ProcessResponse:
    """Convert ProcessingSummary to API response.

    Args:
        summary: Processing summary from DriveProcessor.

    Returns:
        ProcessResponse for API.
    """
    return ProcessResponse(
        success=summary.failed == 0,
        started_at=summary.started_at,
        completed_at=summary.completed_at,
        duration_seconds=summary.duration_seconds,
        total_documents=summary.total_documents,
        successful=summary.successful,
        failed=summary.failed,
        success_rate=summary.success_rate,
        grammar_issues_found=summary.grammar_issues_found,
        pii_instances_replaced=summary.pii_instances_replaced,
        uploads_completed=summary.uploads_completed,
        errors=summary.errors,
        message=_build_summary_message(summary),
    )


def _build_summary_message(summary: ProcessingSummary) -> str:
    """Build a human-readable summary message.

    Args:
        summary: Processing summary.

    Returns:
        Summary message string.
    """
    if summary.total_documents == 0:
        return "No documents found to process"

    if summary.failed == 0:
        return (
            f"Successfully processed {summary.successful} of {summary.total_documents} documents. "
            f"Found {summary.grammar_issues_found} grammar issues."
        )

    return (
        f"Processed {summary.successful} of {summary.total_documents} documents. "
        f"{summary.failed} failed. "
        f"Found {summary.grammar_issues_found} grammar issues."
    )


@app.post("/process", response_model=ProcessResponse)
async def process_documents(request: ProcessRequest) -> ProcessResponse:
    """Process documents from Google Drive.

    This endpoint triggers document processing for the specified folder.
    It discovers folder structure, downloads documents, processes them
    through the FERPA pipeline, and uploads results back to Drive.

    Args:
        request: Processing request with folder ID and options.

    Returns:
        ProcessResponse with processing statistics.

    Raises:
        HTTPException: If processing fails catastrophically.
    """
    logger.info(
        "process_request_received",
        root_folder_id=request.root_folder_id,
        target_patterns=request.target_patterns,
        dry_run=request.dry_run,
    )

    try:
        processor = _create_processor()

        summary = processor.process(
            root_folder_id=request.root_folder_id,
            target_patterns=request.target_patterns,
            dry_run=request.dry_run,
        )

        response = _summary_to_response(summary)

        logger.info(
            "process_request_completed",
            success=response.success,
            total_documents=response.total_documents,
            successful=response.successful,
            failed=response.failed,
            duration_seconds=response.duration_seconds,
        )

        return response

    except Exception as e:
        logger.error(
            "process_request_failed",
            error=str(e),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}",
        ) from e


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check service health.

    Returns basic health information about the service, including
    the authentication method being used.

    Returns:
        HealthResponse with health status.
    """
    # Determine auth method
    auth_method = "workload_identity_federation" if os.environ.get("K_SERVICE") else "oauth2"

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        version="1.0.0",
        auth_method=auth_method,
    )


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint with basic service information.

    Returns:
        Service information.
    """
    return {
        "service": "FERPA Feedback Pipeline - Google Drive Processor",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
