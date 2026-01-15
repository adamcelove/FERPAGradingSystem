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
ferpa-comment-feedback/
├── README.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── settings.yaml              # Main configuration
│   ├── grading_scales.yaml        # Grade interpretation rules
│   └── completeness_rubric.yaml   # What makes a "complete" comment
├── src/
│   └── ferpa_feedback/
│       ├── __init__.py
│       ├── pipeline.py            # Main orchestrator
│       ├── stage_0_ingestion/     # Document parsing
│       ├── stage_1_grammar/       # LanguageTool integration
│       ├── stage_2_names/         # Name extraction & matching
│       ├── stage_3_anonymize/     # PII removal
│       ├── stage_4_semantic/      # API-based analysis
│       ├── stage_5_review/        # Human review queue
│       └── utils/                 # Shared utilities
├── agents/                        # Claude Code agent definitions
│   ├── ferpa-compliance-reviewer.md
│   ├── name-detection-specialist.md
│   └── pipeline-debugger.md
├── skills/                        # Custom skills for this project
│   ├── ferpa-anonymization/
│   └── gliner-name-detection/
├── tests/
│   ├── fixtures/                  # Sample documents for testing
│   ├── test_grammar.py
│   ├── test_names.py
│   ├── test_anonymization.py
│   └── test_pipeline_integration.py
└── scripts/
    ├── process_batch.py           # CLI for batch processing
    └── setup_languagetool.py      # One-time setup
```

## Quick Start

```bash
# 1. Clone and setup
cd ferpa-comment-feedback
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env with your settings

# 3. Setup LanguageTool (one-time)
python scripts/setup_languagetool.py

# 4. Run on sample document
python -m ferpa_feedback.pipeline --input sample.docx --roster roster.csv

# 5. Review results
python -m ferpa_feedback.review_server
```

## FERPA Compliance Guarantees

1. **Stages 0-3 are 100% local** - No network calls, no external dependencies
2. **Stage 4 receives ONLY anonymized text** - All names replaced with placeholders
3. **Bidirectional mapping stored locally** - De-anonymization happens on your infrastructure
4. **Audit logging** - Every processing step is logged with timestamps
5. **ZDR API configuration** - External API calls use Zero Data Retention settings

## Configuration

### `config/settings.yaml`
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

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

Proprietary - For internal educational use only.
