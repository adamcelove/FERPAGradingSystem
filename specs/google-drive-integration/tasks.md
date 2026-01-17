---
spec: google-drive-integration
phase: tasks
total_tasks: 32
created: 2026-01-17
---

# Tasks: Google Drive Integration

## Phase 1: Make It Work (POC)

Focus: Validate the idea works end-to-end. Skip tests, accept hardcoded values, focus on core flow.

### 1.1 Create gdrive module structure and error types

- [x] 1.1 Create gdrive module structure and error types
  - **Do**:
    1. Create the `src/ferpa_feedback/gdrive/` directory
    2. Create `__init__.py` with module exports
    3. Create `errors.py` with custom exception classes: `DriveAccessError`, `DriveExportError`, `DiscoveryTimeoutError`, `DownloadError`, `UploadError`, `FileTooLargeError`, `AuthenticationError`
    4. Create `config.py` with `DriveConfig` dataclass for configuration
  - **Files**:
    - `src/ferpa_feedback/gdrive/__init__.py` (create)
    - `src/ferpa_feedback/gdrive/errors.py` (create)
    - `src/ferpa_feedback/gdrive/config.py` (create)
  - **Done when**: Module can be imported without errors
  - **Verify**: `python -c "from ferpa_feedback.gdrive import DriveAccessError, DriveConfig"`
  - **Commit**: `feat(gdrive): create module structure with errors and config`
  - _Requirements: FR-1, FR-2_
  - _Design: File Structure_

### 1.2 Implement OAuth2 authenticator for local development

- [x] 1.2 Implement OAuth2 authenticator for local development
  - **Do**:
    1. Create `src/ferpa_feedback/gdrive/auth.py`
    2. Implement `DriveAuthenticator` protocol with `get_service()` and `service_account_email` property
    3. Implement `OAuth2Authenticator` class that handles OAuth2 flow using `google-auth-oauthlib`
    4. Add `create_authenticator()` factory function that detects environment
    5. For POC, only implement OAuth2 path (skip WIF for now)
  - **Files**:
    - `src/ferpa_feedback/gdrive/auth.py` (create)
  - **Done when**: Can authenticate with Google Drive API using OAuth2 credentials
  - **Verify**: `python -c "from ferpa_feedback.gdrive.auth import OAuth2Authenticator; print('OAuth2Authenticator imported')"`
  - **Commit**: `feat(gdrive): implement OAuth2 authenticator for development`
  - _Requirements: AC-1.5, FR-16_
  - _Design: Component 1 - DriveAuthenticator_

### 1.3 Implement FolderDiscovery with FolderMap

- [x] 1.3 Implement FolderDiscovery with FolderMap
  - **Do**:
    1. Create `src/ferpa_feedback/gdrive/discovery.py`
    2. Implement `FolderNode` dataclass with id, name, parent_id, depth, children, documents, is_leaf property, path property
    3. Implement `DriveDocument` dataclass with id, name, mime_type, parent_folder_id, modified_time, size_bytes
    4. Implement `FolderMetadata` dataclass for house/teacher/period extraction
    5. Implement `FolderMap` dataclass with root, discovered_at, total_folders, total_documents, leaf_folders; add `get_leaf_folders()`, `filter_by_pattern()`, `filter_by_patterns()`, `to_json()`, `print_tree()` methods
    6. Implement `FolderDiscovery` class with `discover_structure()` method using Drive API `files.list`
    7. Implement `extract_metadata()` for position-based metadata extraction
    8. Implement `match_folder_pattern()` utility using `fnmatch` for glob patterns
  - **Files**:
    - `src/ferpa_feedback/gdrive/discovery.py` (create)
  - **Done when**: Can discover folder structure from a root folder ID and filter by patterns
  - **Verify**: `python -c "from ferpa_feedback.gdrive.discovery import FolderDiscovery, FolderMap, FolderNode"`
  - **Commit**: `feat(gdrive): implement folder discovery with pattern matching`
  - _Requirements: FR-11, AC-8.1, AC-8.2, AC-8.6, AC-11.2_
  - _Design: Component 2 - FolderDiscovery_

### 1.4 Quality Checkpoint

- [x] 1.4 Quality Checkpoint
  - **Do**: Run all quality checks to verify recent changes don't break the build
  - **Verify**: All commands must pass:
    - Type check: `pnpm run check-types` or `python -m mypy src/ferpa_feedback/gdrive --ignore-missing-imports`
    - Lint: `pnpm run lint` or `python -m ruff check src/ferpa_feedback/gdrive`
  - **Done when**: All quality checks pass with no errors
  - **Commit**: `chore(gdrive): pass quality checkpoint` (only if fixes needed)

### 1.5 Implement DocumentDownloader with BytesIO streaming

- [x] 1.5 Implement DocumentDownloader with BytesIO streaming
  - **Do**:
    1. Create `src/ferpa_feedback/gdrive/downloader.py`
    2. Implement `DownloadedDocument` dataclass with drive_document, content (BytesIO), export_mime_type, download_time_seconds
    3. Implement `DocumentDownloader` class with constants for GOOGLE_DOCS_MIME, DOCX_MIME, SIZE_WARNING_BYTES
    4. Implement `download_document()` method that exports Google Docs to .docx or downloads .docx directly
    5. Implement `download_batch()` method that yields `DownloadedDocument` or `DownloadError`
    6. Use `io.BytesIO` for all content (no disk writes)
    7. For POC, use sequential downloads (skip parallel for now)
  - **Files**:
    - `src/ferpa_feedback/gdrive/downloader.py` (create)
  - **Done when**: Can download Google Docs and .docx files as BytesIO streams
  - **Verify**: `python -c "from ferpa_feedback.gdrive.downloader import DocumentDownloader, DownloadedDocument"`
  - **Commit**: `feat(gdrive): implement document downloader with BytesIO streaming`
  - _Requirements: FR-3, FR-4, AC-3.1, AC-3.2, AC-3.3_
  - _Design: Component 3 - DocumentDownloader_

### 1.6 Modify DocumentParser to accept BytesIO

- [x] 1.6 Modify DocumentParser to accept BytesIO
  - **Do**:
    1. Modify `src/ferpa_feedback/stage_0_ingestion.py`
    2. Update `DocumentParser.parse_docx()` signature to accept `source: Union[Path, BytesIO]`
    3. Add conditional logic: if source is BytesIO, pass directly to `DocxDocument()`; if Path, use `DocxDocument(str(file_path))`
    4. Add optional `document_id` and `metadata` parameters
    5. Handle source_path in TeacherDocument: use str(Path) for file paths, use metadata.get('drive_file_id') for BytesIO
    6. Update `parse_document()` convenience function signature
  - **Files**:
    - `src/ferpa_feedback/stage_0_ingestion.py` (modify)
  - **Done when**: `parse_docx()` accepts both Path and BytesIO without breaking existing code
  - **Verify**: `python -c "from ferpa_feedback.stage_0_ingestion import DocumentParser; from io import BytesIO; print('BytesIO support added')"`
  - **Commit**: `feat(ingestion): add BytesIO support to DocumentParser`
  - _Requirements: AC-4.1, AC-4.2_
  - _Design: Component 4 - DocumentParser Extension_

### 1.7 Implement ResultUploader

- [x] 1.7 Implement ResultUploader
  - **Do**:
    1. Create `src/ferpa_feedback/gdrive/uploader.py`
    2. Implement `UploadMode` enum with OVERWRITE, VERSION, SKIP
    3. Implement `UploadResult` dataclass with file_id, file_name, parent_folder_id, success, error, upload_time_seconds
    4. Implement `ResultUploader` class with `upload_grammar_report()`, `upload_anonymized_output()`, `ensure_output_folder()` methods
    5. For POC, implement OVERWRITE mode only
    6. Add basic retry logic (3 retries)
  - **Files**:
    - `src/ferpa_feedback/gdrive/uploader.py` (create)
  - **Done when**: Can upload text files to Google Drive folders
  - **Verify**: `python -c "from ferpa_feedback.gdrive.uploader import ResultUploader, UploadMode, UploadResult"`
  - **Commit**: `feat(gdrive): implement result uploader`
  - _Requirements: FR-7, AC-5.1, AC-5.2, AC-5.4_
  - _Design: Component 5 - ResultUploader_

### 1.8 Quality Checkpoint

- [x] 1.8 Quality Checkpoint
  - **Do**: Run all quality checks to verify recent changes don't break the build
  - **Verify**: All commands must pass:
    - Type check: `python -m mypy src/ferpa_feedback/gdrive src/ferpa_feedback/stage_0_ingestion.py --ignore-missing-imports`
    - Lint: `python -m ruff check src/ferpa_feedback/gdrive src/ferpa_feedback/stage_0_ingestion.py`
  - **Done when**: All quality checks pass with no errors
  - **Commit**: `chore(gdrive): pass quality checkpoint` (only if fixes needed)

### 1.9 Implement DriveProcessor orchestrator

- [x] 1.9 Implement DriveProcessor orchestrator
  - **Do**:
    1. Create `src/ferpa_feedback/gdrive/processor.py`
    2. Implement `ProcessingProgress` dataclass for tracking
    3. Implement `ProcessingSummary` dataclass for results
    4. Implement `DriveProcessor` class that orchestrates the full workflow:
       - `__init__()` takes authenticator, pipeline, config
       - `process()` method: discover folders, filter by patterns, download docs, process through pipeline, upload results
       - `list_folders()` method for `--list-folders` option
    5. Wire together: Discovery -> Download -> Pipeline.process_document -> Upload
    6. Implement continue-on-error for batch processing
    7. Use existing `FeedbackPipeline` from `pipeline.py`
  - **Files**:
    - `src/ferpa_feedback/gdrive/processor.py` (create)
  - **Done when**: Can process documents from Drive end-to-end
  - **Verify**: `python -c "from ferpa_feedback.gdrive.processor import DriveProcessor, ProcessingSummary"`
  - **Commit**: `feat(gdrive): implement DriveProcessor orchestrator`
  - _Requirements: FR-5, FR-6, AC-4.1, AC-4.3, AC-4.4, AC-4.5_
  - _Design: Component 6 - DriveProcessor_

### 1.10 Add gdrive-process CLI command

- [x] 1.10 Add gdrive-process CLI command
  - **Do**:
    1. Modify `src/ferpa_feedback/cli.py`
    2. Add `gdrive_process` command with Typer
    3. Add arguments: `root_folder` (required)
    4. Add options: `--target-folder/-t` (repeatable), `--list-folders/-l`, `--dry-run`, `--output-local/-o`, `--roster/-r`, `--config/-c`, `--parallel/-p`
    5. Implement command logic:
       - Create authenticator (OAuth2 for now)
       - Create DriveProcessor
       - If `--list-folders`, call `list_folders()` and print tree
       - Otherwise, call `process()` with options
    6. Display progress using rich console
    7. Return appropriate exit codes
  - **Files**:
    - `src/ferpa_feedback/cli.py` (modify)
  - **Done when**: `ferpa-feedback gdrive-process --help` works
  - **Verify**: `python -m ferpa_feedback.cli gdrive-process --help`
  - **Commit**: `feat(cli): add gdrive-process command`
  - _Requirements: FR-8, AC-6.1, AC-6.2, AC-6.3, AC-6.4, AC-6.5, AC-6.6, AC-6.7_
  - _Design: Component 7 - CLI Extension_

### 1.11 Update settings.yaml with gdrive section

- [x] 1.11 Update settings.yaml with gdrive section
  - **Do**:
    1. Modify `settings.yaml`
    2. Add `gdrive:` section with subsections:
       - `auth:` with `method`, `oauth2:` (client_secrets_path, token_path)
       - `processing:` with max_concurrent_downloads, download_timeout_seconds, discovery_timeout_seconds, max_folder_depth
       - `upload:` with mode, output_folder_name, max_retries, retry_delay_seconds
       - `rate_limit:` with requests_per_100_seconds
    3. Set sensible defaults for POC
  - **Files**:
    - `settings.yaml` (modify)
  - **Done when**: Configuration file has gdrive section
  - **Verify**: `python -c "import yaml; c=yaml.safe_load(open('settings.yaml')); print(c['gdrive'])"`
  - **Commit**: `feat(config): add gdrive configuration section`
  - _Requirements: Configuration requirement from design_
  - _Design: Configuration Extension_

### 1.12 Update pyproject.toml with google-auth dependency

- [x] 1.12 Update pyproject.toml with google-auth dependency
  - **Do**:
    1. Modify `pyproject.toml`
    2. Add `google-auth>=2.20.0` and `google-auth-httplib2>=0.2.0` to dependencies
    3. Add `[project.optional-dependencies] cloud` with fastapi, uvicorn, gunicorn
  - **Files**:
    - `pyproject.toml` (modify)
  - **Done when**: Dependencies are specified
  - **Verify**: `python -c "import toml; t=toml.load('pyproject.toml'); print('google-auth' in str(t))"`
  - **Commit**: `build(deps): add google-auth and cloud dependencies`
  - _Requirements: Dependencies from design_
  - _Design: Dependencies to Add_

### 1.13 Quality Checkpoint

- [x] 1.13 Quality Checkpoint
  - **Do**: Run all quality checks to verify recent changes don't break the build
  - **Verify**: All commands must pass:
    - Type check: `python -m mypy src/ferpa_feedback --ignore-missing-imports`
    - Lint: `python -m ruff check src/ferpa_feedback`
  - **Done when**: All quality checks pass with no errors
  - **Commit**: `chore(gdrive): pass quality checkpoint` (only if fixes needed)

### 1.14 POC Checkpoint - End-to-end validation

- [x] 1.14 POC Checkpoint
  - **Do**: Verify feature works end-to-end
    1. Set up OAuth2 credentials (client_secrets.json)
    2. Share a test Drive folder with test documents
    3. Run `ferpa-feedback gdrive-process <folder-id> --list-folders`
    4. Run `ferpa-feedback gdrive-process <folder-id> --dry-run`
    5. Run `ferpa-feedback gdrive-process <folder-id> --output-local ./test_output`
  - **Done when**: Feature can be demonstrated working with real Drive folder
  - **Verify**: Manual test of core flow produces expected outputs
  - **Commit**: `feat(gdrive): complete POC for Google Drive integration`

## Phase 2: Refactoring

After POC validated, clean up code and add robustness.

### 2.1 Add rate limiter for API calls

- [x] 2.1 Add rate limiter for API calls
  - **Do**:
    1. Create `src/ferpa_feedback/gdrive/rate_limiter.py`
    2. Implement `RateLimiter` class with fixed window algorithm
    3. Configure for 900 requests per 100 seconds (under Google's 1000 limit)
    4. Add `acquire()` method that blocks if rate exceeded
    5. Integrate with FolderDiscovery, DocumentDownloader, ResultUploader
  - **Files**:
    - `src/ferpa_feedback/gdrive/rate_limiter.py` (create)
    - `src/ferpa_feedback/gdrive/discovery.py` (modify)
    - `src/ferpa_feedback/gdrive/downloader.py` (modify)
    - `src/ferpa_feedback/gdrive/uploader.py` (modify)
  - **Done when**: API calls are rate-limited
  - **Verify**: `python -c "from ferpa_feedback.gdrive.rate_limiter import RateLimiter"`
  - **Commit**: `refactor(gdrive): add rate limiter for API calls`
  - _Requirements: NFR-12, AC-2.5_
  - _Design: Rate Limiting_

### 2.2 Implement Workload Identity Federation authenticator

- [ ] 2.2 Implement Workload Identity Federation authenticator
  - **Do**:
    1. Modify `src/ferpa_feedback/gdrive/auth.py`
    2. Implement `WorkloadIdentityAuthenticator` class
    3. Accept project_id, pool_id, provider_id, service_account_email
    4. Use `google.auth.identity_pool` for token exchange
    5. Update `create_authenticator()` factory to detect Cloud Run environment and use WIF
    6. Add environment detection via `K_SERVICE` environment variable
  - **Files**:
    - `src/ferpa_feedback/gdrive/auth.py` (modify)
  - **Done when**: WIF authenticator implemented (may not be testable locally)
  - **Verify**: `python -c "from ferpa_feedback.gdrive.auth import WorkloadIdentityAuthenticator, create_authenticator"`
  - **Commit**: `feat(gdrive): implement Workload Identity Federation authenticator`
  - _Requirements: FR-1, AC-1.1, AC-1.2, NFR-6_
  - _Design: Component 1 - WorkloadIdentityAuthenticator_

### 2.3 Add parallel downloads with ThreadPoolExecutor

- [ ] 2.3 Add parallel downloads with ThreadPoolExecutor
  - **Do**:
    1. Modify `src/ferpa_feedback/gdrive/downloader.py`
    2. Add `max_concurrent` parameter to `DocumentDownloader.__init__()`
    3. Implement `download_batch()` using `concurrent.futures.ThreadPoolExecutor`
    4. Add progress callback support
    5. Default to 5 concurrent downloads
  - **Files**:
    - `src/ferpa_feedback/gdrive/downloader.py` (modify)
  - **Done when**: Batch downloads run in parallel
  - **Verify**: `python -c "from ferpa_feedback.gdrive.downloader import DocumentDownloader; d = DocumentDownloader(None, max_concurrent=5)"`
  - **Commit**: `refactor(gdrive): add parallel downloads with ThreadPoolExecutor`
  - _Requirements: FR-14, AC-10.2, NFR-3_
  - _Design: Parallel Downloads_

### 2.4 Quality Checkpoint

- [ ] 2.4 Quality Checkpoint
  - **Do**: Run all quality checks to verify refactoring doesn't break the build
  - **Verify**: All commands must pass:
    - Type check: `python -m mypy src/ferpa_feedback --ignore-missing-imports`
    - Lint: `python -m ruff check src/ferpa_feedback`
  - **Done when**: All quality checks pass with no errors
  - **Commit**: `chore(gdrive): pass quality checkpoint` (only if fixes needed)

### 2.5 Add comprehensive error handling

- [ ] 2.5 Add comprehensive error handling
  - **Do**:
    1. Add try/catch blocks around all Drive API calls
    2. Map Google API errors to custom exception types
    3. Add clear error messages with actionable instructions
    4. Add sharing instructions when DriveAccessError occurs
    5. Log all errors with structured fields
  - **Files**:
    - `src/ferpa_feedback/gdrive/discovery.py` (modify)
    - `src/ferpa_feedback/gdrive/downloader.py` (modify)
    - `src/ferpa_feedback/gdrive/uploader.py` (modify)
    - `src/ferpa_feedback/gdrive/auth.py` (modify)
  - **Done when**: All error paths handled gracefully
  - **Verify**: Type check passes
  - **Commit**: `refactor(gdrive): add comprehensive error handling`
  - _Requirements: AC-1.4, AC-2.4, NFR-4_
  - _Design: Error Handling_

### 2.6 Add upload retry with exponential backoff

- [ ] 2.6 Add upload retry with exponential backoff
  - **Do**:
    1. Modify `src/ferpa_feedback/gdrive/uploader.py`
    2. Implement retry decorator or inline retry logic
    3. Exponential backoff: 1s, 2s, 4s for 3 retries
    4. Log retry attempts
    5. Add VERSION upload mode (append timestamp to filename)
  - **Files**:
    - `src/ferpa_feedback/gdrive/uploader.py` (modify)
  - **Done when**: Uploads retry on failure
  - **Verify**: Type check passes
  - **Commit**: `refactor(gdrive): add upload retry with exponential backoff`
  - _Requirements: AC-5.4, NFR-4_
  - _Design: Error Handling_

### 2.7 Add interactive folder selection mode

- [ ] 2.7 Add interactive folder selection mode
  - **Do**:
    1. Modify `src/ferpa_feedback/cli.py`
    2. Add `--interactive/-i` option to gdrive-process command
    3. When enabled, use rich prompt to display folder tree
    4. Allow user to select folders by number or name
    5. Pass selected folders to processor
  - **Files**:
    - `src/ferpa_feedback/cli.py` (modify)
  - **Done when**: Interactive mode allows folder selection
  - **Verify**: `python -m ferpa_feedback.cli gdrive-process --help | grep interactive`
  - **Commit**: `feat(cli): add interactive folder selection mode`
  - _Requirements: FR-21, AC-11.3_
  - _Design: CLI Extension_

### 2.8 Quality Checkpoint

- [ ] 2.8 Quality Checkpoint
  - **Do**: Run all quality checks to verify refactoring doesn't break the build
  - **Verify**: All commands must pass:
    - Type check: `python -m mypy src/ferpa_feedback --ignore-missing-imports`
    - Lint: `python -m ruff check src/ferpa_feedback`
  - **Done when**: All quality checks pass with no errors
  - **Commit**: `chore(gdrive): pass quality checkpoint` (only if fixes needed)

## Phase 3: Testing

### 3.1 Unit tests for discovery module

- [ ] 3.1 Unit tests for discovery module
  - **Do**:
    1. Create `tests/test_gdrive_discovery.py`
    2. Add tests:
       - `test_discover_structure_simple_hierarchy` - 3-level tree
       - `test_discover_structure_identifies_leaf_folders` - Correct leaf detection
       - `test_filter_by_pattern_glob` - "September*" matches correctly
       - `test_filter_by_pattern_multiple` - Multiple patterns (OR)
       - `test_extract_metadata_from_path` - House/Teacher/Period extraction
       - `test_folder_map_to_json` - Serialization roundtrip
    3. Use unittest.mock to mock Google API responses
  - **Files**:
    - `tests/test_gdrive_discovery.py` (create)
  - **Done when**: Tests cover main discovery functionality
  - **Verify**: `pytest tests/test_gdrive_discovery.py -v`
  - **Commit**: `test(gdrive): add unit tests for discovery module`
  - _Requirements: AC-8.1, AC-8.2, AC-8.6, AC-11.2_
  - _Design: Test Strategy - Unit Tests_

### 3.2 Unit tests for downloader module

- [ ] 3.2 Unit tests for downloader module
  - **Do**:
    1. Create `tests/test_gdrive_downloader.py`
    2. Add tests:
       - `test_download_google_doc_exports_to_docx` - MIME type conversion
       - `test_download_existing_docx` - Direct download
       - `test_download_returns_bytesio` - No disk writes
       - `test_download_handles_large_file_warning` - Size threshold
       - `test_download_batch_continues_on_error` - Error isolation
    3. Mock Drive API responses
  - **Files**:
    - `tests/test_gdrive_downloader.py` (create)
  - **Done when**: Tests cover main downloader functionality
  - **Verify**: `pytest tests/test_gdrive_downloader.py -v`
  - **Commit**: `test(gdrive): add unit tests for downloader module`
  - _Requirements: AC-3.1, AC-3.2, AC-3.3, AC-3.5, AC-4.4_
  - _Design: Test Strategy - Unit Tests_

### 3.3 Unit tests for uploader module

- [ ] 3.3 Unit tests for uploader module
  - **Do**:
    1. Create `tests/test_gdrive_uploader.py`
    2. Add tests:
       - `test_upload_grammar_report` - Correct folder/naming
       - `test_upload_overwrite_mode` - Replaces existing
       - `test_upload_version_mode` - Appends timestamp
       - `test_upload_retry_on_failure` - Exponential backoff
       - `test_ensure_output_folder_creates_if_missing`
    3. Mock Drive API responses
  - **Files**:
    - `tests/test_gdrive_uploader.py` (create)
  - **Done when**: Tests cover main uploader functionality
  - **Verify**: `pytest tests/test_gdrive_uploader.py -v`
  - **Commit**: `test(gdrive): add unit tests for uploader module`
  - _Requirements: AC-5.1, AC-5.2, AC-5.3, AC-5.4_
  - _Design: Test Strategy - Unit Tests_

### 3.4 Quality Checkpoint

- [ ] 3.4 Quality Checkpoint
  - **Do**: Run all quality checks to verify tests don't introduce issues
  - **Verify**: All commands must pass:
    - Type check: `python -m mypy src/ferpa_feedback tests --ignore-missing-imports`
    - Lint: `python -m ruff check src/ferpa_feedback tests`
    - Tests: `pytest tests/test_gdrive_*.py -v`
  - **Done when**: All quality checks pass with no errors
  - **Commit**: `chore(gdrive): pass quality checkpoint` (only if fixes needed)

### 3.5 Unit tests for DocumentParser BytesIO support

- [ ] 3.5 Unit tests for DocumentParser BytesIO support
  - **Do**:
    1. Modify `tests/test_stage_0_ingestion.py` or create if not exists
    2. Add tests:
       - `test_parse_docx_from_bytesio` - BytesIO stream input works
       - `test_parse_docx_from_path` - Path input still works (regression)
       - `test_parse_docx_with_metadata` - Metadata parameter works
    3. Use real .docx file in fixtures or create minimal test docx
  - **Files**:
    - `tests/test_stage_0_ingestion.py` (create/modify)
  - **Done when**: BytesIO parsing is tested
  - **Verify**: `pytest tests/test_stage_0_ingestion.py -v`
  - **Commit**: `test(ingestion): add tests for BytesIO support`
  - _Requirements: AC-4.1_
  - _Design: Component 4_

### 3.6 Integration tests for DriveProcessor

- [ ] 3.6 Integration tests for DriveProcessor
  - **Do**:
    1. Create `tests/test_gdrive_integration.py`
    2. Add tests that mock Drive API but use real pipeline:
       - `test_end_to_end_with_mocked_drive` - Full flow with mocked API
       - `test_processor_filters_by_pattern` - Pattern matching works
       - `test_processor_continues_on_document_error` - Error isolation
       - `test_processor_generates_summary` - Summary stats correct
    3. Create mock Drive API responses with realistic data
  - **Files**:
    - `tests/test_gdrive_integration.py` (create)
  - **Done when**: Integration points tested
  - **Verify**: `pytest tests/test_gdrive_integration.py -v`
  - **Commit**: `test(gdrive): add integration tests for DriveProcessor`
  - _Requirements: AC-4.4, AC-4.5, AC-11.1, AC-11.2_
  - _Design: Test Strategy - Integration Tests_

### 3.7 Quality Checkpoint

- [ ] 3.7 Quality Checkpoint
  - **Do**: Run all quality checks to verify all tests pass
  - **Verify**: All commands must pass:
    - Type check: `python -m mypy src/ferpa_feedback tests --ignore-missing-imports`
    - Lint: `python -m ruff check src/ferpa_feedback tests`
    - Tests: `pytest tests/ -v --ignore=tests/e2e`
  - **Done when**: All quality checks pass with no errors
  - **Commit**: `chore(gdrive): pass quality checkpoint` (only if fixes needed)

## Phase 4: Cloud Deployment and Quality Gates

### 4.1 Create Cloud Run handler

- [ ] 4.1 Create Cloud Run handler
  - **Do**:
    1. Create `src/ferpa_feedback/gdrive/cloud_handler.py`
    2. Implement FastAPI app with `/process` endpoint
    3. Implement `ProcessRequest` and `ProcessResponse` Pydantic models
    4. Implement `/health` endpoint
    5. Wire to DriveProcessor with WIF authentication
    6. Add request logging
  - **Files**:
    - `src/ferpa_feedback/gdrive/cloud_handler.py` (create)
  - **Done when**: FastAPI app can be run locally
  - **Verify**: `python -c "from ferpa_feedback.gdrive.cloud_handler import app; print(app.routes)"`
  - **Commit**: `feat(gdrive): add Cloud Run HTTP handler`
  - _Requirements: FR-9, AC-7.1_
  - _Design: Component 8 - Cloud Deployment_

### 4.2 Create Dockerfile for Cloud Run

- [ ] 4.2 Create Dockerfile for Cloud Run
  - **Do**:
    1. Create `Dockerfile` in project root
    2. Use Python 3.11 slim base image
    3. Install system dependencies (for spacy, etc.)
    4. Install project with `pip install -e .[cloud]`
    5. Set entrypoint to run uvicorn with cloud_handler
    6. Configure for 2GB RAM, 4 vCPU
    7. Add healthcheck
  - **Files**:
    - `Dockerfile` (create)
  - **Done when**: Docker image builds successfully
  - **Verify**: `docker build -t ferpa-gdrive . && docker run --rm ferpa-gdrive python -c "from ferpa_feedback.gdrive import DriveProcessor"`
  - **Commit**: `build(docker): add Dockerfile for Cloud Run deployment`
  - _Requirements: FR-9, NFR-11_
  - _Design: Component 8_

### 4.3 Create Cloud Build configuration

- [ ] 4.3 Create Cloud Build configuration
  - **Do**:
    1. Create `cloudbuild.yaml` in project root
    2. Add steps:
       - Build Docker image
       - Push to Container Registry
       - Deploy to Cloud Run
    3. Configure substitution variables for project ID, region
    4. Add trigger configuration for main branch
  - **Files**:
    - `cloudbuild.yaml` (create)
  - **Done when**: Cloud Build config is valid
  - **Verify**: `python -c "import yaml; yaml.safe_load(open('cloudbuild.yaml'))"`
  - **Commit**: `build(gcp): add Cloud Build configuration`
  - _Requirements: FR-9_
  - _Design: Component 8_

### 4.4 Quality Checkpoint

- [ ] 4.4 Quality Checkpoint
  - **Do**: Run all quality checks to verify cloud deployment code is correct
  - **Verify**: All commands must pass:
    - Type check: `python -m mypy src/ferpa_feedback --ignore-missing-imports`
    - Lint: `python -m ruff check src/ferpa_feedback`
    - Tests: `pytest tests/ -v`
  - **Done when**: All quality checks pass with no errors
  - **Commit**: `chore(gdrive): pass quality checkpoint` (only if fixes needed)

### 4.5 Update module exports

- [ ] 4.5 Update module exports
  - **Do**:
    1. Update `src/ferpa_feedback/gdrive/__init__.py`
    2. Export all public classes and functions:
       - Auth: `DriveAuthenticator`, `OAuth2Authenticator`, `WorkloadIdentityAuthenticator`, `create_authenticator`
       - Discovery: `FolderDiscovery`, `FolderMap`, `FolderNode`, `DriveDocument`, `FolderMetadata`
       - Downloader: `DocumentDownloader`, `DownloadedDocument`
       - Uploader: `ResultUploader`, `UploadResult`, `UploadMode`
       - Processor: `DriveProcessor`, `ProcessingSummary`, `ProcessingProgress`
       - Errors: All custom exceptions
       - Config: `DriveConfig`
    3. Add `__all__` list
  - **Files**:
    - `src/ferpa_feedback/gdrive/__init__.py` (modify)
  - **Done when**: All public APIs are exported
  - **Verify**: `python -c "from ferpa_feedback.gdrive import DriveProcessor, FolderDiscovery, DocumentDownloader, ResultUploader"`
  - **Commit**: `refactor(gdrive): update module exports`
  - _Design: File Structure_

### 4.6 Local quality check (full)

- [ ] 4.6 Local quality check
  - **Do**: Run ALL quality checks locally
  - **Verify**: All commands must pass:
    - Type check: `python -m mypy src/ferpa_feedback --ignore-missing-imports --strict`
    - Lint: `python -m ruff check src/ferpa_feedback tests`
    - Tests: `pytest tests/ -v --cov=ferpa_feedback.gdrive`
    - Build: `pip install -e . && python -c "from ferpa_feedback.gdrive import DriveProcessor"`
  - **Done when**: All commands pass with no errors
  - **Commit**: `fix(gdrive): address lint/type issues` (if fixes needed)

### 4.7 Create PR and verify CI

- [ ] 4.7 Create PR and verify CI
  - **Do**:
    1. Verify current branch is a feature branch: `git branch --show-current`
    2. If on default branch, STOP and alert user (should not happen - branch is set at startup)
    3. Push branch: `git push -u origin <branch-name>`
    4. Create PR using gh CLI: `gh pr create --title "feat(gdrive): Add Google Drive integration" --body "## Summary\n\nAdds Google Drive integration to the FERPA pipeline.\n\n## Changes\n\n- New gdrive module with auth, discovery, downloader, uploader, processor\n- BytesIO support in DocumentParser\n- gdrive-process CLI command\n- Cloud Run deployment configuration\n\n## Requirements\n\nCloses requirements: FR-1 through FR-12, FR-20\n\n## Testing\n\n- Unit tests for all gdrive components\n- Integration tests for DriveProcessor"`
    5. If gh CLI unavailable, provide URL for manual PR creation
  - **Verify**: Use gh CLI to verify CI:
    - `gh pr checks --watch` (wait for CI completion)
    - Or `gh pr checks` (poll current status)
    - All checks must show passing
  - **Done when**: All CI checks green, PR ready for review
  - **If CI fails**:
    1. Read failure details: `gh pr checks`
    2. Fix issues locally
    3. Push fixes: `git push`
    4. Re-verify: `gh pr checks --watch`

## Notes

### POC shortcuts taken
- OAuth2 authentication only (WIF added in Phase 2)
- Sequential downloads (parallel added in Phase 2)
- OVERWRITE upload mode only (VERSION added in Phase 2)
- No rate limiting in POC (added in Phase 2)
- No interactive folder selection in POC (added in Phase 2)
- Minimal error messages in POC (improved in Phase 2)

### Production TODOs
- Progress checkpointing for crash recovery (FR-15, AC-9.4)
- Changes API tracking to avoid reprocessing (FR-13, AC-9.1)
- Email notifications on completion (AC-10.5)
- Cloud Scheduler integration with idempotency (AC-7.5)
- Terraform infrastructure as code (optional)

### Dependencies between tasks
- 1.5 (downloader) depends on 1.3 (discovery) for DriveDocument type
- 1.6 (parser modification) is independent
- 1.7 (uploader) depends on 1.3 for DriveDocument type
- 1.9 (processor) depends on 1.2, 1.3, 1.5, 1.6, 1.7
- 1.10 (CLI) depends on 1.9

### Risk areas
- OAuth2 token refresh during long-running batches
- Google Docs export formatting differences
- Rate limit handling for large folder hierarchies
- BytesIO memory management for large documents
