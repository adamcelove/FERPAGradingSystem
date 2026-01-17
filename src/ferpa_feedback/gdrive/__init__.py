"""Google Drive integration module for FERPA feedback pipeline.

This module provides integration with Google Drive for:
- Authenticating with Drive API (OAuth2 and Workload Identity Federation)
- Discovering folder structures and documents
- Downloading documents as BytesIO streams
- Uploading processing results back to Drive
- Orchestrating end-to-end document processing

Example:
    from ferpa_feedback.gdrive import (
        OAuth2Authenticator,
        DriveProcessor,
        DriveConfig,
    )

    # Authenticate
    auth = OAuth2Authenticator(client_secrets_path)

    # Configure pipeline
    from ferpa_feedback.pipeline import FeedbackPipeline
    pipeline = FeedbackPipeline()

    # Process documents
    processor = DriveProcessor(auth, pipeline, DriveConfig())
    summary = processor.process(
        root_folder_id="1abc123xyz",
        target_patterns=["September*"],
    )
    print(f"Processed {summary.successful} of {summary.total_documents} documents")
"""

# Authentication
from ferpa_feedback.gdrive.auth import (
    DriveAuthenticator,
    OAuth2Authenticator,
    WorkloadIdentityAuthenticator,
    create_authenticator,
)

# Configuration
from ferpa_feedback.gdrive.config import (
    AuthConfig,
    DriveConfig,
    OAuth2Config,
    ProcessingConfig,
    RateLimitConfig,
    UploadConfig,
    WorkloadIdentityConfig,
)

# Discovery
from ferpa_feedback.gdrive.discovery import (
    DriveDocument,
    FolderDiscovery,
    FolderMap,
    FolderMetadata,
    FolderNode,
)

# Downloader
from ferpa_feedback.gdrive.downloader import (
    DocumentDownloader,
    DownloadedDocument,
)

# Errors
from ferpa_feedback.gdrive.errors import (
    AuthenticationError,
    DiscoveryTimeoutError,
    DownloadError,
    DriveAccessError,
    DriveExportError,
    FileTooLargeError,
    UploadError,
)

# Processor
from ferpa_feedback.gdrive.processor import (
    DriveProcessor,
    ProcessingProgress,
    ProcessingSummary,
)

# Uploader
from ferpa_feedback.gdrive.uploader import (
    ResultUploader,
    UploadMode,
    UploadResult,
)

__all__ = [
    # Authentication
    "DriveAuthenticator",
    "OAuth2Authenticator",
    "WorkloadIdentityAuthenticator",
    "create_authenticator",
    # Configuration
    "DriveConfig",
    "AuthConfig",
    "OAuth2Config",
    "WorkloadIdentityConfig",
    "ProcessingConfig",
    "UploadConfig",
    "RateLimitConfig",
    # Discovery
    "FolderDiscovery",
    "FolderMap",
    "FolderNode",
    "DriveDocument",
    "FolderMetadata",
    # Downloader
    "DocumentDownloader",
    "DownloadedDocument",
    # Uploader
    "ResultUploader",
    "UploadResult",
    "UploadMode",
    # Processor
    "DriveProcessor",
    "ProcessingSummary",
    "ProcessingProgress",
    # Errors
    "DriveAccessError",
    "DriveExportError",
    "DiscoveryTimeoutError",
    "DownloadError",
    "UploadError",
    "FileTooLargeError",
    "AuthenticationError",
]
