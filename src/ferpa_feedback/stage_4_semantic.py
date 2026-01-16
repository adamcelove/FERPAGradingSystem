"""
Stage 4: Semantic Analysis

This stage performs semantic analysis on comments using Claude API,
including completeness and consistency checks.

CRITICAL: This stage MUST only receive anonymized text. The
FERPAEnforcedClient ensures the FERPA gate is checked before
every API call.

Key features:
- FERPA gate enforcement before all API calls
- Zero Data Retention (ZDR) headers for compliance
- Completeness analysis (specificity, actionability, etc.)
- Grade-comment consistency detection
- Exponential backoff retry for API reliability
"""

import json
import time
from typing import Any

import structlog

from ferpa_feedback.models import (
    CompletenessResult,
    ConfidenceLevel,
    ConsistencyResult,
    StudentComment,
    TeacherDocument,
)
from ferpa_feedback.stage_3_anonymize import AnonymizationGate

logger = structlog.get_logger()


class FERPAViolationError(Exception):
    """
    Raised when attempting to send PII to external API.

    This exception indicates a critical compliance failure where
    text that has not been properly anonymized would have been
    sent to an external API.
    """
    pass


class FERPAEnforcedClient:
    """
    Anthropic client that enforces FERPA gate before all calls.

    This wrapper ensures no PII can reach the Claude API by requiring
    an AnonymizationGate and validating text before every request.
    """

    def __init__(
        self,
        api_key: str | None = None,
        gate: AnonymizationGate | None = None,
        enable_zdr: bool = True,
    ):
        """
        Initialize FERPA-enforced client.

        Args:
            api_key: Anthropic API key (or from env ANTHROPIC_API_KEY).
            gate: FERPA anonymization gate (required).
            enable_zdr: Include zero data retention headers.

        Raises:
            ValueError: If gate is not provided.
        """
        if gate is None:
            raise ValueError("FERPA gate is required for API client")

        self.gate = gate
        self.enable_zdr = enable_zdr
        self._api_key = api_key
        self._client: Any | None = None  # Lazy load

        logger.info(
            "ferpa_client_initialized",
            enable_zdr=enable_zdr,
        )

    @property
    def client(self) -> Any | None:
        """Lazy-load Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
                logger.info("anthropic_client_loaded")
            except ImportError:
                logger.warning("anthropic_not_installed")
                # Will raise in analyze() if called
        return self._client

    def analyze(
        self,
        comment: StudentComment,
        prompt: str,
        max_tokens: int = 1000,
    ) -> dict[str, Any]:
        """
        Send anonymized text to API with FERPA enforcement.

        Args:
            comment: The comment to analyze (must be anonymized).
            prompt: The analysis prompt.
            max_tokens: Maximum tokens in response.

        Returns:
            API response as dictionary.

        Raises:
            FERPAViolationError: If comment fails FERPA gate.
            ImportError: If anthropic is not installed.
        """
        safe_text = self.gate.get_safe_text(comment)
        if safe_text is None:
            raise FERPAViolationError(
                f"Comment {comment.id} blocked by FERPA gate"
            )

        logger.info(
            "api_call_authorized",
            comment_id=comment.id,
        )

        # Build headers
        extra_headers = {}
        if self.enable_zdr:
            extra_headers["anthropic-beta"] = "zero-data-retention-2024-08-01"

        # Check if client is available
        if self.client is None:
            logger.warning(
                "api_call_skipped",
                reason="anthropic_not_available",
                comment_id=comment.id,
            )
            return {}

        # Make actual API call
        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                extra_headers=extra_headers if extra_headers else None,
                messages=[
                    {
                        "role": "user",
                        "content": prompt.format(comment_text=safe_text),
                    }
                ],
            )

            # Extract text content from response
            response_text = ""
            if message.content:
                for block in message.content:
                    if hasattr(block, "text"):
                        response_text += block.text

            logger.info(
                "api_call_complete",
                comment_id=comment.id,
                response_length=len(response_text),
            )

            return {"text": response_text, "model": message.model}

        except Exception as e:
            logger.error(
                "api_call_failed",
                comment_id=comment.id,
                error=str(e),
            )
            raise


class CompletenessAnalyzer:
    """
    Analyzes comment completeness using rubric and LLM.

    Evaluates comments against criteria:
    - Specificity: Does it mention specific behaviors/work?
    - Actionability: Does it provide actionable feedback?
    - Evidence: Is there evidence supporting the assessment?
    - Length: Is it appropriately detailed?
    - Tone: Is the tone professional and constructive?

    Uses Claude API for real analysis with exponential backoff retry.
    Falls back to stub if API is unavailable.
    """

    # Prompt template for completeness evaluation
    COMPLETENESS_PROMPT = """Analyze the following student feedback comment for completeness.

Comment to analyze:
"{comment_text}"

Evaluate the comment on these criteria (score each 0.0 to 1.0):
1. SPECIFICITY: Does it mention specific behaviors, work, or examples?
2. ACTIONABILITY: Does it provide clear guidance for improvement?
3. EVIDENCE: Is there concrete evidence supporting the assessment?
4. LENGTH: Is it appropriately detailed (not too brief, not excessive)?
5. TONE: Is it professional, constructive, and appropriate?

Respond ONLY with valid JSON in this exact format:
{{
  "specificity_score": 0.0,
  "actionability_score": 0.0,
  "evidence_score": 0.0,
  "length_score": 0.0,
  "tone_score": 0.0,
  "missing_elements": ["element1", "element2"],
  "explanation": "Brief explanation of the assessment"
}}

Rules:
- Scores must be between 0.0 and 1.0
- missing_elements should list what would improve the comment
- explanation should be 1-2 sentences
- Output ONLY the JSON, no other text"""

    # Retry configuration: 3 retries with 1s, 2s, 4s delays
    MAX_RETRIES = 3
    RETRY_DELAYS = [1.0, 2.0, 4.0]

    def __init__(
        self,
        client: FERPAEnforcedClient | None = None,
        rubric_path: str | None = None,
    ):
        """
        Initialize completeness analyzer.

        Args:
            client: FERPA-enforced API client (optional for stub).
            rubric_path: Path to completeness_rubric.yaml.
        """
        self.client = client
        self.rubric_path = rubric_path

        logger.info("completeness_analyzer_initialized")

    def _call_api_with_retry(self, comment: StudentComment) -> dict[str, Any] | None:
        """
        Call API with exponential backoff retry logic.

        Args:
            comment: The comment to analyze.

        Returns:
            API response dict or None if all retries failed.
        """
        if self.client is None:
            return None

        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.analyze(
                    comment=comment,
                    prompt=self.COMPLETENESS_PROMPT,
                    max_tokens=500,
                )
                return response

            except Exception as e:
                last_error = e
                delay = self.RETRY_DELAYS[attempt] if attempt < len(self.RETRY_DELAYS) else self.RETRY_DELAYS[-1]

                logger.warning(
                    "completeness_api_retry",
                    comment_id=comment.id,
                    attempt=attempt + 1,
                    max_attempts=self.MAX_RETRIES,
                    delay_seconds=delay,
                    error=str(e),
                )

                # Check if this is a rate limit error
                error_str = str(e).lower()
                if "rate" in error_str or "429" in error_str:
                    # Double the delay for rate limits
                    delay *= 2
                    logger.info(
                        "rate_limit_detected",
                        comment_id=comment.id,
                        extended_delay=delay,
                    )

                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(delay)

        logger.error(
            "completeness_api_failed",
            comment_id=comment.id,
            error=str(last_error) if last_error else "unknown",
        )
        return None

    def _parse_response(self, response_text: str) -> dict[str, Any] | None:
        """
        Parse JSON response from Claude API.

        Args:
            response_text: Raw text response from API.

        Returns:
            Parsed dictionary or None if parsing fails.
        """
        try:
            # Try to extract JSON from response
            text = response_text.strip()

            # Handle markdown code blocks
            if text.startswith("```"):
                # Find the JSON content between code blocks
                lines = text.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith("```") and not in_json:
                        in_json = True
                        continue
                    elif line.startswith("```") and in_json:
                        break
                    elif in_json:
                        json_lines.append(line)
                text = "\n".join(json_lines)

            # Parse JSON
            data: dict[str, Any] = json.loads(text)
            return data

        except json.JSONDecodeError as e:
            logger.warning(
                "completeness_parse_failed",
                error=str(e),
                response_preview=response_text[:200],
            )
            return None

    def _create_result_from_api(self, data: dict[str, Any]) -> CompletenessResult:
        """
        Create CompletenessResult from parsed API response.

        Args:
            data: Parsed JSON response.

        Returns:
            CompletenessResult model.
        """
        # Extract scores with defaults
        specificity = float(data.get("specificity_score", 0.5))
        actionability = float(data.get("actionability_score", 0.5))
        evidence = float(data.get("evidence_score", 0.5))
        length = float(data.get("length_score", 0.5))
        tone = float(data.get("tone_score", 0.5))

        # Clamp scores to valid range
        specificity = max(0.0, min(1.0, specificity))
        actionability = max(0.0, min(1.0, actionability))
        evidence = max(0.0, min(1.0, evidence))
        length = max(0.0, min(1.0, length))
        tone = max(0.0, min(1.0, tone))

        # Calculate overall score (weighted average)
        overall_score = (
            specificity * 0.25 +
            actionability * 0.25 +
            evidence * 0.20 +
            length * 0.15 +
            tone * 0.15
        )

        # Determine completeness threshold
        is_complete = overall_score >= 0.6

        # Determine confidence based on score distribution
        scores = [specificity, actionability, evidence, length, tone]
        score_variance = sum((s - overall_score) ** 2 for s in scores) / len(scores)

        if score_variance < 0.05:
            confidence = ConfidenceLevel.HIGH
        elif score_variance < 0.15:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        # Extract missing elements and explanation
        missing_elements = data.get("missing_elements", [])
        if not isinstance(missing_elements, list):
            missing_elements = []
        missing_elements = [str(elem) for elem in missing_elements]

        explanation = str(data.get("explanation", ""))

        return CompletenessResult(
            is_complete=is_complete,
            score=overall_score,
            confidence=confidence,
            specificity_score=specificity,
            actionability_score=actionability,
            evidence_score=evidence,
            length_score=length,
            tone_score=tone,
            missing_elements=missing_elements,
            explanation=explanation,
        )

    def _create_stub_result(self) -> CompletenessResult:
        """
        Create stub result when API is unavailable.

        Returns:
            Default CompletenessResult.
        """
        return CompletenessResult(
            is_complete=True,
            score=0.5,
            confidence=ConfidenceLevel.UNKNOWN,
            specificity_score=0.5,
            actionability_score=0.5,
            evidence_score=0.5,
            length_score=0.5,
            tone_score=0.5,
            missing_elements=[],
            explanation="API unavailable - using stub analysis",
        )

    def analyze(self, comment: StudentComment) -> CompletenessResult:
        """
        Analyze completeness of a single comment.

        Uses Claude API for real analysis with exponential backoff retry.
        Falls back to stub if API is unavailable or fails.

        Args:
            comment: The comment to analyze.

        Returns:
            CompletenessResult with scores and assessment.
        """
        # Try to use real API
        if self.client is not None:
            response = self._call_api_with_retry(comment)

            if response and response.get("text"):
                parsed = self._parse_response(response["text"])

                if parsed:
                    logger.info(
                        "completeness_analysis_complete",
                        comment_id=comment.id,
                        used_api=True,
                    )
                    return self._create_result_from_api(parsed)

        # Fall back to stub
        logger.debug(
            "completeness_analysis_stub",
            comment_id=comment.id,
            reason="api_unavailable_or_failed",
        )
        return self._create_stub_result()


class ConsistencyAnalyzer:
    """
    Analyzes grade-comment consistency.

    Detects misalignment between assigned grades and comment sentiment.
    For example, a low grade with only positive comments may indicate
    a copy-paste error or misassignment.

    Uses Claude API for real analysis with exponential backoff retry.
    Falls back to stub if API is unavailable.
    """

    # Prompt template for consistency evaluation
    CONSISTENCY_PROMPT = """Analyze whether the following student feedback comment is consistent with the assigned grade.

Grade assigned: {grade}

Comment to analyze:
"{comment_text}"

Determine if the comment sentiment aligns with what you would expect for this grade level:
- High grades (A, A+, A-, 90%+): Should have predominantly positive sentiment
- Medium grades (B, C, 70-89%): Should have mixed or constructive sentiment
- Low grades (D, F, below 70%): Should address concerns or areas for improvement

Respond ONLY with valid JSON in this exact format:
{{
  "is_consistent": true,
  "grade_sentiment": "positive",
  "comment_sentiment": "positive",
  "conflicting_phrases": [],
  "explanation": "Brief explanation of the consistency assessment"
}}

Rules:
- is_consistent: true if comment sentiment matches grade expectations, false if misaligned
- grade_sentiment: expected sentiment based on grade ("positive", "neutral", "negative", "mixed")
- comment_sentiment: actual sentiment detected in comment ("positive", "neutral", "negative", "mixed")
- conflicting_phrases: list of specific phrases that conflict with the grade (empty if consistent)
- explanation: 1-2 sentences explaining the assessment
- Output ONLY the JSON, no other text"""

    # Retry configuration: 3 retries with 1s, 2s, 4s delays
    MAX_RETRIES = 3
    RETRY_DELAYS = [1.0, 2.0, 4.0]

    def __init__(self, client: FERPAEnforcedClient | None = None):
        """
        Initialize consistency analyzer.

        Args:
            client: FERPA-enforced API client (optional for stub).
        """
        self.client = client

        logger.info("consistency_analyzer_initialized")

    def _call_api_with_retry(
        self,
        comment: StudentComment,
        grade: str,
    ) -> dict[str, Any] | None:
        """
        Call API with exponential backoff retry logic.

        Args:
            comment: The comment to analyze.
            grade: The assigned grade.

        Returns:
            API response dict or None if all retries failed.
        """
        if self.client is None:
            return None

        last_error: Exception | None = None

        # Format prompt with grade
        prompt_with_grade = self.CONSISTENCY_PROMPT.replace("{grade}", grade)

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.analyze(
                    comment=comment,
                    prompt=prompt_with_grade,
                    max_tokens=500,
                )
                return response

            except Exception as e:
                last_error = e
                delay = self.RETRY_DELAYS[attempt] if attempt < len(self.RETRY_DELAYS) else self.RETRY_DELAYS[-1]

                logger.warning(
                    "consistency_api_retry",
                    comment_id=comment.id,
                    attempt=attempt + 1,
                    max_attempts=self.MAX_RETRIES,
                    delay_seconds=delay,
                    error=str(e),
                )

                # Check if this is a rate limit error
                error_str = str(e).lower()
                if "rate" in error_str or "429" in error_str:
                    # Double the delay for rate limits
                    delay *= 2
                    logger.info(
                        "rate_limit_detected",
                        comment_id=comment.id,
                        extended_delay=delay,
                    )

                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(delay)

        logger.error(
            "consistency_api_failed",
            comment_id=comment.id,
            error=str(last_error) if last_error else "unknown",
        )
        return None

    def _parse_response(self, response_text: str) -> dict[str, Any] | None:
        """
        Parse JSON response from Claude API.

        Args:
            response_text: Raw text response from API.

        Returns:
            Parsed dictionary or None if parsing fails.
        """
        try:
            # Try to extract JSON from response
            text = response_text.strip()

            # Handle markdown code blocks
            if text.startswith("```"):
                # Find the JSON content between code blocks
                lines = text.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith("```") and not in_json:
                        in_json = True
                        continue
                    elif line.startswith("```") and in_json:
                        break
                    elif in_json:
                        json_lines.append(line)
                text = "\n".join(json_lines)

            # Parse JSON
            data: dict[str, Any] = json.loads(text)
            return data

        except json.JSONDecodeError as e:
            logger.warning(
                "consistency_parse_failed",
                error=str(e),
                response_preview=response_text[:200],
            )
            return None

    def _create_result_from_api(self, data: dict[str, Any]) -> ConsistencyResult:
        """
        Create ConsistencyResult from parsed API response.

        Args:
            data: Parsed JSON response.

        Returns:
            ConsistencyResult model.
        """
        # Extract fields with defaults
        is_consistent = bool(data.get("is_consistent", True))
        grade_sentiment = str(data.get("grade_sentiment", "neutral"))
        comment_sentiment = str(data.get("comment_sentiment", "neutral"))
        explanation = str(data.get("explanation", ""))

        # Extract conflicting phrases
        conflicting_phrases = data.get("conflicting_phrases", [])
        if not isinstance(conflicting_phrases, list):
            conflicting_phrases = []
        conflicting_phrases = [str(phrase) for phrase in conflicting_phrases]

        # Determine confidence based on sentiment clarity
        if grade_sentiment == comment_sentiment:
            # Clear alignment or misalignment
            confidence = ConfidenceLevel.HIGH
        elif grade_sentiment in ["mixed", "neutral"] or comment_sentiment in ["mixed", "neutral"]:
            # Ambiguous sentiment
            confidence = ConfidenceLevel.MEDIUM
        else:
            # Clear disagreement
            confidence = ConfidenceLevel.HIGH if not is_consistent else ConfidenceLevel.MEDIUM

        return ConsistencyResult(
            is_consistent=is_consistent,
            confidence=confidence,
            grade_sentiment=grade_sentiment,
            comment_sentiment=comment_sentiment,
            explanation=explanation,
            conflicting_phrases=conflicting_phrases,
        )

    def _create_stub_result(self) -> ConsistencyResult:
        """
        Create stub result when API is unavailable.

        Returns:
            Default ConsistencyResult.
        """
        return ConsistencyResult(
            is_consistent=True,
            confidence=ConfidenceLevel.UNKNOWN,
            grade_sentiment="neutral",
            comment_sentiment="neutral",
            explanation="API unavailable - using stub analysis",
            conflicting_phrases=[],
        )

    def analyze(
        self,
        comment: StudentComment,
        grade: str,
    ) -> ConsistencyResult:
        """
        Check if comment sentiment aligns with grade.

        Uses Claude API for real analysis with exponential backoff retry.
        Falls back to stub if API is unavailable or fails.

        Args:
            comment: The student comment.
            grade: The assigned grade (e.g., "A+", "C-", "72%").

        Returns:
            ConsistencyResult with alignment assessment.
        """
        # Try to use real API
        if self.client is not None:
            response = self._call_api_with_retry(comment, grade)

            if response and response.get("text"):
                parsed = self._parse_response(response["text"])

                if parsed:
                    logger.info(
                        "consistency_analysis_complete",
                        comment_id=comment.id,
                        grade=grade,
                        used_api=True,
                    )
                    return self._create_result_from_api(parsed)

        # Fall back to stub
        logger.debug(
            "consistency_analysis_stub",
            comment_id=comment.id,
            grade=grade,
            reason="api_unavailable_or_failed",
        )
        return self._create_stub_result()


class SemanticAnalysisProcessor:
    """
    Main processor for Stage 4 semantic analysis.

    Orchestrates completeness and consistency analysis for comments,
    ensuring FERPA gate is validated before any API calls.
    """

    def __init__(
        self,
        completeness_analyzer: CompletenessAnalyzer,
        consistency_analyzer: ConsistencyAnalyzer,
        ferpa_gate: AnonymizationGate,
    ):
        """
        Initialize semantic analysis processor.

        Args:
            completeness_analyzer: Analyzer for comment completeness.
            consistency_analyzer: Analyzer for grade-comment consistency.
            ferpa_gate: FERPA compliance gate.
        """
        self.completeness_analyzer = completeness_analyzer
        self.consistency_analyzer = consistency_analyzer
        self.ferpa_gate = ferpa_gate

        logger.info("semantic_processor_initialized")

    def process_comment(self, comment: StudentComment) -> StudentComment:
        """
        Run semantic analysis on a single comment.

        CRITICAL: This method verifies FERPA gate before any API calls.

        Args:
            comment: Comment to analyze (must be anonymized).

        Returns:
            Comment with completeness and consistency results.
        """
        # Double-check FERPA gate before any analysis
        if not self.ferpa_gate.validate_for_api(comment):
            logger.error(
                "ferpa_gate_blocked_stage4",
                comment_id=comment.id,
            )
            return comment  # Return unmodified

        # Run completeness analysis
        completeness = self.completeness_analyzer.analyze(comment)

        # Run consistency analysis
        consistency = self.consistency_analyzer.analyze(comment, comment.grade)

        logger.debug(
            "semantic_analysis_complete",
            comment_id=comment.id,
            is_complete=completeness.is_complete,
            is_consistent=consistency.is_consistent,
        )

        # Return new comment with analysis results
        return StudentComment(
            **{
                **comment.model_dump(exclude={"completeness", "consistency"}),
                "completeness": completeness,
                "consistency": consistency,
            }
        )

    def process_document(self, document: TeacherDocument) -> TeacherDocument:
        """
        Process all comments in document through semantic analysis.

        Args:
            document: Document with anonymized comments.

        Returns:
            Document with semantic analysis results.
        """
        logger.info(
            "semantic_analysis_document",
            doc_id=document.id,
            comment_count=len(document.comments),
        )

        processed_comments = []
        analyzed_count = 0
        blocked_count = 0

        for comment in document.comments:
            processed = self.process_comment(comment)
            processed_comments.append(processed)

            # Track statistics
            if processed.completeness is not None:
                analyzed_count += 1
            else:
                blocked_count += 1

        logger.info(
            "semantic_analysis_document_complete",
            doc_id=document.id,
            analyzed=analyzed_count,
            blocked=blocked_count,
        )

        return TeacherDocument(
            **{
                **document.model_dump(exclude={"comments"}),
                "comments": processed_comments,
            }
        )


def create_semantic_processor(
    config: dict[str, Any] | None = None,
    ferpa_gate: AnonymizationGate | None = None,
) -> SemanticAnalysisProcessor:
    """
    Factory function for Stage 4 semantic analysis processor.

    Args:
        config: Configuration dictionary with API settings.
        ferpa_gate: FERPA compliance gate (required).

    Returns:
        Configured SemanticAnalysisProcessor.

    Raises:
        ValueError: If ferpa_gate is not provided.
    """
    if ferpa_gate is None:
        raise ValueError("FERPA gate is required for semantic processor")

    config = config or {}

    # Create FERPA-enforced client
    api_key = config.get("api_key")
    enable_zdr = config.get("enable_zdr", True)

    client = FERPAEnforcedClient(
        api_key=api_key,
        gate=ferpa_gate,
        enable_zdr=enable_zdr,
    )

    # Create analyzers
    completeness_analyzer = CompletenessAnalyzer(
        client=client,
        rubric_path=config.get("rubric_path"),
    )

    consistency_analyzer = ConsistencyAnalyzer(client=client)

    # Create processor
    return SemanticAnalysisProcessor(
        completeness_analyzer=completeness_analyzer,
        consistency_analyzer=consistency_analyzer,
        ferpa_gate=ferpa_gate,
    )
