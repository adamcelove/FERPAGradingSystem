"""Google Drive result uploader for the FERPA feedback pipeline.

This module provides functionality to upload processing results (grammar reports,
anonymized outputs) back to Google Drive folders.

Example:
    from ferpa_feedback.gdrive.uploader import ResultUploader, UploadMode

    uploader = ResultUploader(service)
    result = uploader.upload_grammar_report(report_content, original_doc, folder_id)
"""

import time
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from typing import Any, Optional

from ferpa_feedback.gdrive.discovery import DriveDocument
from ferpa_feedback.gdrive.errors import UploadError


class UploadMode(Enum):
    """How to handle existing files with the same name.

    Attributes:
        OVERWRITE: Replace existing file with new content.
        VERSION: Append timestamp to filename to create new version.
        SKIP: Skip upload if file already exists.
    """

    OVERWRITE = "overwrite"
    VERSION = "version"
    SKIP = "skip"


@dataclass
class UploadResult:
    """Result of an upload operation.

    Attributes:
        file_id: Google Drive file ID of the uploaded file.
        file_name: Name of the uploaded file.
        parent_folder_id: ID of the parent folder.
        success: Whether the upload was successful.
        error: Error message if upload failed.
        upload_time_seconds: Time taken to upload the file.
    """

    file_id: str
    file_name: str
    parent_folder_id: str
    success: bool
    error: Optional[str] = None
    upload_time_seconds: float = 0.0


class ResultUploader:
    """Uploads processing results to Google Drive.

    This class handles uploading grammar reports and anonymized outputs
    back to Google Drive folders, with support for different upload modes
    and retry logic.

    Example:
        uploader = ResultUploader(service)

        # Upload grammar report
        result = uploader.upload_grammar_report(
            report_content="Grammar issues found...",
            original_doc=drive_document,
            folder_id="folder123",
        )

        # Upload anonymized output
        result = uploader.upload_anonymized_output(
            content="Anonymized content...",
            original_doc=drive_document,
            output_folder_id="output_folder_id",
        )
    """

    # MIME type for plain text files
    TEXT_MIME = "text/plain"

    # MIME type for folders
    FOLDER_MIME = "application/vnd.google-apps.folder"

    # Default output folder name
    DEFAULT_OUTPUT_FOLDER = "pipeline_outputs"

    def __init__(
        self,
        service: Any,
        rate_limiter: Optional[Any] = None,
        upload_mode: UploadMode = UploadMode.OVERWRITE,
        max_retries: int = 3,
    ) -> None:
        """Initialize the result uploader.

        Args:
            service: Authenticated Google Drive API service.
            rate_limiter: Optional rate limiter for API calls.
            upload_mode: How to handle existing files (OVERWRITE for POC).
            max_retries: Number of retry attempts for failed uploads.
        """
        self._service = service
        self._rate_limiter = rate_limiter
        self._upload_mode = upload_mode
        self._max_retries = max_retries

    def upload_grammar_report(
        self,
        report_content: str,
        original_doc: DriveDocument,
        folder_id: str,
    ) -> UploadResult:
        """Upload grammar report to source folder.

        Creates a text file with the grammar report, named based on the
        original document name with "_grammar_report.txt" suffix.

        Args:
            report_content: Grammar report text content.
            original_doc: Source document metadata.
            folder_id: Target folder ID for the report.

        Returns:
            UploadResult with file ID and status.

        Raises:
            UploadError: If upload fails after all retries.
        """
        # Generate file name based on original document
        base_name = original_doc.name
        # Remove extension if present
        if "." in base_name:
            base_name = base_name.rsplit(".", 1)[0]
        file_name = f"{base_name}_grammar_report.txt"

        return self._upload_text_file(
            content=report_content,
            file_name=file_name,
            folder_id=folder_id,
        )

    def upload_anonymized_output(
        self,
        content: str,
        original_doc: DriveDocument,
        output_folder_id: str,
    ) -> UploadResult:
        """Upload anonymized document output.

        Creates a text file with the anonymized content, named based on
        the original document name with "_anonymized.txt" suffix.

        Args:
            content: Anonymized output text content.
            original_doc: Source document metadata.
            output_folder_id: Target output folder ID.

        Returns:
            UploadResult with file ID and status.

        Raises:
            UploadError: If upload fails after all retries.
        """
        # Generate file name based on original document
        base_name = original_doc.name
        # Remove extension if present
        if "." in base_name:
            base_name = base_name.rsplit(".", 1)[0]
        file_name = f"{base_name}_anonymized.txt"

        return self._upload_text_file(
            content=content,
            file_name=file_name,
            folder_id=output_folder_id,
        )

    def ensure_output_folder(
        self,
        parent_folder_id: str,
        folder_name: str = "pipeline_outputs",
    ) -> str:
        """Create output folder if it doesn't exist.

        Checks if a folder with the given name exists in the parent folder.
        If not, creates it. Returns the folder ID in either case.

        Args:
            parent_folder_id: Parent folder ID where output folder should be.
            folder_name: Name for the output folder.

        Returns:
            Output folder ID (existing or newly created).

        Raises:
            UploadError: If folder creation fails.
        """
        # Apply rate limiting if configured
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            # Search for existing folder with this name
            query = (
                f"'{parent_folder_id}' in parents and "
                f"name = '{folder_name}' and "
                f"mimeType = '{self.FOLDER_MIME}' and "
                "trashed = false"
            )

            response = (
                self._service.files()
                .list(q=query, fields="files(id,name)", pageSize=1)
                .execute()
            )

            files = response.get("files", [])
            if files:
                # Folder exists, return its ID
                return str(files[0]["id"])

            # Folder doesn't exist, create it
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            file_metadata = {
                "name": folder_name,
                "mimeType": self.FOLDER_MIME,
                "parents": [parent_folder_id],
            }

            folder = (
                self._service.files()
                .create(body=file_metadata, fields="id")
                .execute()
            )

            return str(folder["id"])

        except Exception as e:
            raise UploadError(
                f"Failed to create output folder '{folder_name}': {e}",
                folder_id=parent_folder_id,
                file_name=folder_name,
            ) from e

    def _upload_text_file(
        self,
        content: str,
        file_name: str,
        folder_id: str,
    ) -> UploadResult:
        """Upload a text file to Google Drive with retry logic.

        Args:
            content: Text content to upload.
            file_name: Name for the uploaded file.
            folder_id: Target folder ID.

        Returns:
            UploadResult with file ID and status.

        Raises:
            UploadError: If upload fails after all retries.
        """
        start_time = time.time()
        last_error: Optional[Exception] = None

        # For POC, only implement OVERWRITE mode
        # VERSION and SKIP modes will be added in Phase 2

        for attempt in range(self._max_retries):
            try:
                # Apply rate limiting if configured
                if self._rate_limiter is not None:
                    self._rate_limiter.acquire()

                # Check for existing file with same name (for OVERWRITE mode)
                existing_file_id = self._find_existing_file(file_name, folder_id)

                if existing_file_id is not None:
                    # OVERWRITE: Update existing file
                    file_id = self._update_file(existing_file_id, content)
                else:
                    # Create new file
                    file_id = self._create_file(content, file_name, folder_id)

                upload_time = time.time() - start_time

                return UploadResult(
                    file_id=file_id,
                    file_name=file_name,
                    parent_folder_id=folder_id,
                    success=True,
                    upload_time_seconds=upload_time,
                )

            except Exception as e:
                last_error = e
                # Log retry attempt (would use structlog in production)
                if attempt < self._max_retries - 1:
                    # Basic backoff: wait before retry
                    time.sleep(1)
                    continue

        # All retries exhausted
        upload_time = time.time() - start_time
        error_msg = f"Failed to upload '{file_name}' after {self._max_retries} attempts: {last_error}"

        return UploadResult(
            file_id="",
            file_name=file_name,
            parent_folder_id=folder_id,
            success=False,
            error=error_msg,
            upload_time_seconds=upload_time,
        )

    def _find_existing_file(
        self,
        file_name: str,
        folder_id: str,
    ) -> Optional[str]:
        """Find an existing file with the given name in the folder.

        Args:
            file_name: Name of the file to find.
            folder_id: Folder to search in.

        Returns:
            File ID if found, None otherwise.
        """
        try:
            query = (
                f"'{folder_id}' in parents and "
                f"name = '{file_name}' and "
                "trashed = false"
            )

            response = (
                self._service.files()
                .list(q=query, fields="files(id)", pageSize=1)
                .execute()
            )

            files = response.get("files", [])
            if files:
                return str(files[0]["id"])
            return None

        except Exception:
            # If search fails, assume file doesn't exist
            return None

    def _create_file(
        self,
        content: str,
        file_name: str,
        folder_id: str,
    ) -> str:
        """Create a new file in Google Drive.

        Args:
            content: Text content for the file.
            file_name: Name for the new file.
            folder_id: Parent folder ID.

        Returns:
            ID of the created file.

        Raises:
            Exception: If file creation fails.
        """
        from googleapiclient.http import MediaIoBaseUpload  # type: ignore[import-untyped]

        file_metadata = {
            "name": file_name,
            "parents": [folder_id],
        }

        # Convert content to BytesIO
        content_bytes = BytesIO(content.encode("utf-8"))

        media = MediaIoBaseUpload(
            content_bytes,
            mimetype=self.TEXT_MIME,
            resumable=True,
        )

        file_result = (
            self._service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        return str(file_result["id"])

    def _update_file(
        self,
        file_id: str,
        content: str,
    ) -> str:
        """Update an existing file's content.

        Args:
            file_id: ID of the file to update.
            content: New text content.

        Returns:
            ID of the updated file.

        Raises:
            Exception: If file update fails.
        """
        from googleapiclient.http import MediaIoBaseUpload  # type: ignore[import-untyped]

        # Convert content to BytesIO
        content_bytes = BytesIO(content.encode("utf-8"))

        media = MediaIoBaseUpload(
            content_bytes,
            mimetype=self.TEXT_MIME,
            resumable=True,
        )

        file_result = (
            self._service.files()
            .update(fileId=file_id, media_body=media, fields="id")
            .execute()
        )

        return str(file_result["id"])
