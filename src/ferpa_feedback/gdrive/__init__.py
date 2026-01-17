"""Google Drive integration module for FERPA feedback pipeline.

This module provides integration with Google Drive for:
- Authenticating with Drive API (OAuth2 and Workload Identity Federation)
- Discovering folder structures and documents
- Downloading documents as BytesIO streams
- Uploading processing results back to Drive

Example:
    from ferpa_feedback.gdrive import DriveConfig, DriveAccessError

    config = DriveConfig()
    # Configure and use...
"""

from ferpa_feedback.gdrive.config import (
    AuthConfig,
    DriveConfig,
    OAuth2Config,
    ProcessingConfig,
    RateLimitConfig,
    UploadConfig,
    WorkloadIdentityConfig,
)
from ferpa_feedback.gdrive.errors import (
    AuthenticationError,
    DiscoveryTimeoutError,
    DownloadError,
    DriveAccessError,
    DriveExportError,
    FileTooLargeError,
    UploadError,
)

__all__ = [
    # Config classes
    "DriveConfig",
    "AuthConfig",
    "OAuth2Config",
    "WorkloadIdentityConfig",
    "ProcessingConfig",
    "UploadConfig",
    "RateLimitConfig",
    # Error classes
    "DriveAccessError",
    "DriveExportError",
    "DiscoveryTimeoutError",
    "DownloadError",
    "UploadError",
    "FileTooLargeError",
    "AuthenticationError",
]
