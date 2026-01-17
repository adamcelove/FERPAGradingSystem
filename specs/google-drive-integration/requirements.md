---
spec: google-drive-integration
phase: requirements
created: 2026-01-16
---

# Requirements: Google Drive Integration

## Goal

Enable the FERPA-compliant feedback pipeline to ingest teacher comment documents directly from Google Drive, process them through all pipeline stages (0-5), and upload results back to Drive. This eliminates manual file transfers, supports scheduled automated processing of 240+ documents per cycle, and maintains full FERPA compliance using GCP's Workload Identity Federation.

## User Stories

### US-1: Authenticate with Google Drive via Service Account

**As a** school administrator
**I want to** configure a GCP Service Account for automated Drive access
**So that** teachers can share folders with the service account email and processing happens without manual intervention

**Acceptance Criteria:**
- [ ] AC-1.1: Service Account can authenticate using Workload Identity Federation (no JSON key files)
- [ ] AC-1.2: Authentication works in Cloud Run/Cloud Functions environment
- [ ] AC-1.3: Service Account email is displayed during setup for sharing with teachers
- [ ] AC-1.4: Authentication errors provide clear, actionable error messages
- [ ] AC-1.5: OAuth2 fallback available for local development/testing

### US-2: Access Shared Google Drive Folders

**As a** system operator
**I want to** process documents from folders shared with the service account
**So that** teachers maintain ownership while granting processing access

**Acceptance Criteria:**
- [ ] AC-2.1: System can list all folders shared with the service account
- [ ] AC-2.2: System can traverse folder hierarchy (Root > House > Teacher > Period)
- [ ] AC-2.3: System correctly handles "Editor" permissions for upload capability
- [ ] AC-2.4: Access denied errors identify the specific folder and required permission
- [ ] AC-2.5: System respects Google Drive rate limits (1000 requests/100 seconds)

### US-3: Download and Convert Google Docs

**As a** pipeline operator
**I want to** download Google Docs as .docx files for processing
**So that** native Google Docs work seamlessly with the existing python-docx parser

**Acceptance Criteria:**
- [ ] AC-3.1: Native Google Docs are exported to .docx format via Drive API
- [ ] AC-3.2: Already-.docx files are downloaded directly without conversion
- [ ] AC-3.3: Downloaded files stream through BytesIO (no temp files on disk)
- [ ] AC-3.4: Conversion preserves document formatting (headers, paragraphs, tables)
- [ ] AC-3.5: Files larger than 10MB trigger a warning but continue processing

### US-4: Process Documents Through Existing Pipeline

**As a** teacher
**I want** my Google Drive comments processed through the full FERPA pipeline
**So that** I receive grammar, name-matching, and semantic feedback

**Acceptance Criteria:**
- [ ] AC-4.1: Documents from Drive flow through Stages 0-5 identically to local files
- [ ] AC-4.2: TeacherDocument.source_path contains the Google Drive file ID
- [ ] AC-4.3: Metadata (House, Teacher, Period) extracted from folder hierarchy
- [ ] AC-4.4: Processing errors for individual files do not halt batch processing
- [ ] AC-4.5: FERPA compliance maintained (anonymization verified before Stage 4)

### US-5: Upload Results Back to Google Drive

**As a** teacher
**I want** processing results uploaded to my Drive folder
**So that** I can review feedback without leaving the Google ecosystem

**Acceptance Criteria:**
- [ ] AC-5.1: Grammar reports uploaded as text files to source folder
- [ ] AC-5.2: Anonymized outputs uploaded to a designated "outputs" subfolder
- [ ] AC-5.3: Upload respects existing files (configurable: overwrite vs. version)
- [ ] AC-5.4: Failed uploads are retried up to 3 times with exponential backoff
- [ ] AC-5.5: Upload confirmation logged with file ID and parent folder

### US-6: Run Processing via CLI Command

**As a** system operator
**I want to** trigger Drive processing from the command line
**So that** I can run ad-hoc processing or integrate with external schedulers

**Acceptance Criteria:**
- [ ] AC-6.1: Command `ferpa-feedback gdrive-process --root-folder <id>` initiates processing
- [ ] AC-6.2: Progress displayed via rich console (file count, current file, stage)
- [ ] AC-6.3: `--dry-run` flag lists files without processing
- [ ] AC-6.4: `--output-local <path>` option downloads results locally instead of Drive
- [ ] AC-6.5: Exit code 0 on success, non-zero on failure with error summary
- [ ] AC-6.6: `--target-folder <name>` filters to specific sprint folders
- [ ] AC-6.7: `--list-folders` shows discovered structure and exits

### US-7: Schedule Automated Processing on GCP

**As a** school administrator
**I want** processing to run automatically on a schedule
**So that** teachers receive feedback without manual triggering

**Acceptance Criteria:**
- [ ] AC-7.1: Cloud Scheduler can trigger Cloud Run/Cloud Functions endpoint
- [ ] AC-7.2: Schedule configurable (daily, weekly, on-demand)
- [ ] AC-7.3: Invocation logs include start time, duration, document count, errors
- [ ] AC-7.4: Failed runs trigger email/webhook notification
- [ ] AC-7.5: Concurrent invocations prevented via idempotency key

### US-8: Dynamic Folder Structure Discovery

**As a** system operator
**I want** the system to discover and map folder structure at the start of each ingestion
**So that** the system adapts to any school's organization without hardcoded assumptions

**Acceptance Criteria:**
- [ ] AC-8.1: `discover_structure(root_folder_id)` function crawls and returns a folder tree map
- [ ] AC-8.2: Map includes folder ID, name, depth level, parent ID, and child count for each node
- [ ] AC-8.3: Discovery runs at the start of each processing run (not cached between runs)
- [ ] AC-8.4: Discovery completes within 30 seconds for up to 500 folders
- [ ] AC-8.5: Map is logged/exported as JSON for debugging and auditing
- [ ] AC-8.6: System identifies "leaf folders" (folders containing documents, no subfolders) as processing targets

### US-11: Sprint/Folder Selection for Processing

**As a** system operator
**I want** to select which folder (sprint) to process from the discovered structure
**So that** I can run the pipeline on specific comment cycles (e.g., "September Comments" only)

**Acceptance Criteria:**
- [ ] AC-11.1: CLI flag `--target-folder <name-or-id>` filters processing to matching folders
- [ ] AC-11.2: Pattern matching supported (e.g., `--target-folder "Interim*"` matches "Interim 1", "Interim 3")
- [ ] AC-11.3: Interactive mode lists discovered folders and prompts for selection
- [ ] AC-11.4: Multiple folders selectable (e.g., `--target-folder "September" --target-folder "Interim 1"`)
- [ ] AC-11.5: `--list-folders` flag shows discovered structure without processing
- [ ] AC-11.6: Default behavior (no flag) processes ALL leaf folders containing documents

### US-9: Track Processing Progress to Avoid Reprocessing

**As a** system operator
**I want** the system to track which files have been processed
**So that** subsequent runs skip unchanged documents

**Acceptance Criteria:**
- [ ] AC-9.1: Drive Changes API used to detect modified files since last run
- [ ] AC-9.2: Processing checkpoint stored with file ID, version, and timestamp
- [ ] AC-9.3: `--force` flag bypasses checkpoint and reprocesses all files
- [ ] AC-9.4: Checkpoint survives Cloud Run/Functions cold starts (stored in GCS)
- [ ] AC-9.5: Checkpoint includes hash verification to detect out-of-band changes

### US-10: Handle Batch Processing at Scale

**As a** school administrator
**I want** the system to efficiently process 240+ documents per cycle
**So that** all teacher comments are processed within the scheduling window

**Acceptance Criteria:**
- [ ] AC-10.1: Batch processing completes 240 documents in under 60 minutes
- [ ] AC-10.2: Parallel downloads (configurable, default 5 concurrent)
- [ ] AC-10.3: Memory usage stays under 2GB for standard Cloud Run instances
- [ ] AC-10.4: Progress persisted every 10 documents for crash recovery
- [ ] AC-10.5: Processing summary emailed to administrator upon completion

## Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-1 | Authenticate using GCP Workload Identity Federation | P0 (Must Have) | AC-1.1, AC-1.2 |
| FR-2 | List and traverse shared Drive folders | P0 (Must Have) | AC-2.1, AC-2.2 |
| FR-3 | Export Google Docs to .docx format | P0 (Must Have) | AC-3.1, AC-3.2, AC-3.4 |
| FR-4 | Stream files via BytesIO without disk writes | P0 (Must Have) | AC-3.3 |
| FR-5 | Integrate with existing pipeline stages 0-5 | P0 (Must Have) | AC-4.1, AC-4.5 |
| FR-6 | Extract metadata from folder hierarchy | P0 (Must Have) | AC-4.3 |
| FR-7 | Upload results to Google Drive | P0 (Must Have) | AC-5.1, AC-5.2 |
| FR-8 | CLI command for processing | P0 (Must Have) | AC-6.1, AC-6.2, AC-6.5 |
| FR-9 | Deploy to Cloud Run or Cloud Functions | P0 (Must Have) | AC-7.1 |
| FR-10 | Cloud Scheduler integration | P0 (Must Have) | AC-7.2, AC-7.3 |
| FR-11 | Dynamic folder structure discovery at each run | P0 (Must Have) | AC-8.1, AC-8.2, AC-8.3, AC-8.6 |
| FR-12 | Sprint/folder selection via CLI | P0 (Must Have) | AC-11.1, AC-11.2, AC-11.4 |
| FR-20 | List folders command (`--list-folders`) | P0 (Must Have) | AC-11.5 |
| FR-21 | Interactive folder selection mode | P1 (Should Have) | AC-11.3 |
| FR-13 | Track processed files via Changes API | P1 (Should Have) | AC-9.1, AC-9.2 |
| FR-14 | Batch processing with parallel downloads | P1 (Should Have) | AC-10.1, AC-10.2 |
| FR-15 | Persist progress checkpoints | P1 (Should Have) | AC-9.4, AC-10.4 |
| FR-16 | OAuth2 authentication for local development | P2 (Could Have) | AC-1.5 |
| FR-17 | Dry-run mode | P2 (Could Have) | AC-6.3 |
| FR-18 | Push notifications for real-time monitoring | P2 (Could Have) | Webhook-based folder monitoring |
| FR-19 | Multiple root folder support | P2 (Could Have) | Process from multiple configured folders |

## Non-Functional Requirements

| ID | Requirement | Metric | Target |
|----|-------------|--------|--------|
| NFR-1 | Performance | Processing time for 240 documents | Under 60 minutes |
| NFR-2 | Performance | Cold start latency | Under 30 seconds |
| NFR-3 | Scalability | Concurrent document downloads | 5 parallel (configurable to 10) |
| NFR-4 | Reliability | Error recovery | Auto-retry 3x with exponential backoff |
| NFR-5 | Reliability | Crash recovery | Resume from last checkpoint |
| NFR-6 | Security | Authentication | No JSON key files; Workload Identity only |
| NFR-7 | Security | Data in transit | TLS 1.2+ for all Drive API calls |
| NFR-8 | Compliance | FERPA | All PII anonymized before Stage 4 API calls |
| NFR-9 | Compliance | Audit logging | All Drive operations logged with timestamps |
| NFR-10 | Availability | Scheduled job success rate | 99% over 30-day window |
| NFR-11 | Memory | Cloud Run instance | Under 2GB RAM |
| NFR-12 | API Limits | Google Drive API | Respect 1000 req/100sec quota |
| NFR-13 | Folder Discovery | Time to map 500 folders | Under 30 seconds |
| NFR-14 | Flexibility | Folder structure assumptions | Zero hardcoded paths or hierarchy assumptions |

## Glossary

- **Workload Identity Federation**: GCP feature allowing services to authenticate without storing service account keys, using short-lived tokens instead
- **Service Account**: A Google Cloud identity used by applications (not humans) to authenticate and authorize API calls
- **Changes API**: Google Drive API endpoint that returns a list of files modified since a given checkpoint token
- **BytesIO**: Python in-memory file-like object that avoids writing data to disk
- **FERPA Gate**: The anonymization step (Stage 3) that ensures no PII passes to external APIs
- **House**: A grouping of teachers within the school's organizational structure (10 total)
- **Period/Sprint**: A comment cycle such as "September Comments", "Interim 1", "Sponsor Letters" - used interchangeably
- **Folder Map**: JSON structure representing the discovered folder hierarchy with IDs, names, depths, and relationships
- **Leaf Folder**: A folder containing documents but no subfolders - the target for document processing
- **Target Folder**: A user-selected folder (by name or pattern) to filter processing scope
- **Cloud Run**: GCP serverless container platform for running HTTP-triggered workloads
- **Cloud Functions**: GCP serverless functions for event-driven processing
- **Cloud Scheduler**: GCP managed cron service for triggering jobs on a schedule

## Out of Scope

- Real-time collaborative editing detection (only batch processing)
- Google Sheets integration (only Google Docs/.docx)
- Multi-tenancy (single school per deployment)
- Custom authentication providers (GCP only)
- Google Drive desktop app integration
- Mobile app for teachers
- Modifying source documents (read-only processing, results to separate files)
- Processing of images, PDFs, or non-document file types
- Integration with Student Information Systems (SIS)
- Parent notification systems
- Grade submission workflows

## Dependencies

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| Google Drive API | External Service | API changes, quota limits | Pin API version, implement rate limiting |
| GCP Workload Identity | Authentication | Configuration complexity | Detailed setup documentation, fallback OAuth2 |
| Existing pipeline (Stages 0-5) | Internal | Breaking changes | Interface contract, integration tests |
| python-docx | Library | .docx compatibility | Already proven with local files |
| Cloud Run/Functions | Platform | Cold starts, timeouts | Warm-up, chunked processing |
| Cloud Scheduler | Platform | Missed triggers | Alerting, manual trigger option |
| Institutional Google Workspace | External | Access policies | Work with IT for service account approval |
| FERPA BAA with Google | Compliance | Legal requirement | Verify existing Workspace for Education agreement |

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Teachers forget to share folders | High | Documents not processed | Email reminder automation, dashboard showing unshared folders |
| Google Docs export loses formatting | Medium | Parser fails | Test with representative documents, fallback to text-only |
| API quota exceeded | Low | Processing delayed | Exponential backoff, spread processing across time |
| Service account key leakage | N/A | N/A | Using Workload Identity eliminates key files |
| Large files exceed memory | Low | Cloud Run crash | Stream processing, file size limits |
| Concurrent schedule runs | Medium | Duplicate processing | Idempotency key, distributed lock |

## Success Criteria

1. **Functional**: 240 documents processed end-to-end from Drive folders with results uploaded, within 60 minutes
2. **Reliability**: 3 consecutive scheduled runs complete without manual intervention
3. **Adoption**: Teachers successfully share folders and receive feedback within one comment cycle
4. **Compliance**: Security audit confirms FERPA controls maintained with Drive integration
5. **Flexibility**: System works on ANY folder structure without code changes - just point at root folder
6. **Sprint Selection**: Operator can process just "September Comments" across all teachers with single command
7. **Discovery**: Folder structure mapped and displayed in under 30 seconds
8. **Performance**: Cold start to first document processed in under 45 seconds
