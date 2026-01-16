# FERPA-Compliant Teacher Comment Feedback System

A secure, privacy-preserving pipeline for analyzing and improving teacher comments on student progress reports.

## Overview

This system processes teacher comments stored in Google Docs, performing:
1. **Grammar/Spelling Checks** - Deterministic, local processing via LanguageTool
2. **Name-Comment Matching** - Ensures student names in comments match the intended student
3. **Anonymization** - Replaces all PII before any external API calls
4. **Completeness Analysis** - Semantic check that comments are substantive (via API, post-anonymization)
5. **Grade-Comment Consistency** - Validates alignment between grades and comment tone (via API, post-anonymization)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FERPA COMPLIANCE BOUNDARY                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  LOCAL PROCESSING ONLY (No external API calls)                        │  │
│  │                                                                       │  │
│  │  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────────┐  │  │
│  │  │  Document   │───▶│   Grammar/   │───▶│  Name Extraction &      │  │  │
│  │  │  Ingestion  │    │   Spelling   │    │  Student Matching       │  │  │
│  │  │  (Stage 0)  │    │   (Stage 1)  │    │  (Stage 2)              │  │  │
│  │  └─────────────┘    └──────────────┘    └───────────┬─────────────┘  │  │
│  │                                                     │                 │  │
│  │                                         ┌───────────▼─────────────┐  │  │
│  │                                         │    Anonymization        │  │  │
│  │                                         │    (Stage 3)            │  │  │
│  │                                         │    [FERPA GATE]         │  │  │
│  │                                         └───────────┬─────────────┘  │  │
│  └─────────────────────────────────────────────────────┼─────────────────┘  │
│                                                        │                     │
│                         ANONYMIZED DATA ONLY           │                     │
│                                ┌───────────────────────▼──────────────────┐  │
│                                │     External API (ZDR Configured)        │  │
│                                │     - Completeness Check (Stage 4a)      │  │
│                                │     - Grade Consistency (Stage 4b)       │  │
│                                └───────────────────────┬──────────────────┘  │
│                                                        │                     │
│  ┌─────────────────────────────────────────────────────▼─────────────────┐  │
│  │                     Human Review Queue (Stage 5)                       │  │
│  │                     - De-anonymize for display                         │  │
│  │                     - Accept/Reject/Modify suggestions                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
FERPA Comment system/
├── README.md
├── pyproject.toml
├── settings.yaml                  # Main configuration
├── completeness_rubric.yaml       # What makes a "complete" comment
├── src/
│   └── ferpa_feedback/
│       ├── __init__.py
│       ├── cli.py                 # Command-line interface
│       ├── models.py              # Data models
│       ├── pipeline.py            # Main orchestrator
│       ├── stage_0_ingestion.py   # Document parsing
│       ├── stage_1_grammar.py     # LanguageTool integration
│       ├── stage_2_names.py       # Name extraction & matching
│       ├── stage_3_anonymize.py   # PII removal
│       ├── stage_4_semantic.py    # API-based analysis
│       ├── stage_5_review.py      # Human review queue
│       └── recognizers/           # Custom PII recognizers
│           ├── __init__.py
│           └── educational.py     # Education-specific patterns
├── tests/
│   ├── conftest.py                # Test fixtures
│   ├── test_stage_2.py            # Name matching tests
│   ├── test_stage_3.py            # Anonymization tests
│   ├── test_stage_4.py            # Semantic analysis tests
│   └── test_integration.py        # Pipeline integration tests
└── sample_data/                   # Sample documents for testing
    └── outputs/                   # Processing outputs
```

## Quick Start

```bash
# 1. Clone and setup
cd "FERPA Comment system"
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Run on a document
ferpa-feedback process sample_data/document.docx --roster sample_data/roster.csv

# 3. Run tests
pytest tests/
```

## FERPA Compliance Guarantees

1. **Stages 0-3 are 100% local** - No network calls, no external dependencies
2. **Stage 4 receives ONLY anonymized text** - All names replaced with placeholders
3. **Bidirectional mapping stored locally** - De-anonymization happens on your infrastructure
4. **Audit logging** - Every processing step is logged with timestamps
5. **ZDR API configuration** - External API calls use Zero Data Retention settings

## Configuration

### `settings.yaml`
```yaml
pipeline:
  stages:
    grammar: true
    name_matching: true
    completeness: true
    grade_consistency: true

ferpa:
  anonymize_before_api: true  # NEVER set to false
  log_all_api_calls: true

confidence_thresholds:
  auto_accept: 0.95
  human_review: 0.70
  auto_reject: 0.30
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run linting
ruff check src/
```

## License

Proprietary - For internal educational use only.
