"""Preview engine — dry-run rule evaluation.

Evaluates rules against files without executing any actions.  Produces
a report of what *would* happen if the rules were applied.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from loguru import logger

from file_organizer.services.copilot.rules.models import (
    ConditionType,
    Rule,
    RuleCondition,
    RuleSet,
)


@dataclass
class FileMatch:
    """A file that matched a rule."""

    file_path: str
    rule_name: str
    action_type: str
    destination: str
    confidence: float = 1.0


@dataclass
class PreviewResult:
    """Result of a dry-run rule evaluation.

    Attributes:
        matches: Files that matched at least one rule.
        unmatched: Files that matched no rules.
        errors: Files that could not be evaluated.
        total_files: Total files scanned.
    """

    matches: list[FileMatch] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    total_files: int = 0

    @property
    def match_count(self) -> int:
        """Number of files matched."""
        return len(self.matches)

    @property
    def summary(self) -> str:
        """Human-readable summary string."""
        return (
            f"{self.match_count} matched, "
            f"{len(self.unmatched)} unmatched, "
            f"{len(self.errors)} errors "
            f"(of {self.total_files} total)"
        )


class PreviewEngine:
    """Evaluate rules against a directory tree without executing actions.

    Usage::

        engine = PreviewEngine()
        result = engine.preview(rule_set, Path("~/Downloads"))
    """

    def preview(
        self,
        rule_set: RuleSet,
        target_dir: str | Path,
        *,
        recursive: bool = True,
        max_files: int = 500,
    ) -> PreviewResult:
        """Evaluate all enabled rules against files in *target_dir*.

        Args:
            rule_set: The rules to evaluate.
            target_dir: Directory to scan.
            recursive: Whether to recurse into subdirectories.
            max_files: Maximum number of files to scan.

        Returns:
            A ``PreviewResult`` with match details.
        """
        target = Path(target_dir).expanduser().resolve()
        result = PreviewResult()

        if not target.is_dir():
            result.errors.append((str(target), "Not a directory"))
            return result

        rules = rule_set.enabled_rules
        if not rules:
            logger.debug("No enabled rules in set '{}'", rule_set.name)
            return result

        # Collect files
        files: list[Path] = []
        try:
            pattern = target.rglob("*") if recursive else target.iterdir()
            for entry in pattern:
                if entry.is_file():
                    files.append(entry)
                    if len(files) >= max_files:
                        break
        except PermissionError as exc:
            result.errors.append((str(target), f"Permission denied: {exc}"))

        result.total_files = len(files)

        # Evaluate each file against rules (first matching rule wins)
        for file_path in files:
            matched = False
            for rule in rules:
                if self._matches_rule(file_path, rule):
                    dest = self._resolve_destination(file_path, rule)
                    result.matches.append(
                        FileMatch(
                            file_path=str(file_path),
                            rule_name=rule.name,
                            action_type=rule.action.action_type.value,
                            destination=dest,
                        )
                    )
                    matched = True
                    break  # first match wins

            if not matched:
                result.unmatched.append(str(file_path))

        return result

    # ------------------------------------------------------------------
    # Condition evaluation
    # ------------------------------------------------------------------

    def _matches_rule(self, file_path: Path, rule: Rule) -> bool:
        """Check if a file satisfies all conditions of a rule.

        Args:
            file_path: The file to test.
            rule: The rule with conditions.

        Returns:
            True if all conditions match.
        """
        for condition in rule.conditions:
            result = self._evaluate_condition(file_path, condition)
            if condition.negate:
                result = not result
            if not result:
                return False
        return True

    @staticmethod
    def _evaluate_condition(file_path: Path, condition: RuleCondition) -> bool:
        """Evaluate a single condition against a file.

        Args:
            file_path: The file to test.
            condition: The condition to evaluate.

        Returns:
            True if the condition is satisfied.
        """
        ct = condition.condition_type
        value = condition.value

        if ct == ConditionType.EXTENSION:
            extensions = [v.strip().lower() for v in value.split(",")]
            return file_path.suffix.lower() in extensions

        if ct == ConditionType.NAME_PATTERN:
            return fnmatch.fnmatch(file_path.name.lower(), value.lower())

        if ct == ConditionType.SIZE_GREATER:
            try:
                return file_path.stat().st_size > int(value)
            except (OSError, ValueError):
                return False

        if ct == ConditionType.SIZE_LESS:
            try:
                return file_path.stat().st_size < int(value)
            except (OSError, ValueError):
                return False

        if ct == ConditionType.CONTENT_CONTAINS:
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                return value.lower() in text.lower()
            except OSError:
                return False

        if ct == ConditionType.MODIFIED_BEFORE:
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                threshold = datetime.fromisoformat(value)
                return mtime < threshold
            except (OSError, ValueError):
                return False

        if ct == ConditionType.MODIFIED_AFTER:
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                threshold = datetime.fromisoformat(value)
                return mtime > threshold
            except (OSError, ValueError):
                return False

        if ct == ConditionType.PATH_MATCHES:
            return bool(re.search(value, str(file_path), re.IGNORECASE))

        return False

    @staticmethod
    def _resolve_destination(file_path: Path, rule: Rule) -> str:
        """Compute the destination path for a matched file.

        Supports simple template variables: ``{name}``, ``{ext}``, ``{stem}``.

        Args:
            file_path: The source file.
            rule: The matched rule.

        Returns:
            Resolved destination string.
        """
        dest = rule.action.destination
        if not dest:
            return str(file_path.parent)

        return dest.format(
            name=file_path.name,
            ext=file_path.suffix.lstrip("."),
            stem=file_path.stem,
        )
