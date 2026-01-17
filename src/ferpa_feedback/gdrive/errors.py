"""Custom exception classes for Google Drive integration.

This module defines custom exceptions for handling various error conditions
that can occur during Google Drive API operations.
"""

from typing import Optional


class DriveAccessError(Exception):
    """Raised when unable to access a Google Drive resource.

    This typically occurs when:
    - The folder/file ID is invalid
    - The service account doesn't have permission to access the resource
    - The resource has been deleted or moved

    To resolve: Ensure the folder is shared with the service account email.
    """

    def __init__(self, message: str, resource_id: Optional[str] = None) -> None:
        self.resource_id = resource_id
        super().__init__(message)


class DriveExportError(Exception):
    """Raised when unable to export a Google Drive document.

    This typically occurs when:
    - The document exceeds the 10MB export limit
    - The export format is not supported
    - The document is corrupted or in an unsupported state
    """

    def __init__(
        self, message: str, file_id: Optional[str] = None, mime_type: Optional[str] = None
    ) -> None:
        self.file_id = file_id
        self.mime_type = mime_type
        super().__init__(message)


class DiscoveryTimeoutError(Exception):
    """Raised when folder discovery takes too long.

    This typically occurs when:
    - The folder hierarchy is very deep or wide
    - Network latency is high
    - Rate limits are being hit
    """

    def __init__(self, message: str, timeout_seconds: Optional[float] = None) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(message)


class DownloadError(Exception):
    """Raised when unable to download a file from Google Drive.

    This typically occurs when:
    - Network issues during download
    - File was modified/deleted during download
    - Insufficient permissions for the specific file
    """

    def __init__(self, message: str, file_id: Optional[str] = None) -> None:
        self.file_id = file_id
        super().__init__(message)


class UploadError(Exception):
    """Raised when unable to upload a file to Google Drive.

    This typically occurs when:
    - No write permission on the target folder
    - Quota exceeded
    - Network issues during upload
    """

    def __init__(
        self, message: str, folder_id: Optional[str] = None, file_name: Optional[str] = None
    ) -> None:
        self.folder_id = folder_id
        self.file_name = file_name
        super().__init__(message)


class FileTooLargeError(Exception):
    """Raised when a file exceeds size limits for processing.

    Google Docs export is limited to 10MB. This error is raised when
    a document exceeds this limit.
    """

    def __init__(
        self, message: str, file_id: Optional[str] = None, size_bytes: Optional[int] = None
    ) -> None:
        self.file_id = file_id
        self.size_bytes = size_bytes
        super().__init__(message)


class AuthenticationError(Exception):
    """Raised when authentication with Google Drive API fails.

    This typically occurs when:
    - OAuth2 credentials are invalid or expired
    - Service account key is invalid
    - Workload Identity Federation is misconfigured
    - Required scopes are not authorized
    """

    def __init__(self, message: str, auth_method: Optional[str] = None) -> None:
        self.auth_method = auth_method
        super().__init__(message)
