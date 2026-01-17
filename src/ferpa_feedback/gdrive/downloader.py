"""Google Drive document downloader with BytesIO streaming.

This module provides document downloading from Google Drive, exporting
Google Docs to .docx format and streaming content to in-memory BytesIO
objects (no disk writes).

Example:
    from ferpa_feedback.gdrive.downloader import DocumentDownloader

    downloader = DocumentDownloader(service)
    downloaded = downloader.download_document(drive_document)
    # downloaded.content is a BytesIO object ready for parsing
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, Iterator, List, Optional, Union

from ferpa_feedback.gdrive.discovery import DriveDocument
from ferpa_feedback.gdrive.errors import DownloadError, DriveExportError, FileTooLargeError


@dataclass
class DownloadedDocument:
    """A document downloaded from Google Drive.

    Attributes:
        drive_document: Original DriveDocument metadata.
        content: BytesIO stream containing the document content.
        export_mime_type: MIME type of the downloaded content.
        download_time_seconds: Time taken to download the document.
    """

    drive_document: DriveDocument
    content: BytesIO
    export_mime_type: str
    download_time_seconds: float


class DocumentDownloader:
    """Downloads documents from Google Drive as BytesIO streams.

    This class handles downloading both native Google Docs (by exporting
    to .docx) and regular .docx files (by direct download). All content
    is streamed to BytesIO objects to avoid disk writes.

    Example:
        downloader = DocumentDownloader(service)

        # Download single document
        doc = downloader.download_document(drive_document)

        # Download batch of documents
        for result in downloader.download_batch(documents):
            if isinstance(result, DownloadedDocument):
                process(result)
            else:
                handle_error(result)
    """

    # MIME type for Google Docs (native format)
    GOOGLE_DOCS_MIME = "application/vnd.google-apps.document"

    # MIME type for .docx files (export format and direct download)
    DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    # Size warning threshold (10MB - Google Docs export limit)
    SIZE_WARNING_BYTES = 10 * 1024 * 1024  # 10MB

    def __init__(
        self,
        service: Any,
        rate_limiter: Optional[Any] = None,
        max_concurrent: int = 5,
    ) -> None:
        """Initialize the document downloader.

        Args:
            service: Authenticated Google Drive API service.
            rate_limiter: Optional rate limiter for API calls.
            max_concurrent: Maximum parallel downloads (for future use).
        """
        self._service = service
        self._rate_limiter = rate_limiter
        self._max_concurrent = max_concurrent

    def download_document(self, doc: DriveDocument) -> DownloadedDocument:
        """Download a single document to BytesIO.

        For Google Docs, exports to .docx format.
        For .docx files, downloads directly.

        Args:
            doc: Document metadata from discovery.

        Returns:
            Downloaded document with content stream.

        Raises:
            DriveExportError: If export/download fails.
            FileTooLargeError: If file exceeds the 10MB export limit.
            DownloadError: If download fails for other reasons.
        """
        start_time = time.time()

        # Apply rate limiting if configured
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        # Check size warning for known sizes
        if doc.size_bytes is not None and doc.size_bytes > self.SIZE_WARNING_BYTES:
            # Log warning but continue - actual limit is enforced by Google
            pass

        try:
            if doc.mime_type == self.GOOGLE_DOCS_MIME:
                # Export Google Doc to .docx format
                content = self._export_google_doc(doc)
                export_mime = self.DOCX_MIME
            elif doc.mime_type == self.DOCX_MIME:
                # Download .docx directly
                content = self._download_file(doc)
                export_mime = self.DOCX_MIME
            else:
                raise DriveExportError(
                    f"Unsupported MIME type: {doc.mime_type}. "
                    f"Only Google Docs and .docx files are supported.",
                    file_id=doc.id,
                    mime_type=doc.mime_type,
                )

            download_time = time.time() - start_time

            return DownloadedDocument(
                drive_document=doc,
                content=content,
                export_mime_type=export_mime,
                download_time_seconds=download_time,
            )

        except (DriveExportError, FileTooLargeError, DownloadError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            # Wrap unexpected errors
            raise DownloadError(
                f"Failed to download document '{doc.name}': {e}",
                file_id=doc.id,
            ) from e

    def download_batch(
        self,
        documents: List[DriveDocument],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Iterator[Union[DownloadedDocument, DownloadError]]:
        """Download multiple documents in parallel using ThreadPoolExecutor.

        Uses max_concurrent threads to download documents concurrently,
        significantly improving throughput for large batches.

        Args:
            documents: List of documents to download.
            progress_callback: Optional callback with (completed, total) counts.

        Yields:
            DownloadedDocument on success, DownloadError on failure.
            Note: Results are yielded in completion order, not submission order.
        """
        if not documents:
            return

        total = len(documents)
        completed_count = 0

        def _download_one(doc: DriveDocument) -> Union[DownloadedDocument, DownloadError]:
            """Download a single document, returning result or error."""
            try:
                return self.download_document(doc)
            except (DriveExportError, FileTooLargeError, DownloadError) as e:
                if isinstance(e, DownloadError):
                    return e
                return DownloadError(str(e), file_id=doc.id)
            except Exception as e:
                return DownloadError(
                    f"Unexpected error downloading '{doc.name}': {e}",
                    file_id=doc.id,
                )

        with ThreadPoolExecutor(max_workers=self._max_concurrent) as executor:
            # Submit all download tasks
            future_to_doc = {
                executor.submit(_download_one, doc): doc for doc in documents
            }

            # Yield results as they complete
            for future in as_completed(future_to_doc):
                result = future.result()
                yield result

                # Report progress after each completion
                completed_count += 1
                if progress_callback is not None:
                    progress_callback(completed_count, total)

    def _export_google_doc(self, doc: DriveDocument) -> BytesIO:
        """Export a Google Doc to .docx format.

        Args:
            doc: Google Doc document metadata.

        Returns:
            BytesIO stream containing the .docx content.

        Raises:
            DriveExportError: If export fails.
            FileTooLargeError: If document exceeds 10MB export limit.
        """
        try:
            # Use files().export() for Google Docs
            request = self._service.files().export_media(
                fileId=doc.id,
                mimeType=self.DOCX_MIME,
            )

            # Download to BytesIO
            content = BytesIO()
            downloader = self._create_media_downloader(content, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Reset stream position to beginning
            content.seek(0)
            return content

        except Exception as e:
            error_str = str(e).lower()

            # Check for size limit errors
            if "too large" in error_str or "exceeds" in error_str:
                raise FileTooLargeError(
                    f"Document '{doc.name}' exceeds the 10MB export limit. "
                    f"Consider splitting the document or processing it locally.",
                    file_id=doc.id,
                ) from e

            raise DriveExportError(
                f"Failed to export Google Doc '{doc.name}': {e}",
                file_id=doc.id,
                mime_type=doc.mime_type,
            ) from e

    def _download_file(self, doc: DriveDocument) -> BytesIO:
        """Download a file directly from Google Drive.

        Args:
            doc: Document metadata.

        Returns:
            BytesIO stream containing the file content.

        Raises:
            DownloadError: If download fails.
        """
        try:
            # Use files().get_media() for direct download
            request = self._service.files().get_media(fileId=doc.id)

            # Download to BytesIO
            content = BytesIO()
            downloader = self._create_media_downloader(content, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Reset stream position to beginning
            content.seek(0)
            return content

        except Exception as e:
            raise DownloadError(
                f"Failed to download file '{doc.name}': {e}",
                file_id=doc.id,
            ) from e

    def _create_media_downloader(
        self,
        content: BytesIO,
        request: Any,
    ) -> Any:
        """Create a MediaIoBaseDownload for streaming downloads.

        Args:
            content: BytesIO stream to write to.
            request: Google API request object.

        Returns:
            MediaIoBaseDownload instance.
        """
        from googleapiclient.http import MediaIoBaseDownload

        return MediaIoBaseDownload(content, request)
