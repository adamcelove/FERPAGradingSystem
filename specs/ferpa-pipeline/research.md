---
spec: ferpa-pipeline
phase: research
created: 2026-01-15
---

# Research: ferpa-pipeline

## Executive Summary

The FERPA Comment System is a privacy-preserving pipeline for analyzing and improving teacher comments on student progress reports. The system processes Word documents through six stages: ingestion, grammar checking, name verification, anonymization (the FERPA compliance gate), semantic analysis via external API, and human review. The current implementation shows a well-architected foundation with strong privacy controls, but has several incomplete components (Stage 2, 4, 5), project structure inconsistencies, and opportunities for performance optimization.

## External Research

### Best Practices for FERPA Compliance in EdTech

Based on current industry standards (2025-2026):

- **Zero Trust for PII**: All student data should be treated as sensitive; external API calls must only receive anonymized data ([UpGuard FERPA Guide](https://www.upguard.com/blog/ferpa-compliance-guide))
- **Audit Logging**: Every access and processing step must be logged with timestamps - the current system implements this via structlog ([Kiteworks FERPA](https://www.kiteworks.com/regulatory-compliance/ferpa-compliance/))
- **Vendor Management**: Third-party AI services require contractual guarantees (ZDR - Zero Data Retention) ([Microsoft FERPA Compliance](https://learn.microsoft.com/en-us/compliance/regulatory/offering-ferpa))
- **Cyber Threats Increasing**: 18% surge since 2023 in attacks on educational institutions; ransomware exposure averaging $4.45M per incident ([SecurePrivacy K-12](https://secureprivacy.ai/blog/school-data-governance-software-ferpa-coppa-k-12))

### Best Practices for NLP-Based PII Detection

- **Hybrid Approaches Recommended**: Combining rule-based (regex), NER, and ML achieves highest accuracy - this matches the current architecture ([Nature: Hybrid PII Detection](https://www.nature.com/articles/s41598-025-04971-9))
- **PIIvot Framework**: For educational contexts, context-aware PII detection significantly outperforms generic approaches ([PIIvot Paper](https://arxiv.org/html/2505.16931v1))
- **Recall over Precision**: In PII detection, missing a PII instance is worse than false positives; F-beta with beta=2 recommended ([Presidio Evaluation](https://microsoft.github.io/presidio/evaluation/))
- **Microsoft Presidio**: Industry standard open-source tool; configuring properly can boost F-score by ~30% ([Presidio GitHub](https://github.com/microsoft/presidio))

### LanguageTool Integration

- **Local Server Preferred**: Running locally avoids rate limits and ensures FERPA compliance ([language-tool-python PyPI](https://pypi.org/project/language_tool_python/))
- **Performance Note**: n-gram data for advanced detection requires significant I/O; consider server-side processing for large batches ([LanguageTool Forum](https://forum.languagetool.org/t/languagetool-5-5-slower-than-4-5/7396))

### Prior Art

- **Microsoft Presidio**: Already integrated; used for NER-based PII detection
- **GLiNER**: Listed as dependency for name detection - a lightweight NER model
- **spaCy**: Used for NLP tasks; supports batch processing for performance

### Pitfalls to Avoid

1. **Over-reliance on regex alone**: Will miss contextual PII like nicknames
2. **Presidio default models**: May need fine-tuning for educational domain (teacher names vs student names)
3. **LanguageTool startup latency**: Cold start can take 10-30 seconds
4. **Inconsistent placeholder formats**: Can leak information if patterns are predictable

## Codebase Analysis

### Current Architecture

```
Document Input (.docx)
       |
       v
+------------------+
| Stage 0          |  LOCAL - Document Ingestion
| DocumentParser   |  Parses Word docs, extracts student/grade/comment
+------------------+
       |
       v
+------------------+
| Stage 1          |  LOCAL - Grammar/Spelling
| GrammarChecker   |  LanguageTool integration
+------------------+
       |
       v
+------------------+
| Stage 2          |  LOCAL - Name Verification
| (NOT IMPLEMENTED)|  Should verify names match expected student
+------------------+
       |
       v
+------------------+
| Stage 3          |  LOCAL - FERPA GATE
| Anonymization    |  PII detection (roster + Presidio) & replacement
+------------------+
       |
       v
+------------------+
| Stage 4          |  EXTERNAL API (anonymized only)
| (NOT IMPLEMENTED)|  Semantic analysis: completeness, consistency
+------------------+
       |
       v
+------------------+
| Stage 5          |  LOCAL - Human Review
| (NOT IMPLEMENTED)|  De-anonymize for display, accept/reject
+------------------+
```

### Existing Patterns

**Pydantic Models** (`models.py`):
- Immutable data models using `frozen=True`
- Computed properties for aggregations
- Strong typing with enums for confidence levels and status

**Structured Logging** (throughout):
- Uses `structlog` consistently
- Contextual logging with doc_id, counts, etc.

**Factory Pattern** (`create_*` functions):
- Each stage has a factory function accepting config dict
- Allows flexible initialization from YAML config

**FERPA Gate Pattern** (`stage_3_anonymize.py`):
- `AnonymizationGate` class enforces PII removal before API access
- Double verification: detect -> anonymize -> re-detect to verify

### Dependencies

From `pyproject.toml`:

| Dependency | Version | Purpose | Status |
|------------|---------|---------|--------|
| python-docx | >=1.1.0 | Document parsing | Used in Stage 0 |
| language-tool-python | >=2.8 | Grammar checking | Used in Stage 1 |
| gliner | >=0.2.0 | Name detection | Listed but not imported |
| spacy | >=3.7.0 | NLP/NER | Used via Presidio |
| rapidfuzz | >=3.5.0 | Fuzzy matching | Listed but not used |
| presidio-analyzer | >=2.2.0 | PII detection | Used in Stage 3 |
| presidio-anonymizer | >=2.2.0 | PII replacement | Listed but not used |
| anthropic | >=0.18.0 | API client | For Stage 4 (not implemented) |
| pydantic | >=2.5.0 | Data models | Core dependency |
| structlog | >=24.1.0 | Logging | Used throughout |

### Constraints Identified

1. **Missing Package Structure**:
   - `pyproject.toml` expects `src/ferpa_feedback/` directory structure
   - Current files are at project root
   - Import statements (`from ferpa_feedback...`) will fail without proper structure

2. **Missing Stage 2 Implementation**:
   - `pipeline.py` imports `NameVerificationProcessor` and `create_name_processor`
   - No `stage_2_names.py` file exists
   - Pipeline will crash when name_matching is enabled

3. **Missing Stages 4 and 5**:
   - Semantic analysis (completeness, consistency) not implemented
   - Human review queue not implemented
   - These are referenced in models but not in pipeline

4. **Duplicate Ingestion Files**:
   - `stage_0_ingestion_improved.py` exists with enhanced functionality
   - Pipeline imports from `stage_0_ingestion` (original, not found)
   - The improved version has better format detection and validation

5. **Inconsistent Model Definitions**:
   - `stage_0_ingestion_improved.py` defines its own `StudentComment` dataclass
   - `models.py` defines a Pydantic `StudentComment` model
   - These are incompatible (dataclass vs Pydantic, different fields)

## Feasibility Assessment

| Aspect | Assessment | Notes |
|--------|------------|-------|
| Technical Viability | High | Core architecture is sound; improvements are extensions |
| Effort Estimate | M-L | Need to complete missing stages, fix structure |
| Risk Level | Medium | Model inconsistencies need careful resolution |

### Specific Assessments

| Improvement Area | Feasibility | Effort | Priority |
|-----------------|-------------|--------|----------|
| Fix project structure | High | S | Critical |
| Reconcile model definitions | High | M | Critical |
| Implement Stage 2 (names) | High | M | High |
| Implement Stage 4 (semantic) | High | M | High |
| Implement Stage 5 (review) | Medium | L | Medium |
| Performance optimization | High | M | Medium |
| Add test coverage | High | M | High |

## Recommendations for Requirements

### Critical Path (Must Fix)

1. **Fix Project Structure**: Create proper `src/ferpa_feedback/` directory and move/organize files according to `pyproject.toml` expectations

2. **Reconcile Model Definitions**: Decide between dataclass and Pydantic versions of `StudentComment` and `TeacherDocument`; the Pydantic version in `models.py` is more feature-complete but `stage_0_ingestion_improved.py` has better parsing

3. **Implement Stage 2 (Name Verification)**:
   - Use GLiNER for NER-based name extraction (already a dependency)
   - Use rapidfuzz for fuzzy matching (already a dependency)
   - Integrate with roster for expected name matching

### High Priority Improvements

4. **Implement Stage 4 (Semantic Analysis)**:
   - Completeness check: Does comment provide actionable feedback?
   - Grade consistency: Does comment tone match assigned grade?
   - Use Anthropic API (already a dependency) with ZDR configuration
   - Implement rate limiting and retry logic

5. **Optimize Presidio Configuration**:
   - Add custom recognizers for educational domain
   - Consider using batch mode for document processing
   - Tune recall/precision trade-off (prefer recall)

6. **LanguageTool Performance**:
   - Implement lazy loading (already partially done)
   - Consider persistent server for batch processing
   - Add caching for repeated text patterns

### Medium Priority

7. **Implement Stage 5 (Human Review)**:
   - FastAPI endpoint (dependency in optional group)
   - De-anonymization for display
   - Accept/reject/modify workflow
   - Audit trail for decisions

8. **Add Comprehensive Testing**:
   - Unit tests for each stage
   - Integration tests for pipeline
   - Test fixtures with realistic documents
   - PII detection coverage tests

9. **Configuration Validation**:
   - Currently no validation of YAML config
   - Add Pydantic settings for config validation
   - Fail fast on invalid configuration

### Enhancement Opportunities

10. **Batch Processing Optimization**:
    - Parallel processing of independent comments
    - Batch mode for Presidio NER
    - Connection pooling for LanguageTool

11. **Enhanced Validation in Stage 0**:
    - The improved parser has good validation flags
    - Integrate with name matching for better cross-validation
    - Add configurable word count thresholds

12. **Metrics and Monitoring**:
    - Processing time per stage
    - PII detection statistics
    - Grammar issue patterns
    - Human review acceptance rates

## Open Questions

1. **Model Consolidation Strategy**: Should the improved ingestion parser (`stage_0_ingestion_improved.py`) replace the expected original, or should its features be merged into the Pydantic-based approach?

2. **Roster Source**: How will rosters be provided? CSV is supported, but what about SIS (Student Information System) integration?

3. **API Configuration**: What ZDR (Zero Data Retention) settings are required for the Anthropic API? Are there specific prompt constraints?

4. **Review Workflow**: Who performs human review? What is the expected volume? This affects UI design decisions.

5. **Deployment Model**: Will this run as a service or CLI tool? Affects LanguageTool lifecycle management.

6. **Multi-tenancy**: Is this for a single school or multiple? Affects roster management and data isolation.

## Related Specs

No other specs found in the `./specs/` directory.

## Sources

### Web Sources
- [UpGuard FERPA Compliance Guide](https://www.upguard.com/blog/ferpa-compliance-guide)
- [Kiteworks FERPA Compliance](https://www.kiteworks.com/regulatory-compliance/ferpa-compliance/)
- [Microsoft FERPA Compliance](https://learn.microsoft.com/en-us/compliance/regulatory/offering-ferpa)
- [SecurePrivacy K-12 Data Governance](https://secureprivacy.ai/blog/school-data-governance-software-ferpa-coppa-k-12)
- [PIIvot: NLP Anonymization Framework](https://arxiv.org/html/2505.16931v1)
- [Nature: Hybrid PII Detection](https://www.nature.com/articles/s41598-025-04971-9)
- [Microsoft Presidio GitHub](https://github.com/microsoft/presidio)
- [Presidio Evaluation Guide](https://microsoft.github.io/presidio/evaluation/)
- [language-tool-python PyPI](https://pypi.org/project/language_tool_python/)

### Codebase Files Analyzed
- `/Users/alove/FERPA Comment system/README.md`
- `/Users/alove/FERPA Comment system/pipeline.py`
- `/Users/alove/FERPA Comment system/models.py`
- `/Users/alove/FERPA Comment system/stage_0_ingestion_improved.py`
- `/Users/alove/FERPA Comment system/stage_1_grammar.py`
- `/Users/alove/FERPA Comment system/stage_3_anonymize.py`
- `/Users/alove/FERPA Comment system/pyproject.toml`
