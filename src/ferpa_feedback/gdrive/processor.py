"""Google Drive document processor orchestrator.

This module provides the DriveProcessor class that orchestrates the complete
workflow for processing documents from Google Drive through the FERPA pipeline.

The processor coordinates:
1. Folder discovery
2. Pattern-based filtering
3. Document download
4. Pipeline processing
5. Result upload

Example:
    from ferpa_feedback.gdrive.processor import DriveProcessor
    from ferpa_feedback.gdrive.auth import OAuth2Authenticator
    from ferpa_feedback.pipeline import FeedbackPipeline

    auth = OAuth2Authenticator(client_secrets_path)
    pipeline = FeedbackPipeline()
    processor = DriveProcessor(auth, pipeline)

    # List folders without processing
    folder_map = processor.list_folders("root_folder_id")

    # Process documents
    summary = processor.process("root_folder_id", target_patterns=["September*"])
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog

from ferpa_feedback.gdrive.auth import DriveAuthenticator
from ferpa_feedback.gdrive.config import DriveConfig
from ferpa_feedback.gdrive.discovery import (
    DriveDocument,
    FolderDiscovery,
    FolderMap,
    FolderMetadata,
    FolderNode,
)
from ferpa_feedback.gdrive.downloader import DocumentDownloader, DownloadedDocument
from ferpa_feedback.gdrive.errors import DownloadError, UploadError
from ferpa_feedback.gdrive.uploader import ResultUploader, UploadMode
from ferpa_feedback.pipeline import FeedbackPipeline

logger = structlog.get_logger()


@dataclass
class ProcessingProgress:
    """Progress tracking for batch processing.

    This dataclass tracks the current state of a batch processing operation,
    useful for progress callbacks and monitoring.

    Attributes:
        total_documents: Total number of documents to process.
        processed_documents: Number of documents processed so far.
        successful_documents: Number of documents processed successfully.
        failed_documents: Number of documents that failed processing.
        current_document: Name of the document currently being processed.
        current_stage: Name of the current processing stage.
    """

    total_documents: int = 0
    processed_documents: int = 0
    successful_documents: int = 0
    failed_documents: int = 0
    current_document: Optional[str] = None
    current_stage: Optional[str] = None


@dataclass
class ProcessingSummary:
    """Summary of a processing run.

    This dataclass provides a complete summary of a batch processing operation,
    including timing, counts, and any errors encountered.

    Attributes:
        started_at: When processing started.
        completed_at: When processing completed.
        folder_map: The discovered folder structure.
        target_folders: List of folders that were processed.
        total_documents: Total number of documents found.
        successful: Number of documents successfully processed.
        failed: Number of documents that failed processing.
        grammar_issues_found: Total grammar issues found across all documents.
        pii_instances_replaced: Total PII instances anonymized.
        uploads_completed: Number of successful uploads.
        errors: List of error details for debugging.
    """

    started_at: datetime
    completed_at: datetime
    folder_map: FolderMap
    target_folders: List[FolderNode]
    total_documents: int
    successful: int
    failed: int
    grammar_issues_found: int
    pii_instances_replaced: int
    uploads_completed: int
    errors: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        """Total processing duration in seconds."""
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def success_rate(self) -> float:
        """Percentage of documents processed successfully."""
        if self.total_documents == 0:
            return 0.0
        return (self.successful / self.total_documents) * 100


class DriveProcessor:
    """Orchestrates Google Drive document processing.

    This class coordinates the complete workflow for processing documents
    from Google Drive through the FERPA feedback pipeline:

    1. Authenticate with Google Drive API
    2. Discover folder structure from root folder
    3. Filter folders by pattern (optional)
    4. Download documents as BytesIO streams
    5. Process through FeedbackPipeline stages 0-5
    6. Upload results back to Drive

    The processor implements continue-on-error for batch processing, ensuring
    that one failed document doesn't stop the entire batch.

    Example:
        processor = DriveProcessor(authenticator, pipeline, config)

        # List folders without processing
        folder_map = processor.list_folders("1abc123xyz")
        folder_map.print_tree()

        # Process with pattern filter
        summary = processor.process(
            root_folder_id="1abc123xyz",
            target_patterns=["September*", "Interim*"],
        )
        print(f"Processed {summary.successful} of {summary.total_documents} documents")
    """

    def __init__(
        self,
        authenticator: DriveAuthenticator,
        pipeline: FeedbackPipeline,
        config: Optional[DriveConfig] = None,
    ) -> None:
        """Initialize the processor.

        Args:
            authenticator: Drive authentication provider.
            pipeline: Configured FeedbackPipeline for document processing.
            config: Optional Drive-specific configuration. Uses defaults if not provided.
        """
        self._authenticator = authenticator
        self._pipeline = pipeline
        self._config = config or DriveConfig()

        # Get authenticated service
        self._service = authenticator.get_service()

        # Initialize components
        self._discovery = FolderDiscovery(
            service=self._service,
            rate_limiter=None,  # Rate limiting added in Phase 2
        )
        self._downloader = DocumentDownloader(
            service=self._service,
            rate_limiter=None,
            max_concurrent=self._config.processing.max_concurrent_downloads,
        )
        self._uploader = ResultUploader(
            service=self._service,
            rate_limiter=None,
            upload_mode=UploadMode.OVERWRITE,  # POC uses OVERWRITE only
            max_retries=self._config.upload.max_retries,
        )

        logger.info(
            "drive_processor_initialized",
            auth_email=authenticator.service_account_email,
        )

    def list_folders(
        self,
        root_folder_id: str,
    ) -> FolderMap:
        """Discover and return folder structure without processing.

        This method is used by the --list-folders CLI option to display
        the folder hierarchy without actually processing any documents.

        Args:
            root_folder_id: Google Drive folder ID to start from.

        Returns:
            FolderMap containing the complete folder structure.

        Raises:
            DriveAccessError: If root folder is not accessible.
            DiscoveryTimeoutError: If discovery exceeds timeout.
        """
        logger.info("listing_folders", root_folder_id=root_folder_id)

        folder_map = self._discovery.discover_structure(
            root_folder_id=root_folder_id,
            max_depth=self._config.processing.max_folder_depth,
            timeout_seconds=float(self._config.processing.discovery_timeout_seconds),
        )

        logger.info(
            "folder_discovery_complete",
            total_folders=folder_map.total_folders,
            total_documents=folder_map.total_documents,
            leaf_folders=len(folder_map.get_leaf_folders()),
        )

        return folder_map

    def process(
        self,
        root_folder_id: str,
        target_patterns: Optional[List[str]] = None,
        dry_run: bool = False,
        output_local: Optional[Path] = None,
        progress_callback: Optional[Callable[[ProcessingProgress], None]] = None,
    ) -> ProcessingSummary:
        """Execute full processing workflow.

        This method orchestrates the complete processing flow:
        1. Discover folder structure (fresh each run)
        2. Filter to target folders (if patterns provided)
        3. Download documents as BytesIO
        4. Process through pipeline stages 0-5
        5. Upload results to Drive (unless output_local specified)

        The processor implements continue-on-error: if one document fails,
        processing continues with the remaining documents.

        Args:
            root_folder_id: Root folder to process.
            target_patterns: Optional folder name patterns to filter.
                Supports glob patterns like "September*", "*Interim*".
            dry_run: If True, list files without processing.
            output_local: If set, write results locally instead of Drive.
            progress_callback: Optional callback for progress updates.

        Returns:
            ProcessingSummary with statistics and any errors.

        Raises:
            DriveAccessError: If root folder is not accessible.
            DiscoveryTimeoutError: If discovery exceeds timeout.
        """
        started_at = datetime.now()
        errors: List[Dict[str, Any]] = []

        logger.info(
            "processing_started",
            root_folder_id=root_folder_id,
            target_patterns=target_patterns,
            dry_run=dry_run,
            output_local=str(output_local) if output_local else None,
        )

        # Step 1: Discover folder structure
        folder_map = self.list_folders(root_folder_id)

        # Step 2: Filter to target folders
        if target_patterns:
            target_folders = folder_map.filter_by_patterns(target_patterns)
            logger.info(
                "folders_filtered",
                patterns=target_patterns,
                matched_folders=len(target_folders),
            )
        else:
            target_folders = folder_map.get_leaf_folders()
            logger.info("processing_all_leaf_folders", count=len(target_folders))

        # Collect all documents from target folders
        all_documents: List[tuple[DriveDocument, FolderNode]] = []
        for folder in target_folders:
            for doc in folder.documents:
                all_documents.append((doc, folder))

        total_documents = len(all_documents)

        logger.info("documents_to_process", count=total_documents)

        # Initialize progress tracking
        progress = ProcessingProgress(total_documents=total_documents)

        # Dry run: just report what would be processed
        if dry_run:
            logger.info("dry_run_complete", documents=total_documents)
            return ProcessingSummary(
                started_at=started_at,
                completed_at=datetime.now(),
                folder_map=folder_map,
                target_folders=target_folders,
                total_documents=total_documents,
                successful=0,
                failed=0,
                grammar_issues_found=0,
                pii_instances_replaced=0,
                uploads_completed=0,
                errors=[],
            )

        # Step 3-5: Process each document
        successful = 0
        failed = 0
        grammar_issues_found = 0
        pii_instances_replaced = 0
        uploads_completed = 0

        for doc, folder in all_documents:
            progress.current_document = doc.name
            progress.current_stage = "downloading"

            if progress_callback:
                progress_callback(progress)

            try:
                # Step 3: Download document
                logger.info("downloading_document", doc_name=doc.name, doc_id=doc.id)
                downloaded = self._downloader.download_document(doc)

                # Extract metadata from folder path
                metadata = self._discovery.extract_metadata(folder)

                # Step 4: Process through pipeline
                progress.current_stage = "processing"
                if progress_callback:
                    progress_callback(progress)

                processed_doc = self._process_document(
                    downloaded=downloaded,
                    metadata=metadata,
                )

                # Track statistics
                grammar_issues_found += processed_doc.grammar_issues_count
                # Note: PII instances tracking would require changes to anonymization processor
                # For POC, we don't track this

                # Step 5: Upload results or save locally
                progress.current_stage = "uploading"
                if progress_callback:
                    progress_callback(progress)

                if output_local:
                    # Write to local filesystem
                    self._save_results_local(
                        processed_doc=processed_doc,
                        original_doc=doc,
                        metadata=metadata,
                        output_dir=output_local,
                    )
                    uploads_completed += 1
                else:
                    # Upload to Drive
                    upload_success = self._upload_results(
                        processed_doc=processed_doc,
                        original_doc=doc,
                        folder=folder,
                    )
                    if upload_success:
                        uploads_completed += 1

                successful += 1
                logger.info(
                    "document_processed_successfully",
                    doc_name=doc.name,
                    grammar_issues=processed_doc.grammar_issues_count,
                )

            except DownloadError as e:
                failed += 1
                error_info = {
                    "document": doc.name,
                    "document_id": doc.id,
                    "stage": "download",
                    "error": str(e),
                }
                errors.append(error_info)
                logger.error(
                    "document_download_failed",
                    doc_name=doc.name,
                    error=str(e),
                )

            except Exception as e:
                failed += 1
                error_info = {
                    "document": doc.name,
                    "document_id": doc.id,
                    "stage": progress.current_stage,
                    "error": str(e),
                }
                errors.append(error_info)
                logger.error(
                    "document_processing_failed",
                    doc_name=doc.name,
                    stage=progress.current_stage,
                    error=str(e),
                )

            # Update progress
            progress.processed_documents += 1
            progress.successful_documents = successful
            progress.failed_documents = failed

            if progress_callback:
                progress_callback(progress)

        completed_at = datetime.now()

        logger.info(
            "processing_complete",
            successful=successful,
            failed=failed,
            duration_seconds=(completed_at - started_at).total_seconds(),
        )

        return ProcessingSummary(
            started_at=started_at,
            completed_at=completed_at,
            folder_map=folder_map,
            target_folders=target_folders,
            total_documents=total_documents,
            successful=successful,
            failed=failed,
            grammar_issues_found=grammar_issues_found,
            pii_instances_replaced=pii_instances_replaced,
            uploads_completed=uploads_completed,
            errors=errors,
        )

    def _process_document(
        self,
        downloaded: DownloadedDocument,
        metadata: FolderMetadata,
    ) -> Any:
        """Process a downloaded document through the pipeline.

        Args:
            downloaded: Downloaded document with BytesIO content.
            metadata: Folder metadata for context.

        Returns:
            Processed TeacherDocument.
        """
        # Reset stream position
        downloaded.content.seek(0)

        # Build metadata dict for parser
        parse_metadata = {
            "drive_file_id": downloaded.drive_document.id,
            "house": metadata.house,
            "teacher": metadata.teacher,
            "period": metadata.period,
            "source_path": metadata.raw_path,
        }

        # Parse document using pipeline's parser (supports BytesIO)
        document = self._pipeline.document_parser.parse_docx(
            source=downloaded.content,
            document_id=downloaded.drive_document.id,
            metadata=parse_metadata,
        )

        # Run through pipeline stages
        # Stage 1: Grammar check
        if self._pipeline.grammar_checker:
            document = self._pipeline.grammar_checker.check_document(document)

        # Stage 2: Name verification
        if self._pipeline.name_processor:
            document = self._pipeline.name_processor.process_document(document)

        # Stage 3: Anonymization
        document = self._pipeline.anonymization_processor.process_document(document)

        # Verify anonymization
        verification = self._pipeline.anonymization_processor.verify_anonymization(document)
        if not verification["is_clean"]:
            logger.warning(
                "anonymization_verification_failed",
                doc_id=downloaded.drive_document.id,
                issues=verification.get("issues", []),
            )

        return document

    def _upload_results(
        self,
        processed_doc: Any,
        original_doc: DriveDocument,
        folder: FolderNode,
    ) -> bool:
        """Upload processing results to Google Drive.

        Args:
            processed_doc: Processed TeacherDocument.
            original_doc: Original DriveDocument metadata.
            folder: Parent folder for uploads.

        Returns:
            True if upload was successful.
        """
        try:
            # Ensure output folder exists
            output_folder_id = self._uploader.ensure_output_folder(
                parent_folder_id=folder.id,
                folder_name=self._config.upload.output_folder_name,
            )

            # Build grammar report content
            grammar_report = self._build_grammar_report(processed_doc)

            # Upload grammar report
            upload_result = self._uploader.upload_grammar_report(
                report_content=grammar_report,
                original_doc=original_doc,
                folder_id=output_folder_id,
            )

            if not upload_result.success:
                logger.warning(
                    "grammar_report_upload_failed",
                    doc_name=original_doc.name,
                    error=upload_result.error,
                )
                return False

            # Build anonymized output
            anonymized_content = self._build_anonymized_output(processed_doc)

            # Upload anonymized output
            upload_result = self._uploader.upload_anonymized_output(
                content=anonymized_content,
                original_doc=original_doc,
                output_folder_id=output_folder_id,
            )

            if not upload_result.success:
                logger.warning(
                    "anonymized_output_upload_failed",
                    doc_name=original_doc.name,
                    error=upload_result.error,
                )
                return False

            return True

        except UploadError as e:
            logger.error(
                "upload_failed",
                doc_name=original_doc.name,
                error=str(e),
            )
            return False

    def _save_results_local(
        self,
        processed_doc: Any,
        original_doc: DriveDocument,
        metadata: FolderMetadata,
        output_dir: Path,
    ) -> None:
        """Save processing results to local filesystem.

        Args:
            processed_doc: Processed TeacherDocument.
            original_doc: Original DriveDocument metadata.
            metadata: Folder metadata for context.
            output_dir: Directory to save results.
        """
        # Create output directory structure
        output_path = output_dir / (metadata.raw_path.replace("/", "_") if metadata.raw_path else "output")
        output_path.mkdir(parents=True, exist_ok=True)

        # Get base name for output files
        base_name = original_doc.name
        if "." in base_name:
            base_name = base_name.rsplit(".", 1)[0]

        # Save grammar report
        grammar_report = self._build_grammar_report(processed_doc)
        grammar_path = output_path / f"{base_name}_grammar_report.txt"
        grammar_path.write_text(grammar_report, encoding="utf-8")

        # Save anonymized output
        anonymized_content = self._build_anonymized_output(processed_doc)
        anonymized_path = output_path / f"{base_name}_anonymized.txt"
        anonymized_path.write_text(anonymized_content, encoding="utf-8")

        logger.info(
            "results_saved_locally",
            grammar_report=str(grammar_path),
            anonymized_output=str(anonymized_path),
        )

    def _build_grammar_report(self, processed_doc: Any) -> str:
        """Build a grammar report from processed document.

        Args:
            processed_doc: Processed TeacherDocument.

        Returns:
            Grammar report as string.
        """
        lines = [
            "GRAMMAR REPORT",
            "=" * 60,
            f"Document: {processed_doc.source_path}",
            f"Total Comments: {len(processed_doc.comments)}",
            f"Grammar Issues Found: {processed_doc.grammar_issues_count}",
            "",
        ]

        for comment in processed_doc.comments:
            if comment.grammar_issues:
                lines.append(f"--- {comment.student_name} ---")
                for issue in comment.grammar_issues:
                    lines.append(f"  - {issue}")
                lines.append("")

        if processed_doc.grammar_issues_count == 0:
            lines.append("No grammar issues found.")

        return "\n".join(lines)

    def _build_anonymized_output(self, processed_doc: Any) -> str:
        """Build anonymized output from processed document.

        Args:
            processed_doc: Processed TeacherDocument.

        Returns:
            Anonymized content as string.
        """
        lines = [
            "ANONYMIZED OUTPUT",
            "=" * 60,
            f"Document: {processed_doc.source_path}",
            f"Total Comments: {len(processed_doc.comments)}",
            "",
        ]

        for comment in processed_doc.comments:
            lines.append(f"--- Comment {comment.section_index} ---")
            # Use anonymized text if available, otherwise original
            text = comment.anonymized_text if comment.anonymized_text else comment.comment_text
            lines.append(text)
            lines.append("")

        return "\n".join(lines)
