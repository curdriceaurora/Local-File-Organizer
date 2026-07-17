"""Executable organization plans.

The plan is the contract between preview and apply: previews render from
these concrete operations, and confirmation executes the same operations
after validating that the filesystem still matches the reviewed state.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from loguru import logger

from file_organizer._compat import StrEnum
from file_organizer.history.models import OperationType
from file_organizer.services import ProcessedFile, ProcessedImage
from file_organizer.undo import UndoManager
from file_organizer.utils.safe_copy import safe_copy2

PLAN_SCHEMA_VERSION = 1
_CHUNK_SIZE = 65536


class OrganizationOperationType(StrEnum):
    """Concrete filesystem operation kinds supported by organization plans."""

    COPY = "copy"
    HARDLINK = "hardlink"


class OrganizationOperationStatus(StrEnum):
    """Planned operation status."""

    READY = "ready"
    SKIPPED = "skipped"
    ERROR = "error"


class CollisionAction(StrEnum):
    """How destination collisions were resolved at plan time."""

    CREATE = "create"
    SKIP_EXISTING = "skip_existing"
    RENAME_WITH_COUNTER = "rename_with_counter"


class PlanConflictType(StrEnum):
    """Blocking reasons that prevent a reviewed plan from being applied."""

    SOURCE_MISSING = "source_missing"
    SOURCE_NOT_FILE = "source_not_file"
    SOURCE_SYMLINK = "source_symlink"
    SOURCE_CHANGED = "source_changed"
    SOURCE_OUTSIDE_INPUT = "source_outside_input"
    DESTINATION_EXISTS = "destination_exists"
    DESTINATION_OUTSIDE_OUTPUT = "destination_outside_output"
    DESTINATION_PARENT_BLOCKED = "destination_parent_blocked"
    DESTINATION_PARENT_SYMLINK = "destination_parent_symlink"


@dataclass(frozen=True)
class SourceFingerprint:
    """Preview-time source metadata used for stale-plan validation."""

    size: int
    mtime_ns: int
    sha256: str | None = None

    @classmethod
    def capture(cls, path: Path, sha256: str | None = None) -> SourceFingerprint:
        """Capture stable-enough metadata for a planned source file."""
        stat = path.stat()
        return cls(size=stat.st_size, mtime_ns=stat.st_mtime_ns, sha256=sha256)


@dataclass(frozen=True)
class PlanConflict:
    """A single validation conflict for an organization plan."""

    conflict_type: PlanConflictType
    path: str
    description: str
    operation_id: str | None = None
    expected: str | None = None
    actual: str | None = None

    def __str__(self) -> str:
        """Return a compact human-readable conflict description."""
        text = f"{self.conflict_type.value}: {self.path} - {self.description}"
        if self.expected is not None or self.actual is not None:
            text += f" (expected: {self.expected}, actual: {self.actual})"
        return text


@dataclass
class PlanValidationResult:
    """Result of validating a plan against the current filesystem."""

    can_proceed: bool
    conflicts: list[PlanConflict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def error_message(self) -> str:
        """Human-readable summary for the first few blocking conflicts."""
        if self.can_proceed:
            return ""
        details = "; ".join(str(conflict) for conflict in self.conflicts[:3])
        if len(self.conflicts) > 3:
            details += f"; and {len(self.conflicts) - 3} more"
        return details or "Organization plan validation failed."


class PlanValidationError(RuntimeError):
    """Raised when a reviewed organization plan is stale or unsafe to apply."""

    def __init__(self, validation: PlanValidationResult) -> None:
        """Initialize the exception with the failed validation result."""
        super().__init__(validation.error_message)
        self.validation = validation


@dataclass
class OrganizationOperation:
    """One concrete operation in an organization plan."""

    operation_id: str
    source_path: str
    destination_path: str
    operation_type: OrganizationOperationType
    collision_action: CollisionAction
    status: OrganizationOperationStatus
    folder_name: str
    file_name: str
    description: str = ""
    fingerprint: SourceFingerprint | None = None
    error: str | None = None

    @property
    def source(self) -> Path:
        """Source path as a ``Path`` object."""
        return Path(self.source_path)

    @property
    def destination(self) -> Path:
        """Destination path as a ``Path`` object."""
        return Path(self.destination_path)


@dataclass
class OrganizationPlan:
    """Executable plan produced by preview and consumed by apply."""

    plan_id: str
    schema_version: int
    input_path: str
    output_path: str
    created_at: str
    skip_existing: bool
    use_hardlinks: bool
    total_files: int
    processed_files: int
    skipped_files: int
    failed_files: int
    deduplicated_files: int
    operations: list[OrganizationOperation] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ready_operations(self) -> list[OrganizationOperation]:
        """Operations that should be executed."""
        return [
            operation
            for operation in self.operations
            if operation.status == OrganizationOperationStatus.READY
        ]

    def organized_structure(self) -> dict[str, list[str]]:
        """Return the legacy folder-to-filenames display structure."""
        structure: dict[str, list[str]] = {}
        for operation in self.ready_operations:
            structure.setdefault(operation.folder_name, []).append(operation.file_name)
        return structure

    def movements(self) -> list[dict[str, str]]:
        """Return display movement rows with exact source/destination identity."""
        rows: list[dict[str, str]] = []
        for operation in self.operations:
            rows.append(
                {
                    "operation_id": operation.operation_id,
                    "file_name": operation.file_name,
                    "source": operation.source_path,
                    "destination": operation.destination_path,
                    "reason": operation.description or f"Categorized into {operation.folder_name}",
                    "status": operation.status.value,
                }
            )
        return rows

    def to_dict(self) -> dict[str, Any]:
        """Serialize the plan into JSON-compatible primitives."""
        data = asdict(self)
        for operation in data["operations"]:
            operation["operation_type"] = str(operation["operation_type"])
            operation["collision_action"] = str(operation["collision_action"])
            operation["status"] = str(operation["status"])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationPlan:
        """Deserialize a plan previously returned by :meth:`to_dict`."""
        operations: list[OrganizationOperation] = []
        for raw in data.get("operations", []):
            fingerprint_data = raw.get("fingerprint")
            fingerprint = (
                SourceFingerprint(**fingerprint_data)
                if isinstance(fingerprint_data, dict)
                else None
            )
            operations.append(
                OrganizationOperation(
                    operation_id=raw["operation_id"],
                    source_path=raw["source_path"],
                    destination_path=raw["destination_path"],
                    operation_type=OrganizationOperationType(raw["operation_type"]),
                    collision_action=CollisionAction(raw["collision_action"]),
                    status=OrganizationOperationStatus(raw["status"]),
                    folder_name=raw["folder_name"],
                    file_name=raw["file_name"],
                    description=raw.get("description", ""),
                    fingerprint=fingerprint,
                    error=raw.get("error"),
                )
            )

        return cls(
            plan_id=data["plan_id"],
            schema_version=int(data.get("schema_version", PLAN_SCHEMA_VERSION)),
            input_path=data["input_path"],
            output_path=data["output_path"],
            created_at=data["created_at"],
            skip_existing=bool(data.get("skip_existing", True)),
            use_hardlinks=bool(data.get("use_hardlinks", True)),
            total_files=int(data.get("total_files", 0)),
            processed_files=int(data.get("processed_files", 0)),
            skipped_files=int(data.get("skipped_files", 0)),
            failed_files=int(data.get("failed_files", 0)),
            deduplicated_files=int(data.get("deduplicated_files", 0)),
            operations=operations,
            errors=[tuple(error) for error in data.get("errors", [])],
            metadata=dict(data.get("metadata", {})),
        )


def build_plan_from_processed(
    *,
    input_path: Path,
    output_path: Path,
    processed: list[ProcessedFile | ProcessedImage],
    skip_existing: bool,
    use_hardlinks: bool,
    total_files: int,
    skipped_files: int,
    deduplicated_files: int,
    errors: list[tuple[str, str]] | None = None,
    file_hashes: dict[Path, str | None] | None = None,
    metadata: dict[str, Any] | None = None,
) -> OrganizationPlan:
    """Create an executable plan from processed file classifications."""
    operations: list[OrganizationOperation] = []
    reserved_destinations: set[Path] = set()
    output_path = Path(output_path)
    file_hashes = file_hashes or {}

    for result in processed:
        source = Path(result.file_path)
        base_name = f"{result.filename}{source.suffix}"
        destination = output_path / result.folder_name / base_name
        collision_action = CollisionAction.CREATE
        status = OrganizationOperationStatus.READY
        error = result.error

        if error:
            status = OrganizationOperationStatus.ERROR
        elif skip_existing and (destination.exists() or destination in reserved_destinations):
            status = OrganizationOperationStatus.SKIPPED
            collision_action = CollisionAction.SKIP_EXISTING
        elif not skip_existing:
            counter = 1
            planned = destination
            while planned.exists() or planned in reserved_destinations:
                planned = (
                    output_path / result.folder_name / f"{result.filename}_{counter}{source.suffix}"
                )
                counter += 1
            if planned != destination:
                collision_action = CollisionAction.RENAME_WITH_COUNTER
                destination = planned
                base_name = destination.name

        if status == OrganizationOperationStatus.READY:
            reserved_destinations.add(destination)

        fingerprint = None
        if status != OrganizationOperationStatus.ERROR:
            try:
                fingerprint = SourceFingerprint.capture(source, sha256=file_hashes.get(source))
            except OSError as exc:
                status = OrganizationOperationStatus.ERROR
                error = f"Unable to fingerprint source: {exc}"

        operations.append(
            OrganizationOperation(
                operation_id=uuid4().hex,
                source_path=str(source),
                destination_path=str(destination),
                operation_type=(
                    OrganizationOperationType.HARDLINK
                    if use_hardlinks
                    else OrganizationOperationType.COPY
                ),
                collision_action=collision_action,
                status=status,
                folder_name=result.folder_name,
                file_name=base_name,
                description=result.description,
                fingerprint=fingerprint,
                error=error,
            )
        )

    ready_count = sum(1 for op in operations if op.status == OrganizationOperationStatus.READY)
    error_count = sum(1 for op in operations if op.status == OrganizationOperationStatus.ERROR)
    skipped_count = skipped_files + sum(
        1 for op in operations if op.status == OrganizationOperationStatus.SKIPPED
    )

    return OrganizationPlan(
        plan_id=uuid4().hex,
        schema_version=PLAN_SCHEMA_VERSION,
        input_path=str(input_path),
        output_path=str(output_path),
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        skip_existing=skip_existing,
        use_hardlinks=use_hardlinks,
        total_files=total_files,
        processed_files=ready_count,
        skipped_files=skipped_count,
        failed_files=error_count,
        deduplicated_files=deduplicated_files,
        operations=operations,
        errors=list(errors or []),
        metadata=dict(metadata or {}),
    )


def validate_plan(plan: OrganizationPlan) -> PlanValidationResult:  # noqa: C901
    """Validate a reviewed plan before mutating the filesystem."""
    conflicts: list[PlanConflict] = []
    input_root = Path(plan.input_path)
    resolved_input_root = input_root.resolve(strict=False)
    output_root = Path(plan.output_path)
    resolved_output_root = output_root.resolve(strict=False)
    if output_root.exists() and not output_root.is_dir():
        conflicts.append(
            PlanConflict(
                PlanConflictType.DESTINATION_PARENT_BLOCKED,
                str(output_root),
                "Output root exists but is not a directory.",
            )
        )

    for operation in plan.ready_operations:
        source = operation.source
        destination = operation.destination
        resolved_source = source.resolve(strict=False)
        try:
            resolved_source.relative_to(resolved_input_root)
        except ValueError:
            conflicts.append(
                PlanConflict(
                    PlanConflictType.SOURCE_OUTSIDE_INPUT,
                    str(source),
                    "Planned source is outside the plan input root.",
                    operation_id=operation.operation_id,
                    expected=str(resolved_input_root),
                    actual=str(resolved_source),
                )
            )
            continue

        resolved_destination = destination.resolve(strict=False)
        try:
            resolved_destination.relative_to(resolved_output_root)
        except ValueError:
            conflicts.append(
                PlanConflict(
                    PlanConflictType.DESTINATION_OUTSIDE_OUTPUT,
                    str(destination),
                    "Planned destination is outside the plan output root.",
                    operation_id=operation.operation_id,
                    expected=str(resolved_output_root),
                    actual=str(resolved_destination),
                )
            )
            continue

        if not source.exists():
            conflicts.append(
                PlanConflict(
                    PlanConflictType.SOURCE_MISSING,
                    str(source),
                    "Source file no longer exists.",
                    operation_id=operation.operation_id,
                )
            )
            continue
        if source.is_symlink():
            conflicts.append(
                PlanConflict(
                    PlanConflictType.SOURCE_SYMLINK,
                    str(source),
                    "Source path is now a symlink.",
                    operation_id=operation.operation_id,
                )
            )
            continue
        if not source.is_file():
            conflicts.append(
                PlanConflict(
                    PlanConflictType.SOURCE_NOT_FILE,
                    str(source),
                    "Source path is no longer a regular file.",
                    operation_id=operation.operation_id,
                )
            )
            continue

        fingerprint = operation.fingerprint
        if fingerprint is not None:
            try:
                stat = source.stat()
            except OSError as exc:
                conflicts.append(
                    PlanConflict(
                        PlanConflictType.SOURCE_CHANGED,
                        str(source),
                        f"Source stat failed: {exc}",
                        operation_id=operation.operation_id,
                    )
                )
            else:
                if stat.st_size != fingerprint.size or stat.st_mtime_ns != fingerprint.mtime_ns:
                    conflicts.append(
                        PlanConflict(
                            PlanConflictType.SOURCE_CHANGED,
                            str(source),
                            "Source metadata changed after preview.",
                            operation_id=operation.operation_id,
                            expected=f"size={fingerprint.size},mtime_ns={fingerprint.mtime_ns}",
                            actual=f"size={stat.st_size},mtime_ns={stat.st_mtime_ns}",
                        )
                    )
                elif fingerprint.sha256 is not None:
                    actual_sha256 = _sha256(source)
                    if actual_sha256 != fingerprint.sha256:
                        conflicts.append(
                            PlanConflict(
                                PlanConflictType.SOURCE_CHANGED,
                                str(source),
                                "Source content hash changed after preview.",
                                operation_id=operation.operation_id,
                                expected=fingerprint.sha256,
                                actual=actual_sha256,
                            )
                        )

        if destination.exists():
            conflicts.append(
                PlanConflict(
                    PlanConflictType.DESTINATION_EXISTS,
                    str(destination),
                    "Planned destination already exists.",
                    operation_id=operation.operation_id,
                )
            )
            continue

        parent = destination.parent
        for candidate in _parents_from_root(output_root, parent):
            if candidate.exists() and candidate.is_symlink():
                conflicts.append(
                    PlanConflict(
                        PlanConflictType.DESTINATION_PARENT_SYMLINK,
                        str(candidate),
                        "Destination parent is a symlink.",
                        operation_id=operation.operation_id,
                    )
                )
                break
            if candidate.exists() and not candidate.is_dir():
                conflicts.append(
                    PlanConflict(
                        PlanConflictType.DESTINATION_PARENT_BLOCKED,
                        str(candidate),
                        "Destination parent is blocked by a non-directory.",
                        operation_id=operation.operation_id,
                    )
                )
                break

    return PlanValidationResult(can_proceed=not conflicts, conflicts=conflicts)


def execute_plan(
    plan: OrganizationPlan,
    *,
    undo_manager: UndoManager | None = None,
) -> tuple[dict[str, list[str]], str | None, list[tuple[str, str]]]:
    """Validate and execute ready operations from *plan*.

    Returns:
        ``(organized_structure, transaction_id, errors)``.
    """
    validation = validate_plan(plan)
    if not validation.can_proceed:
        raise PlanValidationError(validation)

    manager = undo_manager or UndoManager()
    transaction_id = manager.history.start_transaction(
        metadata={
            "plan_id": plan.plan_id,
            "plan_schema_version": plan.schema_version,
            "input_path": plan.input_path,
            "output_path": plan.output_path,
            "operation_count": len(plan.ready_operations),
        }
    )

    organized: dict[str, list[str]] = {}
    errors: list[tuple[str, str]] = []
    output_root = Path(plan.output_path)
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        for operation in plan.ready_operations:
            destination = operation.destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                if operation.operation_type == OrganizationOperationType.HARDLINK:
                    os.link(operation.source, destination)
                    history_type = OperationType.HARDLINK
                else:
                    safe_copy2(operation.source, destination, output_root)
                    history_type = OperationType.COPY
            except OSError as exc:
                logger.opt(exception=exc).error("Failed to execute plan operation {}", operation)
                errors.append((operation.source_path, str(exc)))
                continue

            try:
                manager.history.log_operation(
                    history_type,
                    source_path=operation.source,
                    destination_path=destination,
                    transaction_id=transaction_id,
                    metadata={
                        "plan_id": plan.plan_id,
                        "operation_id": operation.operation_id,
                        "collision_action": operation.collision_action.value,
                        "folder_name": operation.folder_name,
                    },
                )
            except OSError as exc:
                _cleanup_unlogged_destination(destination)
                errors.append((operation.source_path, str(exc)))
            except (ValueError, RuntimeError, sqlite3.Error) as exc:
                logger.warning("Undo log failed for {}: {}", operation.source_path, exc)
                _cleanup_unlogged_destination(destination)
                errors.append((operation.source_path, str(exc)))
            else:
                organized.setdefault(operation.folder_name, []).append(operation.file_name)

        manager.history.commit_transaction(transaction_id)
    except Exception:
        logger.exception(
            "Plan execution failed; leaving transaction {} uncommitted", transaction_id
        )
        raise

    return organized, transaction_id, errors


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _cleanup_unlogged_destination(destination: Path) -> None:
    """Remove a destination created before undo/history logging failed."""
    try:
        destination.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to clean up unlogged destination {}: {}", destination, exc)


def _parents_from_root(root: Path, leaf_parent: Path) -> list[Path]:
    """Return candidate parents between the output root and destination parent."""
    try:
        relative = leaf_parent.relative_to(root)
    except ValueError:
        return [leaf_parent]

    candidates = [root]
    current = root
    for part in relative.parts:
        current = current / part
        candidates.append(current)
    return candidates
