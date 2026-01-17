---
spec: google-drive-integration
phase: research
created: 2026-01-16
---

# Research: Google Drive Integration for FERPA Pipeline

## Executive Summary

Integrating Google Drive API with the FERPA pipeline is technically feasible with moderate effort. The project already includes `google-api-python-client` and `google-auth-oauthlib` dependencies. The primary considerations are: (1) choosing between OAuth2 and Service Account authentication based on deployment model, (2) maintaining FERPA compliance when handling documents containing student PII from cloud storage, and (3) designing a robust ingestion flow that can handle shared folders, various document formats, and change detection.

## External Research

### Google Drive API Best Practices (Python)

**Official Documentation Pattern**:
- Use `google-api-python-client` library (already in project dependencies)
- Authentication via `google-auth` and `google-auth-oauthlib` (already in project dependencies)
- API v3 is current and recommended
- Sources: [Google Drive Python Quickstart](https://developers.google.com/workspace/drive/api/quickstart/python), [Merge.dev Integration Guide](https://www.merge.dev/blog/google-drive-api-python)

**Key Implementation Patterns**:
1. Track processed file IDs or timestamps to avoid duplicate ingestion
2. Use in-memory processing (e.g., `io.BytesIO`) to minimize disk I/O and improve security
3. Implement exponential backoff for rate limit handling
4. Use pagination (`nextPageToken`) for large folder listings
- Source: [Merge.dev Best Practices](https://www.merge.dev/blog/google-drive-api-python)

### Authentication: OAuth2 vs Service Account

| Criteria | OAuth2 (User Flow) | Service Account |
|----------|-------------------|-----------------|
| **Use Case** | Access user's own files | Server-to-server, app-owned data |
| **User Consent** | Required (user login prompt) | Not required |
| **Shared Folder Access** | Automatic if user has access | Must be explicitly shared with SA email |
| **Domain-Wide Delegation** | N/A | Available for Google Workspace |
| **Key Management** | Refresh tokens (expire) | JSON key files (persistent security risk) |
| **Best For** | Desktop apps, user-initiated | Automated pipelines, batch processing |

**Recommendation**: Service Account is better for this use case because:
1. Pipeline runs as automated/batch process, not user-initiated
2. Teachers share folder with service account email once, then automated
3. No user login prompts during processing
4. Sources: [Google OAuth2 Service Account](https://developers.google.com/identity/protocols/oauth2/service-account), [Daimto Guide](https://www.daimto.com/google-drive-api-with-a-service-account/)

**Security Warning**: Google strongly recommends avoiding service account keys when possible. Consider Workload Identity Federation if deploying on GCP/GKE. If keys must be used:
- Rotate regularly
- Set expiry times
- Never commit to version control
- Use environment variables or secret managers
- Source: [Google IAM Best Practices](https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)

### Handling Shared Folders and Permissions

**How Service Account Access Works**:
1. Service account has an email address (e.g., `ferpa-pipeline@project-id.iam.gserviceaccount.com`)
2. Teachers share folders with this email just like sharing with any user
3. Service account can then list and download files in shared folders
- Source: [Medium - Using Google Drive API with Service Account](https://medium.com/@matheodaly.md/using-google-drive-api-with-python-and-a-service-account-d6ae1f6456c2)

**Query Pattern for Shared Folder Files**:
```python
results = service.files().list(
    q=f"'{folder_id}' in parents",
    pageSize=100,
    fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)"
).execute()
```

**Permission Levels Required**:
- "Viewer" is sufficient for download/read operations
- "Editor" needed only if writing back results
- Recommend "Viewer" for least privilege principle

### Google Drive API Quotas and Rate Limits

| Limit Type | Value | Notes |
|------------|-------|-------|
| Queries per 60 seconds | 12,000 | Per project |
| Queries per 60 seconds per user | 12,000 | Per user context |
| Daily upload limit | 750 GB | Across all drives |
| Maximum file upload size | 5 TB | |
| Export content limit | 10 MB | For Google Docs export |

**Error Handling**:
- `403: User rate limit exceeded` - Quota violation
- `429: Too many requests` - Backend rate limit
- Implement exponential backoff with random jitter
- Maximum backoff typically 32-64 seconds
- Source: [Google Drive API Limits](https://developers.google.com/drive/api/guides/limits)

**Cost**: Google Drive API usage is free; exceeding quotas incurs no charges but blocks requests.

### Change Detection: Polling vs Push Notifications

**Option 1: Polling with Changes API**
```python
# Get start token
start_token = service.changes().getStartPageToken().execute()
# Later, check for changes
changes = service.changes().list(pageToken=stored_token).execute()
```
- Simpler to implement
- No infrastructure requirements
- Suitable for batch processing (e.g., hourly/daily runs)

**Option 2: Push Notifications (Webhooks)**
- Requires HTTPS endpoint with valid SSL certificate
- Requires domain verification
- Watch channels expire (must renew every 24 hours)
- Cannot filter by folder - must implement own filtering
- Better for near-real-time requirements
- Source: [Google Drive Push Notifications](https://developers.google.com/workspace/drive/api/guides/push)

**Recommendation**: Start with polling for simplicity. Push notifications add infrastructure complexity that may not be necessary for batch comment processing.

### Document Format Handling

**Supported Formats in Google Drive**:
- Native Google Docs (`application/vnd.google-apps.document`)
- Microsoft Word (`.docx`): `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- PDF: `application/pdf`

**Export Requirement**: Google Docs must be exported to a usable format (cannot be downloaded directly).
```python
# For Google Docs -> .docx export
request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
```

**Note**: Export is limited to 10 MB for Google Docs. Larger documents need alternative handling.
- Source: [Google Drive Export Formats](https://developers.google.com/workspace/drive/api/guides/ref-export-formats)

### FERPA Compliance Considerations for Cloud Storage

**Google Workspace for Education**:
- Google states: "Google Workspace for Education can be used in compliance with FERPA"
- More than 140 million students and faculty use it
- Source: [Google Cloud FERPA Compliance](https://cloud.google.com/security/compliance/ferpa)

**Institutional Requirements**:
- Many universities only approve institutional Google Workspace accounts, not consumer accounts
- Boston University: "Only the BU version of Google Drive is approved"
- Some institutions consider Google Drive FERPA-approved for "Confidential" but not "Restricted Use" data
- Source: [BU Google Drive Security Guide](https://www.bu.edu/tech/about/policies/google-drive-security-guide-for-ferpa/)

**Key Compliance Points for This Integration**:
1. **Data in Transit**: Google Drive API uses HTTPS - data encrypted in transit
2. **Data at Rest**: Google encrypts data at rest
3. **Access Logging**: Enable audit logging for all API calls (already in `settings.yaml`)
4. **Minimal Data Retention**: Download, process, don't cache raw documents
5. **Service Account Scope**: Use minimal scopes (`drive.readonly` preferred over `drive`)
6. **PII Handling**: Documents downloaded from Drive contain raw PII - must flow through existing FERPA gate before any external API calls (Stage 3 anonymization)

**Compliance Architecture**:
```
Google Drive (PII in cloud)
    --> Download (HTTPS, encrypted)
    --> Local Processing (Stage 0-3, PII present)
    --> FERPA Gate (anonymization)
    --> External API (Stage 4, PII-free)
```

## Codebase Analysis

### Current Stage 0 Ingestion (`stage_0_ingestion.py`)

**Current Capabilities**:
- Parses `.docx` files using `python-docx` library
- Auto-detects document format (combined header, separate header, table)
- Extracts student name, grade, and comment text
- Returns `TeacherDocument` with list of `StudentComment` objects
- Accepts `file_path: Path` as input

**Key Integration Point**:
```python
def parse_docx(self, file_path: Path, document_id: str | None = None) -> TeacherDocument:
```

**Adaptation Needed**:
- Current: Reads from local filesystem `Path`
- New: Need to support `BytesIO` stream from Google Drive download
- `python-docx` supports `Document(file_like_object)` - minimal changes needed

### Existing Dependencies (`pyproject.toml`)

**Already Included**:
```toml
"google-api-python-client>=2.100.0",
"google-auth-oauthlib>=1.1.0",
```

**Missing** (may need to add):
```toml
"google-auth>=2.0.0",  # For service account credentials (may be transitive)
```

### CLI Structure (`cli.py`)

**Current Commands**:
- `process` - Process local documents
- `warmup` - Pre-load LanguageTool
- `review` - Start review UI server

**Pattern Used**: Typer with rich progress indicators
```python
@app.command()
def process(
    input_path: Path = typer.Argument(...),
    roster: Optional[Path] = typer.Option(None),
    ...
)
```

**New Commands Needed**:
- `gdrive-auth` - Initialize/verify Google Drive credentials
- `gdrive-process` - Process documents from Google Drive folder
- `gdrive-watch` - (optional) Monitor folder for changes

### Configuration Patterns (`settings.yaml`)

**Existing Pattern**:
```yaml
section_name:
  setting1: value
  nested:
    subsetting: value
```

**Proposed Addition**:
```yaml
google_drive:
  credentials_file: "./config/service_account.json"
  # Or for OAuth:
  # client_secrets_file: "./config/client_secrets.json"
  # token_file: "./config/token.json"

  default_folder_id: null  # Can be overridden via CLI

  polling:
    enabled: true
    interval_minutes: 60

  file_types:
    - "application/vnd.google-apps.document"  # Google Docs
    - "application/vnd.openxmlformats-officedocument.wordprocessingml.document"  # .docx
```

### Pipeline Integration (`pipeline.py`)

**Current Flow**:
```
file_path --> DocumentParser.parse_docx() --> TeacherDocument
```

**Minimal Changes**:
- Add method to accept `BytesIO` stream instead of file path
- Or download to temp file, process, delete (simpler but less efficient)

### Models (`models.py`)

**Relevant Field**:
```python
class TeacherDocument(BaseModel):
    source_path: str = Field(description="Original file path or Google Drive ID")
```

Already designed to store Google Drive file ID - no changes needed.

## Related Specs

| Spec | Relevance | May Need Update |
|------|-----------|-----------------|
| `ferpa-pipeline` | High - Core pipeline this integrates with | No - additive integration |

The `ferpa-pipeline` spec completed all 42 tasks and established the foundational pipeline. This integration is purely additive - it adds a new document source (Google Drive) that feeds into the existing Stage 0 ingestion. No changes to existing pipeline stages are required.

## Feasibility Assessment

| Aspect | Assessment | Notes |
|--------|------------|-------|
| Technical Viability | **High** | Dependencies exist, API well-documented, clear integration point |
| Effort Estimate | **Medium** | 2-3 weeks for full implementation with auth, CLI, error handling |
| Risk Level | **Low-Medium** | Main risks: credential management, edge cases in doc formats |
| FERPA Compliance | **High** | Maintains existing compliance model, no new external data exposure |

### Effort Breakdown

| Component | Estimate | Notes |
|-----------|----------|-------|
| Authentication module | S (2-3 days) | Service account + optional OAuth2 |
| Google Drive client wrapper | S (2-3 days) | List, download, change tracking |
| Stage 0 adaptation | S (1-2 days) | Stream support for DocumentParser |
| CLI commands | S (2-3 days) | gdrive-auth, gdrive-process |
| Configuration | XS (1 day) | settings.yaml additions |
| Error handling & retry | S (2-3 days) | Rate limits, network errors |
| Testing | M (3-5 days) | Unit tests, integration tests with mocks |
| Documentation | S (1-2 days) | Setup guide, usage examples |

**Total: Medium (2-3 weeks)**

### Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Credential leakage | Medium | High | Use secret manager, never commit keys, document security practices |
| Google Docs export issues | Low | Medium | Test with various doc sizes, handle 10MB export limit |
| Rate limiting | Low | Low | 12,000 queries/min is generous; implement backoff anyway |
| Format variations | Medium | Medium | Test with real teacher documents from Google Docs |
| Network reliability | Low | Medium | Retry logic, graceful degradation |

## Recommendations for Requirements Phase

### Must Have (P0)
1. **Service Account Authentication with Workload Identity Federation** - GCP-native, no key files
2. **Folder Listing and File Download** - Core functionality to fetch documents
3. **Google Docs Export to .docx** - Handle native Google Docs format
4. **Integration with Existing Pipeline** - Feed downloaded docs through Stage 0-5
5. **CLI Command for Processing** - `ferpa-feedback gdrive-process --folder-id <id>`
6. **Result Upload to Google Drive** - Write processed reports back to Drive
7. **GCP Deployment** - Cloud Run or Cloud Functions with Cloud Scheduler

### Should Have (P1)
1. **Folder Structure Auto-Detection** - Crawl, detect patterns, infer hierarchy, confirm with user
2. **Progress Tracking** - Track processed files to avoid reprocessing (Changes API)
3. **Batch Processing** - Handle 240+ documents efficiently
4. **Configuration via settings.yaml** - Default folder, scheduling settings

### Could Have (P2)
1. **Push Notifications** - Real-time folder monitoring (webhook-based)
2. **Recursive Folder Processing** - Process nested subfolders
3. **Multiple Folder Support** - Process from multiple configured folders
4. **OAuth2 Alternative** - For local development/testing without GCP

### Won't Have (for initial release)
1. **Google Sheets Integration** - Focus on document comments only
2. **Google Classroom Integration** - Out of scope
3. **Real-time Collaboration** - Batch processing model only

## User Decisions (Captured)

| Question | Decision | Implications |
|----------|----------|--------------|
| **Deployment** | Google Cloud Platform (GCP) | Use Workload Identity Federation, no key management needed |
| **Authentication** | Service Account | Teachers share folders with SA email, automated processing |
| **Folder Structure** | User will provide examples | Design flexible folder traversal |
| **Processing Trigger** | Scheduled | Cloud Scheduler + Cloud Run or Cloud Functions |
| **Output Location** | Upload back to Drive | Need "Editor" permission, not just "Viewer" |
| **FERPA Compliance** | GCP is FERPA-compliant | Likely covered under existing Workspace for Education agreement |

### Remaining Open Questions

1. **Error Handling**:
   - What should happen if a document fails to process?
   - Skip and continue, or halt entire batch?

### Folder Structure (Confirmed)

```
Root (shared folder)/
├── House (×10)/
│   └── Teacher (×6 per house)/
│       ├── September Comments/   → 1 document (all students)
│       ├── Interim 1 Comments/   → 1 document (all students)
│       ├── Interim 3 Comments/   → 1 document (all students)
│       └── Sponsor Letters/      → 1 document (all students)
```

**Scale**: 10 houses × 6 teachers × 4 periods = **240 documents per cycle**

**Key Insight**: 3-level hierarchy with predictable structure. Each leaf folder contains exactly 1 document with multiple student comments.

### New Feature: Folder Structure Auto-Detection

User requested ability to automatically detect folder structure rather than hardcoding:

1. **Crawl Phase**: Recursively traverse from shared root folder
2. **Pattern Detection**: Identify hierarchy depth, naming patterns, file counts per folder
3. **Semantic Inference**: Suggest what each level represents (configurable labels)
4. **User Confirmation**: Present detected structure for approval before processing
5. **Persistence**: Save confirmed structure for future scheduled runs

This makes the system reusable for other schools with different organizational patterns.

## Sources

### Google Official Documentation
- [Google Drive Python Quickstart](https://developers.google.com/workspace/drive/api/quickstart/python)
- [OAuth2 Service Account Guide](https://developers.google.com/identity/protocols/oauth2/service-account)
- [Google Drive API Limits](https://developers.google.com/drive/api/guides/limits)
- [Push Notifications](https://developers.google.com/workspace/drive/api/guides/push)
- [Export Formats](https://developers.google.com/workspace/drive/api/guides/ref-export-formats)
- [MIME Types](https://developers.google.com/workspace/drive/api/guides/mime-types)
- [Google Cloud FERPA Compliance](https://cloud.google.com/security/compliance/ferpa)

### Security Best Practices
- [Service Account Key Best Practices](https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)
- [Workload Identity Federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation)

### Tutorials and Guides
- [Merge.dev Google Drive API Python](https://www.merge.dev/blog/google-drive-api-python)
- [Medium - Google Drive API with Service Account](https://medium.com/@matheodaly.md/using-google-drive-api-with-python-and-a-service-account-d6ae1f6456c2)
- [Daimto Service Account Guide](https://www.daimto.com/google-drive-api-with-a-service-account/)

### FERPA and Compliance
- [BU Google Drive Security Guide for FERPA](https://www.bu.edu/tech/about/policies/google-drive-security-guide-for-ferpa/)
- [Department of Education Cloud Computing FAQ](https://studentprivacy.ed.gov/resources/cloud-computing-faq)

### Codebase Files Analyzed
- `/Users/alove/FERPA Comment system.backup/src/ferpa_feedback/stage_0_ingestion.py`
- `/Users/alove/FERPA Comment system.backup/src/ferpa_feedback/cli.py`
- `/Users/alove/FERPA Comment system.backup/src/ferpa_feedback/pipeline.py`
- `/Users/alove/FERPA Comment system.backup/src/ferpa_feedback/models.py`
- `/Users/alove/FERPA Comment system.backup/pyproject.toml`
- `/Users/alove/FERPA Comment system.backup/settings.yaml`
