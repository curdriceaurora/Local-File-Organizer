# pyre-ignore-all-errors
"""Executable organization plans.

The plan is the contract between preview and apply: previews render from
these concrete operations, and confirmation executes the same operations
after validating that the filesystem still matches the reviewed state.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any
from uuid import uuid4

from loguru import logger

from file_organizer._compat import StrEnum
from file_organizer.core.organize_options import OrganizeOptions, TransferMode
from file_organizer.history.models import OperationType
from file_organizer.services import ProcessedFile, ProcessedImage
from file_organizer.undo import UndoManager
from file_organizer.utils.safedir import SafeDir, SymlinkRejected

PLAN_SCHEMA_VERSION = 3
_LEGACY_PLAN_SCHEMA_VERSIONS = frozenset({1, 2})
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
    HARDLINK_CROSS_DEVICE = "hardlink_cross_device"
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
    options: OrganizeOptions = field(default_factory=OrganizeOptions)
    operations: list[OrganizationOperation] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def input_root(self) -> Path:
        """Validated input root as a ``Path`` object."""
        return Path(self.input_path)

    @property
    def output_root(self) -> Path:
        """Validated output root as a ``Path`` object."""
        return Path(self.output_path)

    def roots_match(self, input_path: str | Path, output_path: str | Path) -> bool:
        """Return whether the plan roots match already-validated request roots."""
        return self.input_root.resolve(strict=False) == Path(input_path).resolve(
            strict=False
        ) and self.output_root.resolve(strict=False) == Path(output_path).resolve(strict=False)

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
        data["options"] = self.options.to_dict()
        data["use_hardlinks"] = self.options.effective_transfer_mode == TransferMode.HARDLINK
        for operation in data["operations"]:
            operation["operation_type"] = str(operation["operation_type"])
            operation["collision_action"] = str(operation["collision_action"])
            operation["status"] = str(operation["status"])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationPlan:
        """Deserialize a plan previously returned by :meth:`to_dict`."""
        schema_version = int(data.get("schema_version", PLAN_SCHEMA_VERSION))
        if schema_version not in {*_LEGACY_PLAN_SCHEMA_VERSIONS, PLAN_SCHEMA_VERSION}:
            raise ValueError(
                f"Unsupported organization plan schema_version {schema_version}; "
                f"expected 1, 2, or {PLAN_SCHEMA_VERSION}."
            )

        metadata = dict(data.get("metadata", {}))
        if schema_version == 1:
            options = OrganizeOptions(
                skip_existing=bool(data.get("skip_existing", True)),
                use_hardlinks=bool(data.get("use_hardlinks", True)),
                enable_vision=bool(metadata.get("enable_vision", True)),
                prefetch_depth=int(metadata.get("prefetch_depth", 2)),
            )
        else:
            raw_options = data.get("options")
            if not isinstance(raw_options, dict):
                raise ValueError(
                    f"Organization plan schema {schema_version} requires an options object."
                )
            if schema_version == PLAN_SCHEMA_VERSION and "transfer_mode" not in raw_options:
                raise ValueError("Organization plan schema 3 requires transfer_mode.")
            options = OrganizeOptions.from_dict(raw_options)
            if options.skip_existing != bool(data.get("skip_existing", True)):
                raise ValueError("Organization plan skip_existing does not match its options.")
            if options.use_hardlinks != bool(data.get("use_hardlinks", options.use_hardlinks)):
                raise ValueError("Organization plan use_hardlinks does not match its options.")

        operations: list[OrganizationOperation] = []
        for raw in data.get("operations", []):
            status = OrganizationOperationStatus(raw["status"])
            fingerprint_data = raw.get("fingerprint")
            if status == OrganizationOperationStatus.READY and not isinstance(
                fingerprint_data, dict
            ):
                raise ValueError("Ready organization operations require a source fingerprint.")
            try:
                fingerprint = (
                    SourceFingerprint(**fingerprint_data)
                    if isinstance(fingerprint_data, dict)
                    else None
                )
                if fingerprint is not None and (
                    not isinstance(fingerprint.size, int)
                    or not isinstance(fingerprint.mtime_ns, int)
                    or (fingerprint.sha256 is not None and not isinstance(fingerprint.sha256, str))
                ):
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid source fingerprint in organization plan.") from exc
            operations.append(
                OrganizationOperation(
                    operation_id=raw["operation_id"],
                    source_path=raw["source_path"],
                    destination_path=raw["destination_path"],
                    operation_type=OrganizationOperationType(raw["operation_type"]),
                    collision_action=CollisionAction(raw["collision_action"]),
                    status=status,
                    folder_name=raw["folder_name"],
                    file_name=raw["file_name"],
                    description=raw.get("description", ""),
                    fingerprint=fingerprint,
                    error=raw.get("error"),
                )
            )

        expected_operation_type = (
            OrganizationOperationType.HARDLINK
            if options.effective_transfer_mode == TransferMode.HARDLINK
            else OrganizationOperationType.COPY
        )
        if any(operation.operation_type != expected_operation_type for operation in operations):
            raise ValueError("Organization plan operation types do not match transfer_mode.")

        return cls(
            plan_id=data["plan_id"],
            schema_version=PLAN_SCHEMA_VERSION,
            input_path=data["input_path"],
            output_path=data["output_path"],
            created_at=data["created_at"],
            skip_existing=bool(data.get("skip_existing", True)),
            use_hardlinks=options.effective_transfer_mode == TransferMode.HARDLINK,
            total_files=int(data.get("total_files", 0)),
            processed_files=int(data.get("processed_files", 0)),
            skipped_files=int(data.get("skipped_files", 0)),
            failed_files=int(data.get("failed_files", 0)),
            deduplicated_files=int(data.get("deduplicated_files", 0)),
            options=options,
            operations=operations,
            errors=[tuple(error) for error in data.get("errors", [])],
            metadata=metadata,
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
    options: OrganizeOptions | None = None,
) -> OrganizationPlan:
    """Create an executable plan from processed file classifications."""
    operations: list[OrganizationOperation] = []
    reserved_destinations: set[Path] = set()
    output_path = Path(output_path)
    file_hashes = file_hashes or {}

    if options is None:
        options = OrganizeOptions(
            skip_existing=skip_existing,
            use_hardlinks=use_hardlinks,
        )
    else:
        options = replace(options, skip_existing=skip_existing)
        use_hardlinks = options.effective_transfer_mode == TransferMode.HARDLINK

    for result in sorted(processed, key=lambda item: str(item.file_path)):
        source = Path(result.file_path)
        base_name = f"{result.filename}{source.suffix}"
        destination = output_path / result.folder_name / base_name
        collision_action = CollisionAction.CREATE
        status = OrganizationOperationStatus.READY
        error = result.error

        if error:
            status = OrganizationOperationStatus.ERROR
        elif skip_existing and destination.exists():
            status = OrganizationOperationStatus.SKIPPED
            collision_action = CollisionAction.SKIP_EXISTING
        elif destination in reserved_destinations or not skip_existing:
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

        fingerprint = None
        if status != OrganizationOperationStatus.ERROR:
            try:
                fingerprint = SourceFingerprint.capture(source, sha256=file_hashes.get(source))
            except OSError as exc:
                status = OrganizationOperationStatus.ERROR
                error = f"Unable to fingerprint source: {exc}"

        if status == OrganizationOperationStatus.READY:
            reserved_destinations.add(destination)

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

    plan_metadata = dict(metadata or {})
    plan_metadata.setdefault("methodology", options.effective_methodology.value)

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
        options=options,
        operations=operations,
        errors=list(errors or []),
        metadata=plan_metadata,
    )


def validate_plan(plan: OrganizationPlan) -> PlanValidationResult:  # noqa: C901  # copilot: wontfix
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

        if operation.operation_type == OrganizationOperationType.HARDLINK:
            try:
                source_device = source.stat().st_dev
                destination_device = _filesystem_device(destination.parent)
            except OSError as exc:
                conflicts.append(
                    PlanConflict(
                        PlanConflictType.HARDLINK_CROSS_DEVICE,
                        str(destination),
                        f"Unable to verify hardlink filesystem precondition: {exc}",
                        operation_id=operation.operation_id,
                    )
                )
                continue
            if source_device != destination_device:
                conflicts.append(
                    PlanConflict(
                        PlanConflictType.HARDLINK_CROSS_DEVICE,
                        str(destination),
                        "Hardlinks require source and destination on the same filesystem.",
                        operation_id=operation.operation_id,
                        expected=f"device={source_device}",
                        actual=f"device={destination_device}",
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
    completed_destinations: list[Path] = []
    _ensure_output_root(Path(plan.output_path))

    try:
        for operation in plan.ready_operations:
            destination = operation.destination
            try:
                if operation.operation_type == OrganizationOperationType.HARDLINK:
                    _hardlink_operation_anchored(plan, operation)
                    history_type = OperationType.HARDLINK
                else:
                    _copy_operation_anchored(plan, operation)
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
                completed_destinations.append(destination)
                organized.setdefault(operation.folder_name, []).append(operation.file_name)

        try:
            if not manager.history.commit_transaction(transaction_id):
                raise RuntimeError(f"Failed to commit organization transaction {transaction_id}")
        except Exception:
            for destination in reversed(completed_destinations):
                _cleanup_unlogged_destination(destination)
            raise
    except Exception:
        logger.exception(
            "Plan execution failed; leaving transaction {} uncommitted", transaction_id
        )
        raise

    return organized, transaction_id, errors


def _sha256(path: Path) -> str | None:
    hasher = hashlib.sha256()
    if sys.platform != "win32":
        try:
            with SafeDir.open_root(path.parent) as safe_dir:
                fd = safe_dir.open_for_reader(path.name)
                try:
                    fileobj = os.fdopen(fd, "rb", closefd=True)
                except OSError:
                    os.close(fd)
                    raise
                with fileobj:
                    for chunk in iter(lambda: fileobj.read(_CHUNK_SIZE), b""):
                        hasher.update(chunk)
            return hasher.hexdigest()
        except SymlinkRejected as exc:
            logger.warning("Refused to hash symlinked plan source {}: {}", path, exc)
            return None
        except NotImplementedError:
            logger.debug("SafeDir unavailable; hashing {} via legacy reader", path.name)
        except (OSError, ValueError):
            return None

    try:
        with path.open("rb") as fh:  # noqa: safedir-required  # copilot: wontfix  # Windows / NotImplementedError fallback; POSIX uses SafeDir above.
            for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None


def _cleanup_unlogged_destination(destination: Path) -> None:
    """Remove a destination created before undo/history logging failed."""
    try:
        destination.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to clean up unlogged destination {}: {}", destination, exc)


def _ensure_output_root(output_root: Path) -> None:
    """Create the output root before opening it as a SafeDir anchor."""
    if output_root.exists():
        return
    parent = output_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    with SafeDir.open_root(parent) as parent_dir:
        try:
            parent_dir.mkdir(output_root.name)
        except FileExistsError:
            pass


def _relative_to_root(path: Path, root: Path) -> PurePath:
    """Return a plan path relative to its already validated root."""
    return PurePath(path.resolve(strict=False).relative_to(root.resolve(strict=False)))


def _copy_operation_anchored(plan: OrganizationPlan, operation: OrganizationOperation) -> None:
    """Copy a planned file using SafeDir anchored source and destination roots."""
    source_relative = _relative_to_root(operation.source, Path(plan.input_path))
    destination_relative = _relative_to_root(operation.destination, Path(plan.output_path))
    with (
        SafeDir.open_root(plan.input_path) as source_root,
        SafeDir.open_root(plan.output_path) as destination_root,
    ):
        source_fd = source_root.open_anchored_reader(source_relative)
        try:
            _verify_source_fd(source_fd, operation)
        except Exception:
            os.close(source_fd)
            raise
        try:
            destination_fd = destination_root.open_anchored_writer(
                destination_relative,
                flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            )
        except OSError:
            os.close(source_fd)
            raise
        try:
            with (
                os.fdopen(source_fd, "rb", closefd=True) as src,
                os.fdopen(destination_fd, "wb", closefd=True) as dst,
            ):
                for chunk in iter(lambda: src.read(_CHUNK_SIZE), b""):
                    dst.write(chunk)
        except Exception:
            _cleanup_unlogged_destination(operation.destination)
            raise


def _hardlink_operation_anchored(plan: OrganizationPlan, operation: OrganizationOperation) -> None:
    """Create a planned hardlink using SafeDir anchored parent directories."""
    source_relative = _relative_to_root(operation.source, Path(plan.input_path))
    destination_relative = _relative_to_root(operation.destination, Path(plan.output_path))
    with (
        SafeDir.open_root(plan.input_path) as source_root,
        SafeDir.open_root(plan.output_path) as destination_root,
        contextlib.ExitStack() as stack,
    ):
        source_fd = source_root.open_anchored_reader(source_relative)
        try:
            _verify_source_fd(source_fd, operation)
            source_parent, source_name = _open_anchored_parent(
                stack, source_root, source_relative, create=False
            )
            destination_parent, destination_name = _open_anchored_parent(
                stack, destination_root, destination_relative, create=True
            )
            _link_verified_source(
                source_fd, source_parent, source_name, destination_parent, destination_name
            )
        finally:
            os.close(source_fd)


def _verify_source_fd(source_fd: int, operation: OrganizationOperation) -> None:
    """Validate an opened source descriptor against the reviewed fingerprint."""
    fingerprint = operation.fingerprint
    if fingerprint is None:
        raise OSError("Ready operation is missing source fingerprint.")

    stat_result = os.fstat(source_fd)
    if stat_result.st_size != fingerprint.size or stat_result.st_mtime_ns != fingerprint.mtime_ns:
        raise OSError("Source metadata changed after preview.")
    if fingerprint.sha256 is not None and _sha256_fd(source_fd) != fingerprint.sha256:
        raise OSError("Source content hash changed after preview.")
    os.lseek(source_fd, 0, os.SEEK_SET)


def _sha256_fd(source_fd: int) -> str:
    """Return the SHA-256 digest for an already opened source descriptor."""
    hasher = hashlib.sha256()
    os.lseek(source_fd, 0, os.SEEK_SET)
    for chunk in iter(lambda: os.read(source_fd, _CHUNK_SIZE), b""):
        hasher.update(chunk)
    os.lseek(source_fd, 0, os.SEEK_SET)
    return hasher.hexdigest()


def _link_verified_source(
    source_fd: int,
    source_parent: SafeDir,
    source_name: str,
    destination_parent: SafeDir,
    destination_name: str,
) -> None:
    """Create a hardlink to the verified source descriptor when supported."""
    for fd_root in ("/proc/self/fd", "/dev/fd"):
        fd_path = Path(fd_root) / str(source_fd)
        if not fd_path.exists():
            continue
        try:
            os.link(str(fd_path), destination_name, dst_dir_fd=destination_parent.fd)
            return
        except OSError:
            continue

    source_stat = os.fstat(source_fd)
    os.link(
        source_name,
        destination_name,
        src_dir_fd=source_parent.fd,
        dst_dir_fd=destination_parent.fd,
    )
    destination_stat = os.stat(
        destination_name,
        dir_fd=destination_parent.fd,
        follow_symlinks=False,
    )
    if (destination_stat.st_dev, destination_stat.st_ino) != (
        source_stat.st_dev,
        source_stat.st_ino,
    ):
        with contextlib.suppress(OSError):
            destination_parent.unlink(destination_name)
        raise OSError("Linked destination does not match verified source.")


def _open_anchored_parent(
    stack: contextlib.ExitStack,
    root: SafeDir,
    relative_path: PurePath,
    *,
    create: bool,
) -> tuple[SafeDir, str]:
    """Walk to an anchored parent directory and return it with the leaf name."""
    parts = relative_path.parts
    if not parts:
        raise ValueError("Plan operation path must not be empty.")
    current = root
    for component in parts[:-1]:
        if create:
            try:
                current.mkdir(component)
            except FileExistsError:
                pass
        current = stack.enter_context(current.open_subdir(component))
    return current, parts[-1]


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


def _filesystem_device(path: Path) -> int:
    """Return the device for *path* or its nearest existing ancestor."""
    candidate = path
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return candidate.stat().st_dev
