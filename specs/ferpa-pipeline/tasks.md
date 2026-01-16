---
spec: ferpa-pipeline
phase: tasks
total_tasks: 42
created: 2026-01-15
---

# Tasks: FERPA Pipeline Improvements

## Phase 1: Make It Work (POC)

Focus: Get the pipeline running end-to-end by fixing structure, creating missing modules, and unifying models. Accept shortcuts, skip tests.

### 1.1 Project Structure - Create src directory layout

- [x] 1.1.1 Create src/ferpa_feedback directory structure
  - **Do**: Create the required directory structure matching pyproject.toml expectations
    1. Create `src/` directory
    2. Create `src/ferpa_feedback/` directory
    3. Create `src/ferpa_feedback/recognizers/` directory
  - **Files**:
    - `src/ferpa_feedback/` (new directory)
    - `src/ferpa_feedback/recognizers/` (new directory)
  - **Done when**: Directory structure exists: `ls -la src/ferpa_feedback/` shows empty directory, `ls -la src/ferpa_feedback/recognizers/` shows empty directory
  - **Verify**: `ls -la src/ferpa_feedback/ && ls -la src/ferpa_feedback/recognizers/`
  - **Commit**: `feat(structure): create src/ferpa_feedback directory layout`
  - _Requirements: FR-1, AC-1.1, AC-1.2_
  - _Design: Project Structure Transformation_

- [x] 1.1.2 Create __init__.py files for package
  - **Do**: Create package init files with proper exports
    1. Create `src/ferpa_feedback/__init__.py` with version and key exports
    2. Create `src/ferpa_feedback/recognizers/__init__.py` with empty exports
  - **Files**:
    - `src/ferpa_feedback/__init__.py`
    - `src/ferpa_feedback/recognizers/__init__.py`
  - **Done when**: Python can import `ferpa_feedback` package
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); import ferpa_feedback; print(ferpa_feedback.__version__)"`
  - **Commit**: `feat(structure): add package __init__.py files`
  - _Requirements: FR-1, AC-1.1_
  - _Design: Target Directory Structure_

### 1.2 Move and Unify Existing Files

- [x] 1.2.1 Move models.py to src/ferpa_feedback/
  - **Do**: Move the models file to the new package location (file already has unified Pydantic models)
    1. Copy `models.py` to `src/ferpa_feedback/models.py`
    2. Verify content is unchanged
  - **Files**:
    - `src/ferpa_feedback/models.py` (create from models.py)
  - **Done when**: `src/ferpa_feedback/models.py` exists with all Pydantic models
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.models import StudentComment, TeacherDocument; print('Models loaded')"`
  - **Commit**: `feat(structure): move models.py to src/ferpa_feedback/`
  - _Requirements: FR-3, AC-3.1_
  - _Design: Phase 1: Structure Fix_

- [x] 1.2.2 Create unified stage_0_ingestion.py using models.py StudentComment
  - **Do**: Create stage 0 that uses the unified Pydantic StudentComment from models.py instead of the dataclass
    1. Create `src/ferpa_feedback/stage_0_ingestion.py` based on `stage_0_ingestion_improved.py`
    2. Remove the local dataclass StudentComment definition (lines 55-79)
    3. Remove the local TeacherDocument dataclass (lines 81-108)
    4. Import StudentComment and TeacherDocument from ferpa_feedback.models
    5. Update `_create_comment` to return Pydantic StudentComment (adapt fields)
    6. Keep DocumentParser, RosterLoader, and utility functions
  - **Files**:
    - `src/ferpa_feedback/stage_0_ingestion.py` (new)
  - **Done when**: Stage 0 imports models from ferpa_feedback.models and outputs Pydantic StudentComment
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_0_ingestion import DocumentParser; print('Stage 0 loaded')"`
  - **Commit**: `feat(stage0): unify with Pydantic models from models.py`
  - _Requirements: FR-3, AC-3.2, AC-3.3_
  - _Design: Stage 0 Interface_

- [x] 1.2.3 Move stage_1_grammar.py to src/ferpa_feedback/
  - **Do**: Copy grammar stage to new location, update imports
    1. Copy `stage_1_grammar.py` to `src/ferpa_feedback/stage_1_grammar.py`
    2. Import path already correct: `from ferpa_feedback.models import ...`
  - **Files**:
    - `src/ferpa_feedback/stage_1_grammar.py` (new)
  - **Done when**: Stage 1 module is importable from new location
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_1_grammar import GrammarChecker; print('Stage 1 loaded')"`
  - **Commit**: `feat(structure): move stage_1_grammar.py to src/ferpa_feedback/`
  - _Requirements: FR-1_
  - _Design: Phase 1: Structure Fix_

- [x] 1.2.4 Move stage_3_anonymize.py to src/ferpa_feedback/
  - **Do**: Copy anonymization stage to new location
    1. Copy `stage_3_anonymize.py` to `src/ferpa_feedback/stage_3_anonymize.py`
    2. Import path already correct: `from ferpa_feedback.models import ...`
  - **Files**:
    - `src/ferpa_feedback/stage_3_anonymize.py` (new)
  - **Done when**: Stage 3 module is importable from new location
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_3_anonymize import AnonymizationProcessor; print('Stage 3 loaded')"`
  - **Commit**: `feat(structure): move stage_3_anonymize.py to src/ferpa_feedback/`
  - _Requirements: FR-1_
  - _Design: Phase 1: Structure Fix_

- [x] 1.2.5 Quality Checkpoint
  - **Do**: Run quality checks to verify structure changes work
  - **Verify**: All commands must pass:
    - Import check: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback import models, stage_0_ingestion, stage_1_grammar, stage_3_anonymize; print('All modules loaded')"`
    - Type check (if mypy available): `cd src && python -m mypy ferpa_feedback/models.py --ignore-missing-imports || echo 'mypy not configured yet'`
  - **Done when**: All existing modules are importable from new location
  - **Commit**: `chore(structure): pass quality checkpoint` (only if fixes needed)

### 1.3 Implement Stage 2 - Name Verification (Stub)

- [x] 1.3.1 Create stage_2_names.py with stub implementation
  - **Do**: Create Stage 2 module with working stubs that allow pipeline to run
    1. Create `src/ferpa_feedback/stage_2_names.py`
    2. Implement `NameExtractor` protocol and `StubExtractor` class (returns empty list)
    3. Implement `NameMatcher` class with basic fuzzy matching stub
    4. Implement `NameVerificationProcessor` with `process_comment` and `process_document`
    5. Implement `create_name_processor` factory function
    6. Use rapidfuzz for basic string matching
  - **Files**:
    - `src/ferpa_feedback/stage_2_names.py` (new)
  - **Done when**: `create_name_processor()` returns a working processor that can process comments (even if matching is minimal)
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_2_names import create_name_processor; p = create_name_processor(); print('Stage 2 stub loaded')"`
  - **Commit**: `feat(stage2): create stub name verification module`
  - _Requirements: FR-2, AC-2.1_
  - _Design: Stage 2: Name Verification_

- [x] 1.3.2 Add GLiNER-based name extraction (basic)
  - **Do**: Implement GLiNERExtractor class for NER name extraction
    1. Add `GLiNERExtractor` class that loads GLiNER model
    2. Implement `extract_names` method to find PERSON entities
    3. Add lazy loading for model (expensive initialization)
    4. Handle model load failures gracefully (fall back to stub)
  - **Files**:
    - `src/ferpa_feedback/stage_2_names.py` (modify)
  - **Done when**: GLiNERExtractor can extract names from text
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_2_names import GLiNERExtractor; e = GLiNERExtractor(); print(e.extract_names('John Smith did well'))"`
  - **Commit**: `feat(stage2): implement GLiNER name extraction`
  - _Requirements: FR-4, AC-2.2_
  - _Design: GLiNERExtractor interface_

- [x] 1.3.3 Add rapidfuzz name matching
  - **Do**: Implement NameMatcher with fuzzy matching using rapidfuzz
    1. Update `NameMatcher` class to use `rapidfuzz.fuzz.token_sort_ratio`
    2. Implement configurable threshold (default 85)
    3. Implement confidence level classification (HIGH/MEDIUM/LOW)
    4. Return `NameMatch` model from matching
  - **Files**:
    - `src/ferpa_feedback/stage_2_names.py` (modify)
  - **Done when**: NameMatcher correctly matches similar names with scores
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_2_names import NameMatcher; m = NameMatcher(); print(m.match('John Smith', 'Smith, John', ['Smith, John']))"`
  - **Commit**: `feat(stage2): implement rapidfuzz name matching`
  - _Requirements: FR-5, AC-2.3, AC-2.4, AC-2.5_
  - _Design: NameMatcher interface_

- [x] 1.3.4 Quality Checkpoint
  - **Do**: Run quality checks to verify Stage 2 implementation
  - **Verify**: All commands must pass:
    - Import check: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_2_names import NameVerificationProcessor, create_name_processor, GLiNERExtractor, NameMatcher; print('Stage 2 fully loaded')"`
  - **Done when**: Stage 2 module fully importable with all components
  - **Commit**: `chore(stage2): pass quality checkpoint` (only if fixes needed)

### 1.4 Update Pipeline Orchestrator

- [x] 1.4.1 Move pipeline.py to src/ferpa_feedback/
  - **Do**: Copy pipeline orchestrator to new location
    1. Copy `pipeline.py` to `src/ferpa_feedback/pipeline.py`
    2. Imports already use `ferpa_feedback.*` paths
  - **Files**:
    - `src/ferpa_feedback/pipeline.py` (new)
  - **Done when**: Pipeline module is importable
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.pipeline import FeedbackPipeline; print('Pipeline loaded')"`
  - **Commit**: `feat(structure): move pipeline.py to src/ferpa_feedback/`
  - _Requirements: FR-1_
  - _Design: Phase 1: Structure Fix_

### 1.5 Create CLI Module

- [x] 1.5.1 Create cli.py with basic commands
  - **Do**: Create CLI entrypoint matching pyproject.toml script definition
    1. Create `src/ferpa_feedback/cli.py`
    2. Implement `process` command for document processing
    3. Implement `warmup` command stub (can be empty for POC)
    4. Use typer for CLI framework
  - **Files**:
    - `src/ferpa_feedback/cli.py` (new)
  - **Done when**: `python -m ferpa_feedback.cli --help` shows available commands
  - **Verify**: `cd src && python -m ferpa_feedback.cli --help`
  - **Commit**: `feat(cli): create basic CLI module with process command`
  - _Requirements: FR-1, AC-1.3_
  - _Design: CLI Module_

- [x] 1.5.2 Quality Checkpoint
  - **Do**: Run quality checks after CLI implementation
  - **Verify**: All commands must pass:
    - CLI help: `cd src && python -m ferpa_feedback.cli --help`
    - Module imports: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.cli import app; print('CLI loaded')"`
  - **Done when**: CLI is functional with help output
  - **Commit**: `chore(cli): pass quality checkpoint` (only if fixes needed)

### 1.6 Implement Stage 4 - Semantic Analysis (Stub)

- [x] 1.6.1 Create stage_4_semantic.py with FERPA-enforced client
  - **Do**: Create Stage 4 module with FERPA gate enforcement
    1. Create `src/ferpa_feedback/stage_4_semantic.py`
    2. Implement `FERPAViolationError` exception
    3. Implement `FERPAEnforcedClient` that requires AnonymizationGate
    4. Implement stub `CompletenessAnalyzer` (returns default scores)
    5. Implement stub `ConsistencyAnalyzer` (returns default values)
    6. Implement `SemanticAnalysisProcessor` with `process_comment` and `process_document`
    7. Implement `create_semantic_processor` factory function
  - **Files**:
    - `src/ferpa_feedback/stage_4_semantic.py` (new)
  - **Done when**: Stage 4 module is importable and enforces FERPA gate
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_4_semantic import create_semantic_processor, FERPAEnforcedClient; print('Stage 4 loaded')"`
  - **Commit**: `feat(stage4): create stub semantic analysis with FERPA enforcement`
  - _Requirements: FR-8, FR-9, FR-10, AC-5.1, AC-5.4_
  - _Design: Stage 4: Semantic Analysis, FERPAEnforcedClient_

### 1.7 Implement Stage 5 - Review Queue (Stub)

- [x] 1.7.1 Create stage_5_review.py with basic queue
  - **Do**: Create Stage 5 module with review queue logic
    1. Create `src/ferpa_feedback/stage_5_review.py`
    2. Implement `ReviewItem` model (or use from models.py if exists)
    3. Implement `ReviewQueue` class with in-memory storage
    4. Implement `add_document`, `get_pending`, `update_status` methods
    5. Implement `DeAnonymizer` class for restoring original text
    6. Implement `create_review_processor` factory function
  - **Files**:
    - `src/ferpa_feedback/stage_5_review.py` (new)
  - **Done when**: Stage 5 module is importable and can queue comments
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_5_review import ReviewQueue, create_review_processor; print('Stage 5 loaded')"`
  - **Commit**: `feat(stage5): create stub review queue module`
  - _Requirements: FR-11, FR-13, AC-6.1_
  - _Design: Stage 5: Review Queue_

- [x] 1.7.2 Quality Checkpoint
  - **Do**: Run quality checks for all stages
  - **Verify**: All commands must pass:
    - All stages import: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback import stage_0_ingestion, stage_1_grammar, stage_2_names, stage_3_anonymize, stage_4_semantic, stage_5_review; print('All stages loaded')"`
  - **Done when**: All stage modules importable without errors
  - **Commit**: `chore(stages): pass quality checkpoint` (only if fixes needed)

### 1.8 POC Checkpoint - End-to-End Validation

- [x] 1.8.1 Verify pipeline runs end-to-end
  - **Do**: Test that the complete pipeline can be instantiated and run (may need sample doc)
    1. Create a simple test script that initializes FeedbackPipeline
    2. Verify all stages can be called in sequence
    3. Document any shortcuts or hardcoded values used
  - **Files**:
    - (no new files - verification only)
  - **Done when**: `FeedbackPipeline` can be instantiated without ImportError
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.pipeline import FeedbackPipeline, PipelineConfig; p = FeedbackPipeline(PipelineConfig()); print('Pipeline instantiated successfully')"`
  - **Commit**: `feat(pipeline): complete POC - pipeline runs end-to-end`
  - _Requirements: AC-1.1, AC-1.3_
  - _Design: Data Flow_

---

## Phase 2: Refactoring

After POC validated, clean up code and implement full functionality.

### 2.1 Enhance Stage 2 - Full Name Detection

- [x] 2.1.1 Add spaCy fallback extractor
  - **Do**: Implement SpaCyExtractor as fallback when GLiNER fails
    1. Add `SpaCyExtractor` class to stage_2_names.py
    2. Implement `extract_names` using spaCy NER
    3. Update `create_name_processor` to use fallback pattern
  - **Files**:
    - `src/ferpa_feedback/stage_2_names.py` (modify)
  - **Done when**: SpaCyExtractor can extract names as fallback
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_2_names import SpaCyExtractor; e = SpaCyExtractor(); print(e.extract_names('Mary Jane helped'))"`
  - **Commit**: `refactor(stage2): add spaCy fallback extractor`
  - _Requirements: FR-4_
  - _Design: SpaCyExtractor interface_

- [x] 2.1.2 Handle name edge cases
  - **Do**: Update name matching to handle edge cases
    1. Add apostrophe handling (O'Brien, O'Connor)
    2. Add hyphenated name handling (Smith-Jones)
    3. Add prefix capitalization (McDonald, MacArthur)
    4. Add suffix stripping (Jr., Sr., III)
    5. Add nickname expansion table
  - **Files**:
    - `src/ferpa_feedback/stage_2_names.py` (modify)
  - **Done when**: Name matching handles all edge cases from design doc
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_2_names import NameMatcher; m = NameMatcher(); print(m.match(\"O'Brien\", \"OBrien\", [\"O'Brien\"]))"`
  - **Commit**: `refactor(stage2): handle name edge cases`
  - _Requirements: FR-16, AC-2.6_
  - _Design: Name Edge Cases_

### 2.2 Enhance Stage 3 - Custom Presidio Recognizers

- [x] 2.2.1 Create educational PII recognizers
  - **Do**: Create custom Presidio recognizers for educational context
    1. Create `src/ferpa_feedback/recognizers/educational.py`
    2. Implement `StudentIDRecognizer` with patterns
    3. Implement `GradeLevelRecognizer` with patterns
    4. Implement `SchoolNameRecognizer` (configurable patterns)
  - **Files**:
    - `src/ferpa_feedback/recognizers/educational.py` (new)
  - **Done when**: Custom recognizers can be instantiated
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.recognizers.educational import StudentIDRecognizer, GradeLevelRecognizer; print('Recognizers loaded')"`
  - **Commit**: `refactor(stage3): create custom educational PII recognizers`
  - _Requirements: FR-6, AC-4.1, AC-4.2_
  - _Design: New Recognizers_

- [x] 2.2.2 Integrate custom recognizers into PIIDetector
  - **Do**: Update PIIDetector to use custom recognizers
    1. Modify `PIIDetector` to accept custom recognizers
    2. Add `create_enhanced_analyzer` function
    3. Configure low threshold (0.3) for high recall
  - **Files**:
    - `src/ferpa_feedback/stage_3_anonymize.py` (modify)
  - **Done when**: PIIDetector uses custom recognizers
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_3_anonymize import PIIDetector; d = PIIDetector(); print(d.detect('Student ID: S12345678'))"`
  - **Commit**: `refactor(stage3): integrate custom educational recognizers`
  - _Requirements: FR-7, AC-4.3_
  - _Design: Enhanced PIIDetector Configuration_

- [x] 2.2.3 Quality Checkpoint
  - **Do**: Run quality checks after refactoring
  - **Verify**: All commands must pass:
    - Import check: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.recognizers.educational import StudentIDRecognizer; from ferpa_feedback.stage_3_anonymize import PIIDetector; print('Refactored modules loaded')"`
  - **Done when**: All refactored modules work correctly
  - **Commit**: `chore(refactor): pass quality checkpoint` (only if fixes needed)

### 2.3 Implement Stage 4 - Full Semantic Analysis

- [x] 2.3.1 Implement completeness analyzer with Claude API
  - **Do**: Replace stub with real Claude API integration
    1. Update `CompletenessAnalyzer` to call Claude API
    2. Implement prompt for completeness evaluation
    3. Parse response into `CompletenessResult` model
    4. Add retry logic with exponential backoff
  - **Files**:
    - `src/ferpa_feedback/stage_4_semantic.py` (modify)
  - **Done when**: CompletenessAnalyzer returns real analysis (requires API key)
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_4_semantic import CompletenessAnalyzer; print('Completeness analyzer ready')"`
  - **Commit**: `refactor(stage4): implement Claude API completeness analysis`
  - _Requirements: FR-8, AC-5.2, AC-5.5, AC-5.6, AC-5.7_
  - _Design: CompletenessAnalyzer interface_

- [x] 2.3.2 Implement consistency analyzer
  - **Do**: Implement grade-comment consistency checking
    1. Update `ConsistencyAnalyzer` to call Claude API
    2. Implement prompt for sentiment analysis
    3. Parse response into `ConsistencyResult` model
    4. Add ZDR headers to API calls
  - **Files**:
    - `src/ferpa_feedback/stage_4_semantic.py` (modify)
  - **Done when**: ConsistencyAnalyzer detects sentiment misalignment
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_4_semantic import ConsistencyAnalyzer; print('Consistency analyzer ready')"`
  - **Commit**: `refactor(stage4): implement Claude API consistency analysis`
  - _Requirements: FR-9, AC-5.3, AC-5.5_
  - _Design: ConsistencyAnalyzer interface_

### 2.4 Implement Stage 5 - Review UI

- [x] 2.4.1 Add FastAPI review UI (optional dependency)
  - **Do**: Implement web interface for human review
    1. Add `create_review_app` function to stage_5_review.py
    2. Implement GET `/` endpoint for review list
    3. Implement POST `/review/{comment_id}` for status updates
    4. Implement GET `/export` for approved comments
    5. Handle ImportError gracefully if FastAPI not installed
  - **Files**:
    - `src/ferpa_feedback/stage_5_review.py` (modify)
  - **Done when**: FastAPI app can be created (if dependencies installed)
  - **Verify**: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_5_review import create_review_app; print('Review app factory exists')"`
  - **Commit**: `refactor(stage5): add FastAPI review UI`
  - _Requirements: FR-12, AC-6.2, AC-6.3, AC-6.4, AC-6.5_
  - _Design: FastAPI Review UI_

- [x] 2.4.2 Add review CLI command
  - **Do**: Add `review` command to CLI for starting review server
    1. Update cli.py with `review` command
    2. Use uvicorn to run FastAPI app
    3. Handle missing optional dependencies gracefully
  - **Files**:
    - `src/ferpa_feedback/cli.py` (modify)
  - **Done when**: `ferpa-feedback review` command exists in CLI
  - **Verify**: `cd src && python -m ferpa_feedback.cli review --help`
  - **Commit**: `refactor(cli): add review server command`
  - _Requirements: FR-12_
  - _Design: CLI Module_

- [x] 2.4.3 Quality Checkpoint
  - **Do**: Run quality checks after Stage 4 and 5 refactoring
  - **Verify**: All commands must pass:
    - Stage 4 imports: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_4_semantic import SemanticAnalysisProcessor, CompletenessAnalyzer, ConsistencyAnalyzer; print('Stage 4 complete')"`
    - Stage 5 imports: `python -c "import sys; sys.path.insert(0, 'src'); from ferpa_feedback.stage_5_review import ReviewQueue, DeAnonymizer; print('Stage 5 complete')"`
  - **Done when**: All refactored stages work correctly
  - **Commit**: `chore(stages): pass quality checkpoint` (only if fixes needed)

### 2.5 CLI Polish and LanguageTool Warmup

- [x] 2.5.1 Implement warmup command
  - **Do**: Add LanguageTool warmup command to reduce cold start
    1. Update `warmup` command in cli.py
    2. Pre-load LanguageTool server
    3. Add progress indicator using rich
  - **Files**:
    - `src/ferpa_feedback/cli.py` (modify)
  - **Done when**: `ferpa-feedback warmup` pre-loads LanguageTool
  - **Verify**: `cd src && python -m ferpa_feedback.cli warmup --help`
  - **Commit**: `refactor(cli): implement LanguageTool warmup command`
  - _Requirements: FR-14, AC-7.1, AC-7.2, AC-7.3_
  - _Design: CLI warmup command_

### 2.6 Dependency Audit

- [x] 2.6.1 Audit and document dependencies
  - **Do**: Verify all pyproject.toml dependencies are used
    1. Create audit of each dependency and its usage
    2. Verify GLiNER is used by Stage 2
    3. Verify rapidfuzz is used by Stage 2
    4. Update pyproject.toml if any unused dependencies found
  - **Files**:
    - `pyproject.toml` (potentially modify)
  - **Done when**: All dependencies have documented purpose
  - **Verify**: `pip install -e . && python -c "import ferpa_feedback; print('Package installs correctly')"`
  - **Commit**: `refactor(deps): audit and document all dependencies`
  - _Requirements: FR-15, AC-8.1, AC-8.2, AC-8.3, AC-8.4_
  - _Design: Phase 6: CLI and Polish_

---

## Phase 3: Testing

Add comprehensive test coverage for critical stages.

### 3.1 Test Infrastructure Setup

- [x] 3.1.1 Create test directory structure and conftest
  - **Do**: Set up pytest infrastructure
    1. Create `tests/` directory
    2. Create `tests/__init__.py`
    3. Create `tests/conftest.py` with shared fixtures
    4. Create `tests/fixtures/` directory
    5. Create sample test data files
  - **Files**:
    - `tests/__init__.py` (new)
    - `tests/conftest.py` (new)
    - `tests/fixtures/sample_comments.json` (new)
    - `tests/fixtures/test_roster.csv` (new)
  - **Done when**: `pytest tests/` runs without import errors
  - **Verify**: `pytest tests/ --collect-only`
  - **Commit**: `test(setup): create test infrastructure and fixtures`
  - _Requirements: AC-1.4_
  - _Design: Test Strategy_

### 3.2 Stage 2 Tests

- [x] 3.2.1 Add unit tests for name extraction
  - **Do**: Test name extraction functionality
    1. Create `tests/test_stage_2.py`
    2. Add tests for GLiNER extraction
    3. Add tests for spaCy fallback
    4. Add tests for edge cases (apostrophe, hyphenated, etc.)
  - **Files**:
    - `tests/test_stage_2.py` (new)
  - **Done when**: Name extraction tests pass
  - **Verify**: `pytest tests/test_stage_2.py -v`
  - **Commit**: `test(stage2): add name extraction unit tests`
  - _Requirements: AC-2.2, AC-2.6_
  - _Design: Unit Tests - Stage 2_

- [x] 3.2.2 Add unit tests for name matching
  - **Do**: Test fuzzy name matching
    1. Add tests for exact match (HIGH confidence)
    2. Add tests for nickname match (MEDIUM confidence)
    3. Add tests for wrong name (LOW confidence)
    4. Add tests for configurable threshold
  - **Files**:
    - `tests/test_stage_2.py` (modify)
  - **Done when**: Name matching tests pass
  - **Verify**: `pytest tests/test_stage_2.py -v -k "match"`
  - **Commit**: `test(stage2): add name matching unit tests`
  - _Requirements: AC-2.3, AC-2.4, AC-2.5_
  - _Design: Unit Tests - TestNameMatching_

### 3.3 Stage 3 Tests

- [x] 3.3.1 Add unit tests for custom recognizers
  - **Do**: Test educational PII recognizers
    1. Create `tests/test_stage_3.py`
    2. Add tests for StudentIDRecognizer
    3. Add tests for GradeLevelRecognizer
  - **Files**:
    - `tests/test_stage_3.py` (new)
  - **Done when**: Recognizer tests pass
  - **Verify**: `pytest tests/test_stage_3.py -v`
  - **Commit**: `test(stage3): add custom recognizer unit tests`
  - _Requirements: AC-4.2_
  - _Design: Unit Tests - TestCustomRecognizers_

- [x] 3.3.2 Add PII recall tests
  - **Do**: Test that PII detection achieves 95% recall target
    1. Create test corpus with known PII
    2. Add test verifying >= 95% recall
    3. Document false positive rate
  - **Files**:
    - `tests/test_stage_3.py` (modify)
    - `tests/fixtures/pii_test_corpus.json` (new)
  - **Done when**: Recall test passes with >= 95%
  - **Verify**: `pytest tests/test_stage_3.py -v -k "recall"`
  - **Commit**: `test(stage3): add PII recall tests with 95% target`
  - _Requirements: FR-7, AC-4.4, AC-4.5, NFR-1_
  - _Design: Unit Tests - TestPIIRecall_

- [ ] 3.3.3 Quality Checkpoint
  - **Do**: Run all tests to verify test infrastructure
  - **Verify**: All commands must pass:
    - Run tests: `pytest tests/ -v`
  - **Done when**: All tests pass
  - **Commit**: `chore(test): pass quality checkpoint` (only if fixes needed)

### 3.4 Stage 4 Tests

- [ ] 3.4.1 Add FERPA gate enforcement tests
  - **Do**: Test that FERPA gate blocks unanonymized content
    1. Create `tests/test_stage_4.py`
    2. Add test for blocking unanonymized comment
    3. Add test for blocking comment with remaining PII
    4. Add test for allowing clean anonymized comment
    5. Add test for FERPAViolationError exception
  - **Files**:
    - `tests/test_stage_4.py` (new)
  - **Done when**: FERPA gate tests pass
  - **Verify**: `pytest tests/test_stage_4.py -v -k "ferpa"`
  - **Commit**: `test(stage4): add FERPA gate enforcement tests`
  - _Requirements: FR-10, AC-5.4, NFR-6_
  - _Design: Unit Tests - TestFERPAGateEnforcement_

- [ ] 3.4.2 Add semantic analysis tests (mocked API)
  - **Do**: Test semantic analysis with mocked Claude API
    1. Add mock fixtures for Anthropic client
    2. Add test for completeness scoring
    3. Add test for consistency detection
  - **Files**:
    - `tests/test_stage_4.py` (modify)
  - **Done when**: Semantic analysis tests pass with mocks
  - **Verify**: `pytest tests/test_stage_4.py -v -k "semantic"`
  - **Commit**: `test(stage4): add semantic analysis tests with mocked API`
  - _Requirements: AC-5.2, AC-5.3_
  - _Design: Unit Tests - TestSemanticAnalysis_

### 3.5 Integration Tests

- [ ] 3.5.1 Add pipeline integration tests
  - **Do**: Test full pipeline integration
    1. Create `tests/test_integration.py`
    2. Add test for full pipeline with sample document
    3. Add test for pipeline with roster
    4. Add test for FERPA gate integration
    5. Add critical compliance test: no PII reaches API
  - **Files**:
    - `tests/test_integration.py` (new)
  - **Done when**: Integration tests pass
  - **Verify**: `pytest tests/test_integration.py -v`
  - **Commit**: `test(integration): add pipeline integration tests`
  - _Requirements: AC-1.1, NFR-6_
  - _Design: Integration Tests_

- [ ] 3.5.2 Quality Checkpoint
  - **Do**: Run all tests to verify complete coverage
  - **Verify**: All commands must pass:
    - All tests: `pytest tests/ -v`
    - Coverage check: `pytest tests/ --cov=ferpa_feedback --cov-report=term-missing || echo 'coverage not configured'`
  - **Done when**: All tests pass
  - **Commit**: `chore(test): pass final test quality checkpoint` (only if fixes needed)

---

## Phase 4: Quality Gates

Final verification and PR creation.

### 4.1 Local Quality Checks

- [ ] 4.1.1 Run type checking with mypy
  - **Do**: Verify type safety with mypy strict mode
    1. Run mypy on all source files
    2. Fix any type errors found
    3. Ensure no errors in strict mode
  - **Files**:
    - (potentially any src files with type issues)
  - **Done when**: `mypy --strict` passes
  - **Verify**: `cd src && python -m mypy ferpa_feedback/ --strict --ignore-missing-imports`
  - **Commit**: `fix(types): resolve mypy strict mode errors`
  - _Requirements: AC-3.4, NFR-8_

- [ ] 4.1.2 Run linting with ruff
  - **Do**: Verify code style with ruff
    1. Run ruff on all source files
    2. Fix any lint errors found
  - **Files**:
    - (potentially any src files with lint issues)
  - **Done when**: `ruff check` passes
  - **Verify**: `ruff check src/`
  - **Commit**: `fix(lint): resolve ruff lint errors`

- [ ] 4.1.3 Run all tests
  - **Do**: Final test verification
    1. Run full test suite
    2. Verify all tests pass
    3. Check coverage meets target (80% for critical stages)
  - **Files**:
    - (no file changes expected)
  - **Done when**: All tests pass
  - **Verify**: `pytest tests/ -v --tb=short`
  - **Commit**: `fix(tests): resolve any failing tests` (only if needed)
  - _Requirements: AC-1.4, NFR-9_

- [ ] 4.1.4 Verify package installation
  - **Do**: Test that package installs correctly
    1. Run pip install in editable mode
    2. Verify CLI is accessible
    3. Run basic smoke test
  - **Files**:
    - (no file changes)
  - **Done when**: `pip install -e .` succeeds and CLI works
  - **Verify**: `pip install -e . && ferpa-feedback --help`
  - **Commit**: (no commit needed if successful)
  - _Requirements: AC-1.3_

### 4.2 Create PR and Verify CI

- [ ] 4.2.1 Final quality checkpoint
  - **Do**: Run ALL quality checks locally before PR
  - **Verify**: All commands must pass:
    - Type check: `cd src && python -m mypy ferpa_feedback/ --strict --ignore-missing-imports || echo 'some type issues remain'`
    - Lint: `ruff check src/ || echo 'some lint issues remain'`
    - Tests: `pytest tests/ -v`
    - Install: `pip install -e . && ferpa-feedback --help`
  - **Done when**: All quality checks pass
  - **Commit**: `chore(quality): pass final quality checkpoint` (only if fixes needed)

- [ ] 4.2.2 Create PR and verify CI
  - **Do**:
    1. Verify current branch is a feature branch: `git branch --show-current`
    2. If on default branch, STOP and alert user (should not happen - branch is set at startup)
    3. Push branch: `git push -u origin <branch-name>`
    4. Create PR using gh CLI: `gh pr create --title "feat(pipeline): FERPA pipeline improvements" --body "Implements FR-1 through FR-16 for FERPA pipeline stabilization and enhancement"`
    5. If gh CLI unavailable, provide URL for manual PR creation
  - **Verify**: Use gh CLI to verify CI:
    - `gh pr checks --watch` (wait for CI completion)
    - Or `gh pr checks` (poll current status)
    - All checks must show checkmark (passing)
  - **Done when**: All CI checks green, PR ready for review
  - **If CI fails**:
    1. Read failure details: `gh pr checks`
    2. Fix issues locally
    3. Push fixes: `git push`
    4. Re-verify: `gh pr checks --watch`

---

## Notes

### POC shortcuts taken:
- Stage 2 GLiNER extractor may use default model without optimization
- Stage 4 semantic analysis uses stub implementations until API integration
- Stage 5 review queue uses in-memory storage (no persistence)
- Custom recognizers use basic patterns without extensive tuning
- Test corpus for 95% recall may be limited in POC

### Production TODOs for later:
- Fine-tune GLiNER model for educational context
- Implement persistent storage for review queue
- Add comprehensive nickname expansion table
- Tune Presidio thresholds based on real-world data
- Add authentication to FastAPI review UI
- Implement batch scheduling for automated processing
- Add comprehensive audit logging to file/database

### Files created in this spec:
- `src/ferpa_feedback/__init__.py`
- `src/ferpa_feedback/models.py` (moved from root)
- `src/ferpa_feedback/stage_0_ingestion.py` (adapted)
- `src/ferpa_feedback/stage_1_grammar.py` (moved from root)
- `src/ferpa_feedback/stage_2_names.py` (new)
- `src/ferpa_feedback/stage_3_anonymize.py` (moved from root)
- `src/ferpa_feedback/stage_4_semantic.py` (new)
- `src/ferpa_feedback/stage_5_review.py` (new)
- `src/ferpa_feedback/pipeline.py` (moved from root)
- `src/ferpa_feedback/cli.py` (new)
- `src/ferpa_feedback/recognizers/__init__.py` (new)
- `src/ferpa_feedback/recognizers/educational.py` (new)
- `tests/conftest.py` (new)
- `tests/test_stage_2.py` (new)
- `tests/test_stage_3.py` (new)
- `tests/test_stage_4.py` (new)
- `tests/test_integration.py` (new)
- `tests/fixtures/sample_comments.json` (new)
- `tests/fixtures/test_roster.csv` (new)
- `tests/fixtures/pii_test_corpus.json` (new)
