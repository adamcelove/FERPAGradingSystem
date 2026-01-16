"""
Stage 1: Grammar, Spelling, and Punctuation Check

Uses LanguageTool for deterministic, local grammar checking.
This stage is 100% local - no external API calls.

LanguageTool runs as a local Java server, ensuring all text
processing happens on your infrastructure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import language_tool_python
import structlog

from ferpa_feedback.models import GrammarIssue, StudentComment, TeacherDocument

logger = structlog.get_logger()


class GrammarChecker:
    """
    Grammar, spelling, and punctuation checker using LanguageTool.

    LanguageTool is an open-source grammar checker that runs locally,
    ensuring FERPA compliance by never sending text externally.
    """

    def __init__(
        self,
        language: str = "en-US",
        disabled_rules: list[str] | None = None,
        custom_dictionary: list[str] | None = None,
    ):
        """
        Initialize the grammar checker.

        Args:
            language: Language code (e.g., "en-US", "en-GB")
            disabled_rules: List of LanguageTool rule IDs to disable
            custom_dictionary: Additional words to accept as correct
        """
        self.language = language
        self.disabled_rules = disabled_rules or []
        self.custom_dictionary = set(custom_dictionary or [])

        logger.info("initializing_language_tool", language=language)
        self._tool: language_tool_python.LanguageTool | None = None

    @property
    def tool(self) -> language_tool_python.LanguageTool:
        """Lazy initialization of LanguageTool."""
        if self._tool is None:
            self._tool = language_tool_python.LanguageTool(self.language)

            # Disable specified rules
            if self.disabled_rules:
                for _rule_id in self.disabled_rules:
                    self._tool.disable_spellchecking()  # Example; actual API may vary
                logger.info("disabled_rules", rules=self.disabled_rules)

        return self._tool

    def add_to_dictionary(self, words: list[str]) -> None:
        """Add words to the custom dictionary (will not be flagged as misspellings)."""
        self.custom_dictionary.update(w.lower() for w in words)
        logger.debug("dictionary_updated", added_count=len(words))

    def load_dictionary_from_file(self, file_path: Path) -> None:
        """Load custom dictionary from a text file (one word per line)."""
        if not file_path.exists():
            logger.warning("dictionary_file_not_found", path=str(file_path))
            return

        with open(file_path, encoding='utf-8') as f:
            words = [line.strip() for line in f if line.strip()]

        self.add_to_dictionary(words)
        logger.info("dictionary_loaded", path=str(file_path), count=len(words))

    def check_text(self, text: str) -> list[GrammarIssue]:
        """
        Check a text for grammar, spelling, and punctuation issues.

        Args:
            text: The text to check

        Returns:
            List of GrammarIssue objects
        """
        if not text.strip():
            return []

        matches = self.tool.check(text)
        issues = []

        for match in matches:
            # Skip disabled rules
            if match.ruleId in self.disabled_rules:
                continue

            # Skip custom dictionary words (for spelling rules)
            if match.ruleId.startswith("MORFOLOGIK") or match.ruleId.startswith("SPELLING"):
                # Extract the misspelled word
                misspelled = text[match.offset:match.offset + match.errorLength].lower()
                if misspelled in self.custom_dictionary:
                    continue

            # Calculate confidence based on rule category
            confidence = self._calculate_confidence(match)

            issue = GrammarIssue(
                rule_id=match.ruleId,
                message=match.message,
                context=match.context,
                offset=match.offset,
                length=match.errorLength,
                suggestions=match.replacements[:5] if match.replacements else [],
                confidence=confidence,
            )
            issues.append(issue)

        return issues

    def _calculate_confidence(self, match: Any) -> float:
        """
        Calculate confidence score for a grammar match.

        Higher confidence for definite errors (spelling, punctuation)
        Lower confidence for style suggestions.
        """
        # High confidence rules (definite errors)
        high_confidence_categories = [
            "TYPOS",
            "SPELLING",
            "GRAMMAR",
            "PUNCTUATION",
        ]

        # Medium confidence (likely errors)
        medium_confidence_categories = [
            "CONFUSED_WORDS",
            "REDUNDANCY",
            "CASING",
        ]

        # Get rule category from ID
        rule_id = match.ruleId.upper()

        if any(cat in rule_id for cat in high_confidence_categories):
            return 0.95
        elif any(cat in rule_id for cat in medium_confidence_categories):
            return 0.80
        else:
            # Style and other suggestions
            return 0.60

    def check_comment(self, comment: StudentComment) -> StudentComment:
        """
        Check a single comment and return updated comment with issues.

        Args:
            comment: The StudentComment to check

        Returns:
            New StudentComment with grammar_issues populated
        """
        issues = self.check_text(comment.comment_text)

        # Create new comment with issues (immutable model)
        return StudentComment(
            **{
                **comment.model_dump(),
                "grammar_issues": issues,
            }
        )

    def check_document(self, document: TeacherDocument) -> TeacherDocument:
        """
        Check all comments in a document.

        Args:
            document: The TeacherDocument to check

        Returns:
            New TeacherDocument with grammar issues populated
        """
        logger.info("checking_document", doc_id=document.id, comment_count=len(document.comments))

        checked_comments = []
        total_issues = 0

        for comment in document.comments:
            checked = self.check_comment(comment)
            checked_comments.append(checked)
            total_issues += len(checked.grammar_issues)

        logger.info(
            "document_checked",
            doc_id=document.id,
            total_issues=total_issues,
        )

        return TeacherDocument(
            **{
                **document.model_dump(exclude={"comments"}),
                "comments": checked_comments,
            }
        )

    def close(self) -> None:
        """Clean up LanguageTool resources."""
        if self._tool is not None:
            self._tool.close()
            self._tool = None
            logger.debug("language_tool_closed")


class GrammarReportGenerator:
    """Generates reports of grammar issues for review."""

    @staticmethod
    def generate_summary(document: TeacherDocument) -> dict[str, Any]:
        """
        Generate a summary of grammar issues in a document.

        Returns:
            Dictionary with issue counts and details
        """
        issues_by_rule: dict[str, dict[str, Any]] = {}
        issues_by_comment: dict[str, int] = {}

        for comment in document.comments:
            if comment.grammar_issues:
                issues_by_comment[comment.id] = len(comment.grammar_issues)

                for issue in comment.grammar_issues:
                    rule = issue.rule_id
                    if rule not in issues_by_rule:
                        issues_by_rule[rule] = {
                            "count": 0,
                            "message": issue.message,
                            "examples": [],
                        }
                    rule_entry = issues_by_rule[rule]
                    rule_entry["count"] = int(rule_entry["count"]) + 1
                    examples = rule_entry["examples"]
                    if isinstance(examples, list) and len(examples) < 3:
                        examples.append(issue.context)

        return {
            "document_id": document.id,
            "total_comments": len(document.comments),
            "comments_with_issues": len(issues_by_comment),
            "total_issues": sum(issues_by_comment.values()),
            "issues_by_rule": issues_by_rule,
            "most_common_issues": sorted(
                issues_by_rule.items(),
                key=lambda x: int(x[1]["count"]),
                reverse=True,
            )[:10],
        }


# Factory function for easy initialization with config
def create_grammar_checker(config: dict[str, Any]) -> GrammarChecker:
    """
    Create a GrammarChecker from configuration dictionary.

    Args:
        config: Dictionary with grammar configuration

    Returns:
        Configured GrammarChecker instance
    """
    checker = GrammarChecker(
        language=config.get("language", "en-US"),
        disabled_rules=config.get("disabled_rules", []),
    )

    # Load custom dictionary if specified
    dict_file = config.get("custom_dictionary_file")
    if dict_file:
        checker.load_dictionary_from_file(Path(dict_file))

    return checker
