"""Rule execution engine for persisted copilot rules."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from file_organizer.history.models import OperationType
from file_organizer.services.copilot.rules.actions import (
    ConflictStrategy,
    LinkResult,
    apply_hardlink,
    apply_symlink,
    copy_file,
    resolve_conflict,
)
from file_organizer.services.copilot.rules.models import ActionType, Rule, RuleSet
from file_organizer.services.copilot.rules.preview import PreviewEngine
from file_organizer.undo import UndoManager
from file_organizer.undo._journal import default_journal_path
from file_organizer.undo.durable_move import durable_move


class PostMutationError(Exception):
    """Raised when an error occurs after a filesystem mutation was performed."""


@dataclass
class ExecutionResult:
    """Outcome for one file matched by one rule."""

    file_path: str
    rule_name: str
    action_type: str
    destination: str = ""
    status: str = "pending"
    message: str = ""


@dataclass
class ApplyResult:
    """Aggregate result for a rules apply run."""

    results: list[ExecutionResult] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    total_files: int = 0
    transaction_id: str | None = None

    @property
    def applied_count(self) -> int:
        """Number of actions that changed the filesystem."""
        return len([r for r in self.results if r.status == "applied"])

    @property
    def skipped_count(self) -> int:
        """Number of matched actions skipped by conflict or dry-run."""
        return len([r for r in self.results if r.status == "skipped"])

    @property
    def failed_count(self) -> int:
        """Number of matched actions that failed."""
        return len([r for r in self.results if r.status == "failed"])

    @property
    def summary(self) -> str:
        """Human-readable summary string."""
        return (
            f"{self.applied_count} applied, {self.skipped_count} skipped, "
            f"{self.failed_count} failed (of {self.total_files} scanned)"
        )


class RuleExecutor:
    """Apply rule actions using the same matching logic as preview."""

    def __init__(
        self,
        *,
        undo_manager: UndoManager | None = None,
        preview_engine: PreviewEngine | None = None,
    ) -> None:
        """Initialize the executor with optional collaborators for tests."""
        self._undo_manager = undo_manager
        self._preview_engine = preview_engine or PreviewEngine()

    def apply(
        self,
        rule_set: RuleSet,
        target_dir: str | Path,
        *,
        recursive: bool = True,
        max_files: int = 500,
        dry_run: bool = False,
    ) -> ApplyResult:
        """Apply enabled rules to files under *target_dir*."""
        target = Path(target_dir).expanduser().resolve()
        preview = self._preview_engine.preview(
            rule_set,
            target,
            recursive=recursive,
            max_files=max_files,
        )
        result = ApplyResult(errors=list(preview.errors), total_files=preview.total_files)
        rules_by_name = {rule.name: rule for rule in rule_set.enabled_rules}

        if dry_run:
            for match in preview.matches:
                result.results.append(
                    ExecutionResult(
                        file_path=match.file_path,
                        rule_name=match.rule_name,
                        action_type=match.action_type,
                        destination=match.destination,
                        status="skipped",
                        message="dry-run",
                    )
                )
            return result

        undo_manager = self._undo_manager or UndoManager()
        transaction_id = undo_manager.history.start_transaction(
            metadata={"rule_set": rule_set.name, "target_dir": str(target)}
        )
        result.transaction_id = transaction_id

        try:
            for match in preview.matches:
                rule = rules_by_name.get(match.rule_name)
                if rule is None:
                    continue
                source = Path(match.file_path)
                try:
                    if self._inside_destination_root(
                        source, match.destination, rule.action.action_type, target
                    ):
                        result.results.append(
                            self._skipped(rule, source, source, "inside destination")
                        )
                        continue
                    result.results.append(
                        self._execute_match(
                            rule,
                            source,
                            match.destination,
                            target,
                            undo_manager,
                            transaction_id,
                        )
                    )
                except ValueError as val_exc:
                    result.results.append(
                        ExecutionResult(
                            file_path=str(source),
                            rule_name=rule.name,
                            action_type=rule.action.action_type.value,
                            destination=match.destination,
                            status="failed",
                            message=str(val_exc),
                        )
                    )
        except Exception:
            logger.exception(
                "Rule execution failed; leaving transaction {} uncommitted", transaction_id
            )
            raise
        else:
            undo_manager.history.commit_transaction(transaction_id)

        return result

    def watch(
        self,
        rule_set: RuleSet,
        target_dir: str | Path,
        *,
        recursive: bool = True,
        max_files: int = 500,
        interval_seconds: float = 10.0,
        once: bool = False,
        dry_run: bool = False,
        on_cycle: Callable[[ApplyResult], None] | None = None,
    ) -> ApplyResult:
        """Run rules repeatedly for fire-and-forget workflows."""
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        last_result = ApplyResult()
        while True:
            last_result = self.apply(
                rule_set,
                target_dir,
                recursive=recursive,
                max_files=max_files,
                dry_run=dry_run,
            )
            if on_cycle is not None:
                on_cycle(last_result)
            if once:
                return last_result
            time.sleep(interval_seconds)

    def _execute_match(
        self,
        rule: Rule,
        source: Path,
        destination: str,
        base_dir: Path,
        undo_manager: UndoManager,
        transaction_id: str,
    ) -> ExecutionResult:
        action_type = rule.action.action_type
        try:
            if action_type in {
                ActionType.MOVE,
                ActionType.RENAME,
                ActionType.ARCHIVE,
                ActionType.CATEGORIZE,
            }:
                return self._execute_move_like(
                    rule,
                    source,
                    destination,
                    base_dir,
                    undo_manager,
                    transaction_id,
                )
            if action_type == ActionType.COPY:
                return self._execute_copy_like(
                    rule,
                    source,
                    destination,
                    base_dir,
                    OperationType.COPY,
                    copy_file,
                    undo_manager,
                    transaction_id,
                )
            if action_type == ActionType.HARDLINK:
                return self._execute_copy_like(
                    rule,
                    source,
                    destination,
                    base_dir,
                    OperationType.HARDLINK,
                    apply_hardlink,
                    undo_manager,
                    transaction_id,
                )
            if action_type == ActionType.SYMLINK:
                return self._execute_copy_like(
                    rule,
                    source,
                    destination,
                    base_dir,
                    OperationType.SYMLINK,
                    apply_symlink,
                    undo_manager,
                    transaction_id,
                )
            if action_type == ActionType.DELETE:
                return self._execute_delete(rule, source, undo_manager, transaction_id)
            if action_type == ActionType.TAG:
                return ExecutionResult(
                    file_path=str(source),
                    rule_name=rule.name,
                    action_type=action_type.value,
                    status="skipped",
                    message="tag action has no storage backend yet",
                )
            return ExecutionResult(
                file_path=str(source),
                rule_name=rule.name,
                action_type=action_type.value,
                status="failed",
                message="unsupported action",
            )
        except PostMutationError:
            raise
        except Exception as exc:
            logger.warning("Rule '{}' failed for {}: {}", rule.name, source, exc)
            return ExecutionResult(
                file_path=str(source),
                rule_name=rule.name,
                action_type=action_type.value,
                destination=destination,
                status="failed",
                message=str(exc),
            )

    def _execute_move_like(
        self,
        rule: Rule,
        source: Path,
        destination: str,
        base_dir: Path,
        undo_manager: UndoManager,
        transaction_id: str,
    ) -> ExecutionResult:
        target = self._target_path(source, destination, rule.action.action_type, base_dir)
        strategy = self._conflict_strategy(rule)
        resolved = resolve_conflict(target, strategy)
        if resolved is None:
            return self._skipped(rule, source, target, "exists")
        durable_move(source, resolved, journal=default_journal_path())
        try:
            undo_manager.history.log_operation(
                OperationType.RENAME
                if rule.action.action_type == ActionType.RENAME
                else OperationType.MOVE,
                source_path=source,
                destination_path=resolved,
                transaction_id=transaction_id,
            )
        except Exception as log_exc:
            try:
                durable_move(resolved, source, journal=default_journal_path())
            except Exception as rollback_exc:
                logger.error("Failed to rollback filesystem mutation: {}", rollback_exc)
            raise PostMutationError(str(log_exc)) from log_exc
        return self._applied(rule, source, resolved)

    def _execute_copy_like(
        self,
        rule: Rule,
        source: Path,
        destination: str,
        base_dir: Path,
        operation_type: OperationType,
        fn: Callable[[Path, Path, ConflictStrategy], LinkResult],
        undo_manager: UndoManager,
        transaction_id: str,
    ) -> ExecutionResult:
        target = self._target_path(source, destination, rule.action.action_type, base_dir)
        link_result = fn(source, target, self._conflict_strategy(rule))
        if link_result.skipped:
            return self._skipped(rule, source, link_result.destination, link_result.reason)
        try:
            undo_manager.history.log_operation(
                operation_type,
                source_path=source,
                destination_path=link_result.destination,
                transaction_id=transaction_id,
            )
        except Exception as log_exc:
            try:
                if link_result.destination.exists() or link_result.destination.is_symlink():
                    link_result.destination.unlink()
            except Exception as rollback_exc:
                logger.error("Failed to rollback filesystem mutation: {}", rollback_exc)
            raise PostMutationError(str(log_exc)) from log_exc
        return self._applied(rule, source, link_result.destination)

    def _execute_delete(
        self,
        rule: Rule,
        source: Path,
        undo_manager: UndoManager,
        transaction_id: str,
    ) -> ExecutionResult:
        trash_path = (
            undo_manager.executor.trash_dir / transaction_id / f"{uuid.uuid4().hex}-{source.name}"
        )
        durable_move(source, trash_path, journal=default_journal_path())
        try:
            op_id = undo_manager.history.log_operation(
                OperationType.DELETE,
                source_path=source,
                destination_path=trash_path,
                transaction_id=transaction_id,
            )
        except Exception as log_exc:
            try:
                durable_move(trash_path, source, journal=default_journal_path())
            except Exception as rollback_exc:
                logger.error("Failed to rollback filesystem mutation: {}", rollback_exc)
            raise PostMutationError(str(log_exc)) from log_exc
        logger.debug("Logged delete operation {} after moving {} to trash", op_id, source)
        return self._applied(rule, source, trash_path)

    @staticmethod
    def _conflict_strategy(rule: Rule) -> ConflictStrategy:
        raw = rule.action.parameters.get("conflict", ConflictStrategy.SKIP.value)
        return ConflictStrategy(raw)

    @staticmethod
    def _target_path(
        source: Path,
        destination: str,
        action_type: ActionType,
        base_dir: Path,
    ) -> Path:
        if not destination:
            return source.parent / source.name
        raw = Path(destination).expanduser()
        if raw.is_absolute():
            raise ValueError(f"Absolute path not allowed for destination: {destination}")
        if action_type == ActionType.RENAME:
            candidate = source.parent / raw
        else:
            candidate = base_dir / raw

        # Path traversal guard: verify candidate remains inside base_dir
        try:
            resolved_base = base_dir.resolve()
            resolved_candidate = candidate.resolve(strict=False)
            resolved_candidate.relative_to(resolved_base)
        except ValueError as exc:
            raise ValueError(
                f"Path traversal detected: {destination} escapes base directory {base_dir}"
            ) from exc

        if candidate.exists() and candidate.is_dir():
            return candidate / source.name
        if candidate.suffix:
            return candidate
        return candidate / source.name

    @classmethod
    def _inside_destination_root(
        cls,
        source: Path,
        destination: str,
        action_type: ActionType,
        base_dir: Path,
    ) -> bool:
        if action_type in {ActionType.RENAME, ActionType.DELETE, ActionType.TAG}:
            return False
        target = cls._target_path(source, destination, action_type, base_dir)
        if not cls._destination_is_directory_like(destination, action_type, target):
            return source.resolve() == target.resolve()
        root = target.parent
        try:
            source.resolve().relative_to(root.resolve())
        except ValueError:
            return False
        return True

    @staticmethod
    def _destination_is_directory_like(
        destination: str,
        action_type: ActionType,
        target: Path,
    ) -> bool:
        if not destination:
            return False
        raw = Path(destination).expanduser()
        if action_type == ActionType.RENAME:
            return False
        if target.exists():
            return target.is_dir()
        return not raw.suffix

    @staticmethod
    def _applied(rule: Rule, source: Path, destination: Path) -> ExecutionResult:
        return ExecutionResult(
            file_path=str(source),
            rule_name=rule.name,
            action_type=rule.action.action_type.value,
            destination=str(destination),
            status="applied",
        )

    @staticmethod
    def _skipped(rule: Rule, source: Path, destination: Path, reason: str) -> ExecutionResult:
        return ExecutionResult(
            file_path=str(source),
            rule_name=rule.name,
            action_type=rule.action.action_type.value,
            destination=str(destination),
            status="skipped",
            message=reason,
        )
