"""Normalization helpers for cross-surface conformance comparisons (#1605).

These helpers reduce scans, plans, results, errors, audit events, and job
events to transport-neutral dictionaries so the same golden expectations apply
to every driver.  Only presentation-only or environment-dependent details are
removed (identifiers, timestamps, prose descriptions, absolute path prefixes);
everything behavior-affecting is preserved.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from file_organizer.core.organization_service import OrganizationScan
from file_organizer.core.plan import (
    OrganizationOperation,
    OrganizationPlan,
    PlanValidationError,
)
from file_organizer.core.types import OrganizationResult
from file_organizer.history.models import Operation

#: Placeholder prefixes substituted for the request roots in normalized paths.
INPUT_ROOT_TOKEN = "<input>"
OUTPUT_ROOT_TOKEN = "<output>"
EXTERNAL_TOKEN = "<external>"

#: Job-event keys treated as volatile until #1604 finalizes job semantics.
VOLATILE_JOB_KEYS = frozenset({"job_id", "timestamp", "created_at", "updated_at", "duration"})


def normalize_path(path: str | Path, input_root: Path, output_root: Path) -> str:
    """Map an absolute path onto a root-relative, POSIX-style token path."""
    candidate = Path(path)
    resolved = candidate.resolve(strict=False)
    roots = (
        (input_root.resolve(strict=False), INPUT_ROOT_TOKEN),
        (output_root.resolve(strict=False), OUTPUT_ROOT_TOKEN),
    )
    # A number of surfaces default to an output directory below the input
    # root (for example ``./organized_output``). Match the most-specific root
    # first so destinations are not mislabeled as input files.
    for resolved_root, token in sorted(roots, key=lambda item: len(item[0].parts), reverse=True):
        for probe in (candidate, resolved):
            try:
                relative = probe.relative_to(resolved_root)
            except ValueError:
                continue
            if not relative.parts:
                return token
            return f"{token}/{relative.as_posix()}"
    return f"{EXTERNAL_TOKEN}/{candidate.name}"


def redact_roots(text: str, input_root: Path, output_root: Path) -> str:
    """Replace absolute root prefixes embedded in *text* with stable tokens."""
    replacements = [
        (str(input_root.resolve(strict=False)), INPUT_ROOT_TOKEN),
        (str(output_root.resolve(strict=False)), OUTPUT_ROOT_TOKEN),
        (str(input_root), INPUT_ROOT_TOKEN),
        (str(output_root), OUTPUT_ROOT_TOKEN),
    ]
    # Longest prefix first so nested roots cannot partially rewrite each other.
    for raw, token in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        text = text.replace(raw, token)
    return text


def normalize_scan(scan: OrganizationScan, input_root: Path, output_root: Path) -> dict[str, Any]:
    """Normalize a canonical scan into comparable primitives."""
    return {
        "total_files": scan.total_files,
        "files": [normalize_path(path, input_root, output_root) for path in scan.files],
        "counts": dict(sorted(scan.counts.items())),
    }


def _normalize_operation(
    operation: OrganizationOperation, input_root: Path, output_root: Path
) -> dict[str, Any]:
    fingerprint = None
    if operation.fingerprint is not None:
        # All three fields participate in reviewed-plan validation. The
        # corpus pins mtime_ns specifically so it is safe to compare across
        # drivers and must not be normalized away.
        fingerprint = {
            "size": operation.fingerprint.size,
            "mtime_ns": operation.fingerprint.mtime_ns,
            "sha256": operation.fingerprint.sha256,
        }
    error = operation.error
    if error is not None:
        error = redact_roots(error, input_root, output_root)
    return {
        "source": normalize_path(operation.source_path, input_root, output_root),
        "destination": normalize_path(operation.destination_path, input_root, output_root),
        "operation_type": operation.operation_type.value,
        "collision_action": operation.collision_action.value,
        "status": operation.status.value,
        "folder": operation.folder_name,
        "file_name": operation.file_name,
        "fingerprint": fingerprint,
        "error": error,
    }


def normalize_plan(plan: OrganizationPlan, input_root: Path, output_root: Path) -> dict[str, Any]:
    """Normalize an executable plan, dropping identifiers and timestamps.

    ``plan_id``, ``created_at``, per-operation ids, and prose descriptions are
    presentation/bookkeeping; everything needed to reproduce execution stays.
    """
    # Operation order is executable plan behavior: it controls collision
    # allocation and the order in which mutations are attempted. Preserve it
    # so normalization cannot hide adapter reordering.
    operations = [
        _normalize_operation(operation, input_root, output_root) for operation in plan.operations
    ]
    return {
        "schema_version": plan.schema_version,
        "input_path": normalize_path(plan.input_path, input_root, output_root),
        "output_path": normalize_path(plan.output_path, input_root, output_root),
        "skip_existing": plan.skip_existing,
        "use_hardlinks": plan.use_hardlinks,
        "counts": {
            "total_files": plan.total_files,
            "processed_files": plan.processed_files,
            "skipped_files": plan.skipped_files,
            "failed_files": plan.failed_files,
            "deduplicated_files": plan.deduplicated_files,
        },
        "options": plan.options.to_dict(),
        "operations": operations,
        "errors": normalize_error_pairs(plan.errors, input_root, output_root),
        "metadata": dict(plan.metadata),
    }


def normalize_error_pairs(
    errors: Iterable[tuple[str, str]], input_root: Path, output_root: Path
) -> list[dict[str, str]]:
    """Normalize ``(path, message)`` error tuples shared by plans and results."""
    normalized = [
        {
            "path": normalize_path(path, input_root, output_root),
            "message": redact_roots(message, input_root, output_root),
        }
        for path, message in errors
    ]
    return sorted(normalized, key=lambda item: (item["path"], item["message"]))


def normalize_result(
    result: OrganizationResult, input_root: Path, output_root: Path
) -> dict[str, Any]:
    """Normalize an execution/preview result; the plan is normalized separately.

    ``processing_time`` is wall-clock noise and is dropped.
    """
    return {
        "counts": {
            "total_files": result.total_files,
            "processed_files": result.processed_files,
            "skipped_files": result.skipped_files,
            "failed_files": result.failed_files,
            "deduplicated_files": result.deduplicated_files,
        },
        "organized_structure": {
            folder: sorted(files) for folder, files in sorted(result.organized_structure.items())
        },
        "errors": normalize_error_pairs(result.errors, input_root, output_root),
    }


def normalize_error(exc: BaseException, input_root: Path, output_root: Path) -> dict[str, Any]:
    """Normalize a raised error into a surface-neutral envelope payload."""
    normalized: dict[str, Any] = {
        "error_type": type(exc).__name__,
        "message": redact_roots(str(exc), input_root, output_root),
    }
    if isinstance(exc, PlanValidationError):
        normalized["conflicts"] = sorted(
            (
                {
                    "conflict_type": conflict.conflict_type.value,
                    "path": normalize_path(conflict.path, input_root, output_root),
                }
                for conflict in exc.validation.conflicts
            ),
            key=lambda item: (item["conflict_type"], item["path"]),
        )
    return normalized


def normalize_audit_events(
    operations: Iterable[Operation], input_root: Path, output_root: Path
) -> list[dict[str, Any]]:
    """Normalize history operations recorded by an execution.

    Identifiers, timestamps, and file hashes stay out; the observable audit
    contract is which sources landed where, through which operation type, in a
    committed transaction.  #1604 owns extending this with job and recovery
    lifecycle events.
    """
    # History order is observable recovery behavior. Preserve the store's
    # order rather than sorting it into a presentation-friendly shape.
    return [
        {
            "operation_type": operation.operation_type.value,
            "status": operation.status.value,
            "source": normalize_path(operation.source_path, input_root, output_root),
            "destination": (
                normalize_path(operation.destination_path, input_root, output_root)
                if operation.destination_path is not None
                else None
            ),
            "collision_action": operation.metadata.get("collision_action"),
            "folder": operation.metadata.get("folder_name"),
        }
        for operation in operations
    ]


def normalize_job_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize job lifecycle events (provisional until #1604 lands).

    Drops volatile identifiers/timestamps and preserves ordering, which is the
    part of the lifecycle contract already observable today.  #1604 replaces
    this with the canonical job/recovery event schema; keeping the seam here
    lets adapter drivers adopt it without changing the oracle.
    """
    return [
        {key: value for key, value in sorted(event.items()) if key not in VOLATILE_JOB_KEYS}
        for event in events
    ]
