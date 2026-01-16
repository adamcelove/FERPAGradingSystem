---
spec: ferpa-pipeline
phase: requirements
created: 2026-01-15
---

# Requirements: FERPA Pipeline Improvements

## Goal

Stabilize and enhance the FERPA-compliant teacher comment feedback pipeline by resolving critical structural issues that prevent the system from running, implementing missing stages, and optimizing PII detection accuracy to ensure regulatory compliance while improving system reliability and performance.

## User Stories

### US-1: Fix Project Structure for Runnable Pipeline

**As a** developer or operations engineer
**I want to** run the pipeline without import errors
**So that** I can process teacher comment documents end-to-end

**Acceptance Criteria:**
- [ ] AC-1.1: Pipeline imports resolve correctly when running `python -m ferpa_feedback.pipeline`
- [ ] AC-1.2: All module paths in `pyproject.toml` match actual file locations
- [ ] AC-1.3: Running `pip install -e .` followed by `ferpa-feedback --help` succeeds without ImportError
- [ ] AC-1.4: Unit tests pass when run with `pytest tests/`

### US-2: Implement Missing Stage 2 (Name Verification)

**As a** teacher document reviewer
**I want to** detect when a comment mentions a different student than the one it is assigned to
**So that** comments do not get sent to the wrong student's report

**Acceptance Criteria:**
- [ ] AC-2.1: Stage 2 module exists at the expected import path `ferpa_feedback.stage_2_names`
- [ ] AC-2.2: Stage 2 extracts names from comment text using NER (GLiNER or spaCy)
- [ ] AC-2.3: Extracted names are matched against expected student using fuzzy matching (rapidfuzz)
- [ ] AC-2.4: Name mismatches are flagged with confidence scores (HIGH/MEDIUM/LOW)
- [ ] AC-2.5: Match threshold is configurable (default 85% similarity)
- [ ] AC-2.6: Handles edge cases: nicknames, hyphenated names, middle names, apostrophes

### US-3: Unify StudentComment Model Definition

**As a** developer maintaining the codebase
**I want to** have a single authoritative StudentComment definition
**So that** data flows consistently through all pipeline stages without type errors

**Acceptance Criteria:**
- [ ] AC-3.1: Single `StudentComment` class exists (Pydantic model in `models.py`)
- [ ] AC-3.2: Stage 0 ingestion outputs the unified `StudentComment` type
- [ ] AC-3.3: All pipeline stages accept and return the same `StudentComment` type
- [ ] AC-3.4: Type checking passes with `mypy --strict`

### US-4: Optimize Presidio PII Detection Configuration

**As a** compliance officer
**I want to** maximize recall of PII detection before external API calls
**So that** no student information is inadvertently sent to third parties

**Acceptance Criteria:**
- [ ] AC-4.1: Presidio AnalyzerEngine configured with educational domain recognizers
- [ ] AC-4.2: Custom recognizers added for: student IDs, grade levels, school-specific terms
- [ ] AC-4.3: Detection threshold tuned for recall over precision (configurable, default 0.3)
- [ ] AC-4.4: PII detection achieves minimum 95% recall on test corpus of educational comments
- [ ] AC-4.5: False positive rate documented and under 30%

### US-5: Implement Stage 4 (Semantic Analysis)

**As a** teacher or administrator
**I want to** receive feedback on comment quality (completeness and grade consistency)
**So that** I can improve comments before they go to students

**Acceptance Criteria:**
- [ ] AC-5.1: Stage 4 module exists at `ferpa_feedback.stage_4_semantic`
- [ ] AC-5.2: Completeness analysis evaluates: specificity, actionability, evidence, length, tone
- [ ] AC-5.3: Grade-comment consistency analysis detects sentiment misalignment
- [ ] AC-5.4: All API calls use only anonymized text (enforced by FERPA gate)
- [ ] AC-5.5: API calls include ZDR (Zero Data Retention) headers if supported
- [ ] AC-5.6: Results are stored in `CompletenessResult` and `ConsistencyResult` models
- [ ] AC-5.7: Stage gracefully handles API rate limits and errors with retry logic

### US-6: Implement Stage 5 (Human Review Queue)

**As a** teacher or administrator
**I want to** review flagged comments in a web interface
**So that** I can approve, reject, or modify suggested changes before finalizing

**Acceptance Criteria:**
- [ ] AC-6.1: Stage 5 module exists at `ferpa_feedback.stage_5_review`
- [ ] AC-6.2: Web interface displays de-anonymized comments for review
- [ ] AC-6.3: Users can accept, reject, or modify suggestions per comment
- [ ] AC-6.4: Review decisions are logged with timestamp and reviewer identity
- [ ] AC-6.5: Export capability for reviewed/approved comments

### US-7: Reduce LanguageTool Cold Start Latency

**As a** user processing documents
**I want to** avoid long delays when starting the pipeline
**So that** I can iterate quickly when reviewing comments

**Acceptance Criteria:**
- [ ] AC-7.1: LanguageTool lazy loading prevents blocking on pipeline initialization
- [ ] AC-7.2: Optional warm-up command preloads LanguageTool server
- [ ] AC-7.3: Progress indicator shows when LanguageTool is loading
- [ ] AC-7.4: Cold start under 15 seconds on standard hardware (documented baseline)

### US-8: Clean Up Unused Dependencies

**As a** developer or security reviewer
**I want to** remove unused dependencies from pyproject.toml
**So that** the attack surface is minimized and install times are reduced

**Acceptance Criteria:**
- [ ] AC-8.1: All listed dependencies are actively imported somewhere in the codebase
- [ ] AC-8.2: GLiNER dependency is either used by Stage 2 or removed
- [ ] AC-8.3: rapidfuzz dependency is either used by Stage 2 or removed
- [ ] AC-8.4: Dependency audit document lists each dependency with its purpose

---

## Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-1 | Restructure project to match pyproject.toml package layout (`src/ferpa_feedback/`) | P0 (Critical) | Imports resolve; CLI runs |
| FR-2 | Create `stage_2_names` module with `NameVerificationProcessor` and `create_name_processor` factory | P0 (Critical) | Module exists; no ImportError |
| FR-3 | Consolidate `StudentComment` to single Pydantic definition in `models.py` | P0 (Critical) | Type checking passes |
| FR-4 | Implement NER-based name extraction using GLiNER or spaCy in Stage 2 | P1 (High) | Names extracted with confidence scores |
| FR-5 | Implement fuzzy name matching using rapidfuzz in Stage 2 | P1 (High) | Threshold-based matching with configurable similarity |
| FR-6 | Add custom Presidio recognizers for educational PII patterns | P1 (High) | Student IDs, grade levels detected |
| FR-7 | Configure Presidio thresholds optimized for recall | P1 (High) | 95%+ recall on test corpus |
| FR-8 | Create `stage_4_semantic` module with completeness analysis | P1 (High) | Analysis results populate model fields |
| FR-9 | Create `stage_4_semantic` module with grade-consistency analysis | P1 (High) | Sentiment mismatch detection works |
| FR-10 | Enforce FERPA gate before all Stage 4 API calls | P0 (Critical) | No raw PII reaches API |
| FR-11 | Create `stage_5_review` module with review queue logic | P2 (Medium) | Comments queued with status tracking |
| FR-12 | Create basic web UI for Stage 5 using FastAPI | P2 (Medium) | Web interface accessible at localhost |
| FR-13 | Implement de-anonymization for human review display | P1 (High) | Original names restored for reviewer |
| FR-14 | Add warm-up command for LanguageTool preloading | P3 (Low) | CLI command pre-starts Java server |
| FR-15 | Document and verify all dependencies in pyproject.toml | P2 (Medium) | Audit list complete |
| FR-16 | Handle name edge cases: nicknames, hyphenated names, apostrophes | P1 (High) | Test cases pass for O'Brien, McDonald, hyphenated |

---

## Non-Functional Requirements

| ID | Requirement | Metric | Target |
|----|-------------|--------|--------|
| NFR-1 | PII Detection Recall | Recall rate on test corpus | >= 95% |
| NFR-2 | PII Detection Precision | Precision rate (for tuning) | >= 70% |
| NFR-3 | Pipeline Startup Time | Time to first document processed | <= 30 seconds (cold), <= 2 seconds (warm) |
| NFR-4 | LanguageTool Cold Start | Time to LanguageTool ready | <= 15 seconds |
| NFR-5 | Document Processing Throughput | Comments processed per second | >= 10 comments/second (local stages) |
| NFR-6 | FERPA Compliance | Zero PII to external API | 100% enforcement |
| NFR-7 | Audit Logging | All API calls logged | 100% coverage |
| NFR-8 | Code Type Safety | mypy strict mode compliance | Zero errors |
| NFR-9 | Test Coverage | Line coverage for critical stages | >= 80% for stages 2, 3, 4 |
| NFR-10 | Dependency Security | Known vulnerabilities | Zero high/critical CVEs |

---

## Glossary

- **PII (Personally Identifiable Information)**: Data that can identify a student, including names, student IDs, email addresses, and any combination that could reveal identity.
- **FERPA (Family Educational Rights and Privacy Act)**: US federal law protecting student education records.
- **FERPA Gate**: The anonymization checkpoint (Stage 3) that ensures no PII passes to external APIs.
- **ZDR (Zero Data Retention)**: API configuration where the provider does not retain request/response data.
- **NER (Named Entity Recognition)**: ML technique for identifying named entities (people, places, organizations) in text.
- **GLiNER**: A generalist NER model that can detect arbitrary entity types without fine-tuning.
- **Presidio**: Microsoft's open-source PII detection and anonymization library.
- **LanguageTool**: Open-source grammar, spelling, and style checker that runs locally.
- **rapidfuzz**: Fast fuzzy string matching library for Python.
- **Roster**: The class enrollment list containing student names and identifiers.
- **Completeness**: Quality metric for comments evaluating specificity, actionability, and evidence.
- **Consistency**: Alignment between the grade assigned and the sentiment of the comment.

---

## Out of Scope

- **Google Drive integration**: Stage 0 will accept local .docx files only; Google Docs API integration is deferred.
- **Multi-language support**: Only English (en-US) is supported for grammar and NER.
- **Real-time collaboration**: No simultaneous editing or live sync features.
- **Grade calculation**: The system analyzes but does not modify or compute grades.
- **Parent portal integration**: No direct communication with parents or student information systems.
- **Mobile interface**: Web UI targets desktop browsers only.
- **Batch scheduling**: No automated scheduled processing; manual invocation only.
- **OCR for scanned documents**: Only digital .docx files supported.

---

## Dependencies

| Dependency | Purpose | Status |
|------------|---------|--------|
| Python >= 3.10 | Runtime | Required |
| python-docx | Parse .docx files in Stage 0 | Installed |
| language-tool-python | Local grammar checking in Stage 1 | Installed |
| GLiNER | NER for name extraction in Stage 2 | Listed, not yet used |
| spaCy | Alternative/fallback NER | Listed |
| rapidfuzz | Fuzzy string matching in Stage 2 | Listed, not yet used |
| presidio-analyzer | PII detection in Stage 3 | Installed |
| presidio-anonymizer | PII anonymization in Stage 3 | Installed |
| anthropic | API client for Stage 4 semantic analysis | Listed |
| Pydantic >= 2.5 | Data validation and models | Installed |
| structlog | Structured logging throughout | Installed |
| FastAPI (optional) | Web UI for Stage 5 | Listed as optional |
| pytest | Test framework | Dev dependency |
| mypy | Type checking | Dev dependency |

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| GLiNER/spaCy NER misses names in educational context | Medium | High | Train custom model or supplement with roster-based detection |
| Presidio false negatives leak PII to API | Low | Critical | Double-verification with re-scan after anonymization |
| LanguageTool Java server instability | Low | Medium | Add health checks and auto-restart logic |
| API rate limits during batch processing | Medium | Medium | Implement exponential backoff and batch queuing |
| Large documents cause memory issues | Low | Medium | Stream processing or document chunking |
| Type incompatibility between stages | High (current) | High | P0 priority to unify models |

---

## Success Criteria

1. **Pipeline runs end-to-end**: `python -m ferpa_feedback.pipeline --input sample.docx --roster roster.csv` completes without errors.
2. **All 6 stages functional**: Each stage (0-5) produces expected outputs.
3. **FERPA compliance verified**: Audit log confirms no PII in API requests.
4. **PII recall >= 95%**: Test corpus confirms detection rate.
5. **Type safety**: `mypy --strict` passes on entire codebase.
6. **Test coverage >= 80%**: Critical stages have comprehensive test suites.
7. **Documentation complete**: Each stage has docstrings and usage examples.
