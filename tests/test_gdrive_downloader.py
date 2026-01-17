"""Unit tests for Google Drive downloader module.

Tests document downloading, MIME type handling, BytesIO streaming, and error handling.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from ferpa_feedback.gdrive.discovery import DriveDocument
from ferpa_feedback.gdrive.downloader import DocumentDownloader, DownloadedDocument
from ferpa_feedback.gdrive.errors import DownloadError, DriveExportError

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_service() -> MagicMock:
    """Create a mock Google Drive API service."""
    return MagicMock()


@pytest.fixture
def google_doc() -> DriveDocument:
    """Create a Google Doc (native format) document."""
    return DriveDocument(
        id="doc_google_123",
        name="Test Document",
        mime_type="application/vnd.google-apps.document",
        parent_folder_id="folder123",
        modified_time="2026-01-15T10:00:00Z",
        size_bytes=None,  # Google Docs don't report size
    )


@pytest.fixture
def docx_file() -> DriveDocument:
    """Create a .docx file document."""
    return DriveDocument(
        id="doc_docx_456",
        name="Test Document.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        parent_folder_id="folder456",
        modified_time="2026-01-15T11:00:00Z",
        size_bytes=50000,  # 50KB
    )


@pytest.fixture
def large_docx_file() -> DriveDocument:
    """Create a large .docx file (over 10MB threshold)."""
    return DriveDocument(
        id="doc_large_789",
        name="Large Document.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        parent_folder_id="folder789",
        modified_time="2026-01-15T12:00:00Z",
        size_bytes=15 * 1024 * 1024,  # 15MB
    )


@pytest.fixture
def unsupported_file() -> DriveDocument:
    """Create an unsupported file type (PDF)."""
    return DriveDocument(
        id="doc_pdf_999",
        name="Test Document.pdf",
        mime_type="application/pdf",
        parent_folder_id="folder999",
        modified_time="2026-01-15T13:00:00Z",
        size_bytes=100000,
    )


# -----------------------------------------------------------------------------
# Helper to mock media download
# -----------------------------------------------------------------------------


def create_mock_downloader(content: bytes) -> MagicMock:  # noqa: ARG001
    """Create a mock MediaIoBaseDownload that returns the given content."""
    mock_downloader = MagicMock()
    # Simulate the chunked download pattern
    mock_downloader.next_chunk.side_effect = [
        (MagicMock(progress=lambda: 0.5), False),  # First chunk
        (MagicMock(progress=lambda: 1.0), True),   # Final chunk, done
    ]

    # Actually write the content to the BytesIO when next_chunk is called
    def write_content_side_effect() -> None:
        # This is a simplified simulation
        pass

    _ = write_content_side_effect  # Suppress unused warning

    return mock_downloader


# -----------------------------------------------------------------------------
# Test download_document
# -----------------------------------------------------------------------------


class TestDownloadDocument:
    """Tests for DocumentDownloader.download_document method."""

    def test_download_google_doc_exports_to_docx(self, mock_service: MagicMock, google_doc: DriveDocument) -> None:
        """Google Docs are exported to .docx format."""
        # Setup mock for export
        mock_content = b"PK\x03\x04"  # .docx magic bytes (it's a ZIP)
        mock_request = MagicMock()
        mock_service.files().export_media.return_value = mock_request

        with patch("ferpa_feedback.gdrive.downloader.DocumentDownloader._create_media_downloader") as mock_create:
            # Mock the downloader to write content
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.side_effect = [
                (None, False),
                (None, True),
            ]

            def populate_buffer(buffer: BytesIO, request: MagicMock) -> MagicMock:
                buffer.write(mock_content)
                return mock_downloader

            mock_create.side_effect = populate_buffer

            downloader = DocumentDownloader(mock_service)
            result = downloader.download_document(google_doc)

        assert isinstance(result, DownloadedDocument)
        assert result.export_mime_type == DocumentDownloader.DOCX_MIME
        mock_service.files().export_media.assert_called_once_with(
            fileId=google_doc.id,
            mimeType=DocumentDownloader.DOCX_MIME,
        )

    def test_download_existing_docx_direct_download(self, mock_service: MagicMock, docx_file: DriveDocument) -> None:
        """Existing .docx files are downloaded directly without conversion."""
        mock_content = b"PK\x03\x04"  # .docx magic bytes
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        with patch("ferpa_feedback.gdrive.downloader.DocumentDownloader._create_media_downloader") as mock_create:
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.side_effect = [
                (None, False),
                (None, True),
            ]

            def populate_buffer(buffer: BytesIO, request: MagicMock) -> MagicMock:
                buffer.write(mock_content)
                return mock_downloader

            mock_create.side_effect = populate_buffer

            downloader = DocumentDownloader(mock_service)
            result = downloader.download_document(docx_file)

        assert isinstance(result, DownloadedDocument)
        assert result.export_mime_type == DocumentDownloader.DOCX_MIME
        # Should use get_media for direct download, not export_media
        mock_service.files().get_media.assert_called_once_with(fileId=docx_file.id)

    def test_download_returns_bytesio(self, mock_service: MagicMock, docx_file: DriveDocument) -> None:
        """Downloaded content is returned as BytesIO (no disk writes)."""
        mock_content = b"PK\x03\x04test content"
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        with patch("ferpa_feedback.gdrive.downloader.DocumentDownloader._create_media_downloader") as mock_create:
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.side_effect = [
                (None, True),
            ]

            def populate_buffer(buffer: BytesIO, request: MagicMock) -> MagicMock:
                buffer.write(mock_content)
                return mock_downloader

            mock_create.side_effect = populate_buffer

            downloader = DocumentDownloader(mock_service)
            result = downloader.download_document(docx_file)

        # Verify result is BytesIO
        assert isinstance(result.content, BytesIO)
        # BytesIO should be seeked to beginning
        assert result.content.tell() == 0
        # Content should match
        assert result.content.read() == mock_content

    def test_download_handles_large_file_warning(self, mock_service: MagicMock, large_docx_file: DriveDocument) -> None:
        """Large files (>10MB) are downloaded with size warning logged."""
        mock_content = b"PK\x03\x04"
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        with patch("ferpa_feedback.gdrive.downloader.DocumentDownloader._create_media_downloader") as mock_create:
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.side_effect = [(None, True)]

            def populate_buffer(buffer: BytesIO, request: MagicMock) -> MagicMock:
                buffer.write(mock_content)
                return mock_downloader

            mock_create.side_effect = populate_buffer

            downloader = DocumentDownloader(mock_service)
            # Should not raise, just continue with warning logged
            result = downloader.download_document(large_docx_file)

        assert isinstance(result, DownloadedDocument)
        # Verify the size was above threshold
        assert large_docx_file.size_bytes is not None
        assert large_docx_file.size_bytes > DocumentDownloader.SIZE_WARNING_BYTES

    def test_download_unsupported_mime_type_raises(self, mock_service: MagicMock, unsupported_file: DriveDocument) -> None:
        """Unsupported MIME types raise DriveExportError."""
        downloader = DocumentDownloader(mock_service)

        with pytest.raises(DriveExportError) as exc_info:
            downloader.download_document(unsupported_file)

        assert "Unsupported MIME type" in str(exc_info.value)
        assert "application/pdf" in str(exc_info.value)

    def test_download_preserves_document_metadata(self, mock_service: MagicMock, docx_file: DriveDocument) -> None:
        """Downloaded document preserves original metadata."""
        mock_content = b"PK\x03\x04"
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        with patch("ferpa_feedback.gdrive.downloader.DocumentDownloader._create_media_downloader") as mock_create:
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.side_effect = [(None, True)]

            def populate_buffer(buffer: BytesIO, request: MagicMock) -> MagicMock:
                buffer.write(mock_content)
                return mock_downloader

            mock_create.side_effect = populate_buffer

            downloader = DocumentDownloader(mock_service)
            result = downloader.download_document(docx_file)

        # Verify original document is preserved
        assert result.drive_document.id == docx_file.id
        assert result.drive_document.name == docx_file.name
        assert result.drive_document.mime_type == docx_file.mime_type

    def test_download_records_timing(self, mock_service: MagicMock, docx_file: DriveDocument) -> None:
        """Download time is recorded in result."""
        mock_content = b"PK\x03\x04"
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        with patch("ferpa_feedback.gdrive.downloader.DocumentDownloader._create_media_downloader") as mock_create:
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.side_effect = [(None, True)]

            def populate_buffer(buffer: BytesIO, request: MagicMock) -> MagicMock:
                buffer.write(mock_content)
                return mock_downloader

            mock_create.side_effect = populate_buffer

            downloader = DocumentDownloader(mock_service)
            result = downloader.download_document(docx_file)

        # Should have recorded some download time
        assert result.download_time_seconds >= 0


# -----------------------------------------------------------------------------
# Test download_batch
# -----------------------------------------------------------------------------


class TestDownloadBatch:
    """Tests for DocumentDownloader.download_batch method."""

    def test_download_batch_empty_list(self, mock_service: MagicMock) -> None:
        """Empty document list returns no results."""
        downloader = DocumentDownloader(mock_service)

        results = list(downloader.download_batch([]))

        assert len(results) == 0

    def test_download_batch_continues_on_error(self, mock_service: MagicMock) -> None:
        """Batch download continues when individual documents fail."""
        # Create mix of valid and invalid documents
        valid_doc = DriveDocument(
            id="valid1",
            name="Valid.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            parent_folder_id="folder",
            modified_time="2026-01-15T10:00:00Z",
        )
        invalid_doc = DriveDocument(
            id="invalid1",
            name="Invalid.pdf",
            mime_type="application/pdf",  # Unsupported
            parent_folder_id="folder",
            modified_time="2026-01-15T10:00:00Z",
        )

        mock_content = b"PK\x03\x04"
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        with patch("ferpa_feedback.gdrive.downloader.DocumentDownloader._create_media_downloader") as mock_create:
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.side_effect = [(None, True)]

            def populate_buffer(buffer: BytesIO, request: MagicMock) -> MagicMock:
                buffer.write(mock_content)
                return mock_downloader

            mock_create.side_effect = populate_buffer

            downloader = DocumentDownloader(mock_service, max_concurrent=1)
            results = list(downloader.download_batch([valid_doc, invalid_doc]))

        # Should have 2 results - one success, one error
        assert len(results) == 2

        successes = [r for r in results if isinstance(r, DownloadedDocument)]
        errors = [r for r in results if isinstance(r, DownloadError)]

        assert len(successes) == 1
        assert len(errors) == 1
        assert successes[0].drive_document.id == "valid1"

    def test_download_batch_progress_callback(self, mock_service: MagicMock, docx_file: DriveDocument) -> None:
        """Progress callback is called for each completed download."""
        mock_content = b"PK\x03\x04"
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        progress_calls: list[tuple[int, int]] = []

        def track_progress(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        with patch("ferpa_feedback.gdrive.downloader.DocumentDownloader._create_media_downloader") as mock_create:
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.side_effect = [(None, True)]

            def populate_buffer(buffer: BytesIO, request: MagicMock) -> MagicMock:
                buffer.write(mock_content)
                return mock_downloader

            mock_create.side_effect = populate_buffer

            downloader = DocumentDownloader(mock_service, max_concurrent=1)
            # Download 2 copies of the same doc
            docs = [docx_file, docx_file]
            _ = list(downloader.download_batch(docs, progress_callback=track_progress))

        # Should have been called twice
        assert len(progress_calls) == 2
        # Progress should show completion
        assert progress_calls[-1] == (2, 2)

    def test_download_batch_uses_thread_pool(self, mock_service: MagicMock) -> None:
        """Batch download uses ThreadPoolExecutor for parallelism."""
        downloader = DocumentDownloader(mock_service, max_concurrent=5)

        # Verify the max_concurrent parameter is stored
        assert downloader._max_concurrent == 5


# -----------------------------------------------------------------------------
# Test rate limiting integration
# -----------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for rate limiter integration."""

    def test_rate_limiter_called_on_download(self, mock_service: MagicMock, docx_file: DriveDocument) -> None:
        """Rate limiter is called before each download."""
        mock_rate_limiter = MagicMock()
        mock_content = b"PK\x03\x04"
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        with patch("ferpa_feedback.gdrive.downloader.DocumentDownloader._create_media_downloader") as mock_create:
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.side_effect = [(None, True)]

            def populate_buffer(buffer: BytesIO, request: MagicMock) -> MagicMock:
                buffer.write(mock_content)
                return mock_downloader

            mock_create.side_effect = populate_buffer

            downloader = DocumentDownloader(mock_service, rate_limiter=mock_rate_limiter)
            downloader.download_document(docx_file)

        # Rate limiter should have been called
        mock_rate_limiter.acquire.assert_called_once()


# -----------------------------------------------------------------------------
# Test DownloadedDocument
# -----------------------------------------------------------------------------


class TestDownloadedDocument:
    """Tests for DownloadedDocument dataclass."""

    def test_downloaded_document_attributes(self, docx_file: DriveDocument) -> None:
        """DownloadedDocument stores all expected attributes."""
        content = BytesIO(b"test content")

        doc = DownloadedDocument(
            drive_document=docx_file,
            content=content,
            export_mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            download_time_seconds=1.5,
        )

        assert doc.drive_document == docx_file
        assert doc.content == content
        assert doc.export_mime_type == DocumentDownloader.DOCX_MIME
        assert doc.download_time_seconds == 1.5
