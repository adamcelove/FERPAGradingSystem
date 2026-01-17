"""Unit tests for Google Drive uploader module.

Tests upload functionality, retry logic, upload modes, and folder creation.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from ferpa_feedback.gdrive.discovery import DriveDocument
from ferpa_feedback.gdrive.uploader import ResultUploader, UploadMode, UploadResult

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_service() -> MagicMock:
    """Create a mock Google Drive API service."""
    return MagicMock()


@pytest.fixture
def sample_document() -> DriveDocument:
    """Create a sample DriveDocument for testing."""
    return DriveDocument(
        id="doc123",
        name="Test Comments.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        parent_folder_id="folder123",
        modified_time="2026-01-15T10:00:00Z",
    )


# -----------------------------------------------------------------------------
# Test upload_grammar_report
# -----------------------------------------------------------------------------


class TestUploadGrammarReport:
    """Tests for ResultUploader.upload_grammar_report method."""

    def test_upload_grammar_report_correct_naming(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """Grammar report is named correctly based on original document."""
        # Mock successful upload
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.return_value = {"id": "new_file_123"}

        uploader = ResultUploader(mock_service)
        result = uploader.upload_grammar_report(
            report_content="Grammar issues found...",
            original_doc=sample_document,
            folder_id="folder123",
        )

        assert result.success is True
        # File name should be original name + _grammar_report.txt
        assert result.file_name == "Test Comments_grammar_report.txt"

    def test_upload_grammar_report_to_correct_folder(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """Grammar report is uploaded to the specified folder."""
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.return_value = {"id": "new_file_123"}

        uploader = ResultUploader(mock_service)
        result = uploader.upload_grammar_report(
            report_content="Grammar issues found...",
            original_doc=sample_document,
            folder_id="target_folder_456",
        )

        assert result.success is True
        assert result.parent_folder_id == "target_folder_456"


# -----------------------------------------------------------------------------
# Test upload_anonymized_output
# -----------------------------------------------------------------------------


class TestUploadAnonymizedOutput:
    """Tests for ResultUploader.upload_anonymized_output method."""

    def test_upload_anonymized_output_correct_naming(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """Anonymized output is named correctly."""
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.return_value = {"id": "new_file_123"}

        uploader = ResultUploader(mock_service)
        result = uploader.upload_anonymized_output(
            content="Anonymized content...",
            original_doc=sample_document,
            output_folder_id="output_folder",
        )

        assert result.success is True
        # File name should be original name + _anonymized.txt
        assert result.file_name == "Test Comments_anonymized.txt"


# -----------------------------------------------------------------------------
# Test upload modes
# -----------------------------------------------------------------------------


class TestUploadModes:
    """Tests for different upload modes."""

    def test_upload_overwrite_mode_replaces_existing(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """OVERWRITE mode updates existing file instead of creating new."""
        # Mock finding an existing file
        mock_service.files().list().execute.return_value = {
            "files": [{"id": "existing_file_123"}]
        }
        mock_service.files().update().execute.return_value = {"id": "existing_file_123"}

        uploader = ResultUploader(mock_service, upload_mode=UploadMode.OVERWRITE)
        result = uploader.upload_grammar_report(
            report_content="Updated grammar issues...",
            original_doc=sample_document,
            folder_id="folder123",
        )

        assert result.success is True
        assert result.file_id == "existing_file_123"
        # Should call update, not create
        mock_service.files().update.assert_called()

    def test_upload_overwrite_mode_creates_if_not_exists(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """OVERWRITE mode creates new file if none exists."""
        # Mock no existing file
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.return_value = {"id": "new_file_456"}

        uploader = ResultUploader(mock_service, upload_mode=UploadMode.OVERWRITE)
        result = uploader.upload_grammar_report(
            report_content="Grammar issues...",
            original_doc=sample_document,
            folder_id="folder123",
        )

        assert result.success is True
        assert result.file_id == "new_file_456"
        # Should call create
        mock_service.files().create.assert_called()

    def test_upload_version_mode_appends_timestamp(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """VERSION mode appends timestamp to filename."""
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.return_value = {"id": "new_file_789"}

        uploader = ResultUploader(mock_service, upload_mode=UploadMode.VERSION)
        result = uploader.upload_grammar_report(
            report_content="Grammar issues...",
            original_doc=sample_document,
            folder_id="folder123",
        )

        assert result.success is True
        # File name should include timestamp pattern: _YYYYMMDD_HHMMSS
        assert "Test Comments_grammar_report_" in result.file_name
        assert result.file_name.endswith(".txt")
        # Should have a timestamp in the middle
        import re
        assert re.search(r"_\d{8}_\d{6}\.txt$", result.file_name)

    def test_upload_skip_mode_skips_existing(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """SKIP mode skips upload if file exists."""
        # Mock finding an existing file
        mock_service.files().list().execute.return_value = {
            "files": [{"id": "existing_file_123"}]
        }

        uploader = ResultUploader(mock_service, upload_mode=UploadMode.SKIP)
        result = uploader.upload_grammar_report(
            report_content="Grammar issues...",
            original_doc=sample_document,
            folder_id="folder123",
        )

        assert result.success is True
        assert result.file_id == "existing_file_123"
        # Should NOT call create or update
        mock_service.files().create.assert_not_called()
        mock_service.files().update.assert_not_called()

    def test_upload_skip_mode_creates_if_not_exists(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """SKIP mode creates file if it doesn't exist."""
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.return_value = {"id": "new_file_123"}

        uploader = ResultUploader(mock_service, upload_mode=UploadMode.SKIP)
        result = uploader.upload_grammar_report(
            report_content="Grammar issues...",
            original_doc=sample_document,
            folder_id="folder123",
        )

        assert result.success is True
        assert result.file_id == "new_file_123"
        mock_service.files().create.assert_called()


# -----------------------------------------------------------------------------
# Test retry logic
# -----------------------------------------------------------------------------


class TestRetryLogic:
    """Tests for upload retry with exponential backoff."""

    def test_upload_retry_on_failure(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """Upload retries on failure with exponential backoff."""
        # Mock: first 2 attempts fail, third succeeds
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.side_effect = [
            Exception("Network error"),
            Exception("Timeout"),
            {"id": "success_file_123"},
        ]

        with patch("time.sleep") as mock_sleep:
            uploader = ResultUploader(mock_service, max_retries=3)
            result = uploader.upload_grammar_report(
                report_content="Grammar issues...",
                original_doc=sample_document,
                folder_id="folder123",
            )

        assert result.success is True
        assert result.file_id == "success_file_123"
        # Should have slept with exponential backoff: 1s, 2s
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)  # 2^0 = 1
        mock_sleep.assert_any_call(2)  # 2^1 = 2

    def test_upload_fails_after_max_retries(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """Upload fails after exhausting all retries."""
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.side_effect = Exception("Persistent error")

        with patch("time.sleep"):
            uploader = ResultUploader(mock_service, max_retries=3)
            result = uploader.upload_grammar_report(
                report_content="Grammar issues...",
                original_doc=sample_document,
                folder_id="folder123",
            )

        assert result.success is False
        assert result.error is not None
        assert "after 3 attempts" in result.error
        assert "Persistent error" in result.error

    def test_upload_exponential_backoff_timing(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """Exponential backoff follows correct timing pattern."""
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
            Exception("Error 3"),
        ]

        with patch("time.sleep") as mock_sleep:
            uploader = ResultUploader(mock_service, max_retries=3)
            result = uploader.upload_grammar_report(
                report_content="Grammar issues...",
                original_doc=sample_document,
                folder_id="folder123",
            )

        assert result.success is False
        # Backoff pattern: 2^0=1, 2^1=2 (no sleep after final failure)
        assert mock_sleep.call_args_list == [call(1), call(2)]


# -----------------------------------------------------------------------------
# Test ensure_output_folder
# -----------------------------------------------------------------------------


class TestEnsureOutputFolder:
    """Tests for ResultUploader.ensure_output_folder method."""

    def test_ensure_output_folder_returns_existing(self, mock_service: MagicMock) -> None:
        """Returns existing folder ID if folder already exists."""
        mock_service.files().list().execute.return_value = {
            "files": [{"id": "existing_output_folder", "name": "pipeline_outputs"}]
        }

        uploader = ResultUploader(mock_service)
        folder_id = uploader.ensure_output_folder(
            parent_folder_id="parent123",
            folder_name="pipeline_outputs",
        )

        assert folder_id == "existing_output_folder"
        # Should not call create
        mock_service.files().create.assert_not_called()

    def test_ensure_output_folder_creates_if_missing(self, mock_service: MagicMock) -> None:
        """Creates new folder if it doesn't exist."""
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.return_value = {"id": "new_output_folder"}

        uploader = ResultUploader(mock_service)
        folder_id = uploader.ensure_output_folder(
            parent_folder_id="parent123",
            folder_name="pipeline_outputs",
        )

        assert folder_id == "new_output_folder"
        mock_service.files().create.assert_called()

    def test_ensure_output_folder_uses_correct_mime_type(self, mock_service: MagicMock) -> None:
        """Creates folder with correct MIME type."""
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.return_value = {"id": "new_folder"}

        uploader = ResultUploader(mock_service)
        uploader.ensure_output_folder(
            parent_folder_id="parent123",
            folder_name="outputs",
        )

        # Verify create was called with folder MIME type
        create_call = mock_service.files().create.call_args
        body = create_call.kwargs.get("body") or create_call[1].get("body")
        assert body["mimeType"] == "application/vnd.google-apps.folder"
        assert body["name"] == "outputs"
        assert body["parents"] == ["parent123"]


# -----------------------------------------------------------------------------
# Test UploadResult
# -----------------------------------------------------------------------------


class TestUploadResult:
    """Tests for UploadResult dataclass."""

    def test_upload_result_success(self) -> None:
        """UploadResult captures successful upload."""
        result = UploadResult(
            file_id="file123",
            file_name="report.txt",
            parent_folder_id="folder456",
            success=True,
            upload_time_seconds=1.5,
        )

        assert result.file_id == "file123"
        assert result.file_name == "report.txt"
        assert result.success is True
        assert result.error is None
        assert result.upload_time_seconds == 1.5

    def test_upload_result_failure(self) -> None:
        """UploadResult captures failed upload."""
        result = UploadResult(
            file_id="",
            file_name="report.txt",
            parent_folder_id="folder456",
            success=False,
            error="Upload failed: Permission denied",
            upload_time_seconds=0.5,
        )

        assert result.file_id == ""
        assert result.success is False
        assert result.error is not None
        assert "Permission denied" in result.error


# -----------------------------------------------------------------------------
# Test rate limiting integration
# -----------------------------------------------------------------------------


class TestRateLimitingIntegration:
    """Tests for rate limiter integration with uploader."""

    def test_rate_limiter_called_on_upload(
        self, mock_service: MagicMock, sample_document: DriveDocument
    ) -> None:
        """Rate limiter is called before upload operations."""
        mock_rate_limiter = MagicMock()
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.return_value = {"id": "new_file"}

        uploader = ResultUploader(mock_service, rate_limiter=mock_rate_limiter)
        uploader.upload_grammar_report(
            report_content="Grammar issues...",
            original_doc=sample_document,
            folder_id="folder123",
        )

        # Rate limiter should have been called at least once
        assert mock_rate_limiter.acquire.call_count >= 1
