"""Tests for executable organization plans."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.core.plan import (
    CollisionAction,
    OrganizationOperationStatus,
    OrganizationPlan,
    PlanValidationError,
    SourceFingerprint,
    build_plan_from_processed,
    execute_plan,
    validate_plan,
)
from file_organizer.history.tracker import OperationHistory
from file_organizer.services.text_processor import ProcessedFile
from file_organizer.undo import UndoManager

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _processed(path: Path, folder: str = "Docs", name: str | None = None) -> ProcessedFile:
    return ProcessedFile(
        file_path=path,
        description=f"Categorized into {folder}",
        folder_name=folder,
        filename=name or path.stem,
    )


def test_plan_generation_records_exact_ready_operation(tmp_path: Path) -> None:
    source = tmp_path / "input" / "report.txt"
    source.parent.mkdir()
    source.write_text("hello")
    output = tmp_path / "out"

    plan = build_plan_from_processed(
        input_path=source.parent,
        output_path=output,
        processed=[_processed(source)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
        file_hashes={source: "abc"},
    )

    assert plan.processed_files == 1
    assert plan.organized_structure() == {"Docs": ["report.txt"]}
    operation = plan.operations[0]
    assert operation.source_path == str(source)
    assert operation.destination_path == str(output / "Docs" / "report.txt")
    assert operation.status == OrganizationOperationStatus.READY
    assert operation.fingerprint is not None
    assert operation.fingerprint.sha256 == "abc"


def test_plan_roots_display_rows_and_serialization_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "input" / "report.txt"
    source.parent.mkdir()
    source.write_text("hello")
    output = tmp_path / "out"

    plan = build_plan_from_processed(
        input_path=source.parent,
        output_path=output,
        processed=[_processed(source)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
        metadata={"methodology": "none"},
    )

    assert plan.input_root == source.parent
    assert plan.output_root == output
    assert plan.roots_match(source.parent / ".", output / ".")
    assert not plan.roots_match(tmp_path / "other-input", output)
    assert plan.movements() == [
        {
            "operation_id": plan.operations[0].operation_id,
            "file_name": "report.txt",
            "source": str(source),
            "destination": str(output / "Docs" / "report.txt"),
            "reason": "Categorized into Docs",
            "status": "ready",
        }
    ]

    restored = OrganizationPlan.from_dict(plan.to_dict())

    assert restored == plan
    assert restored.operations[0].operation_type == plan.operations[0].operation_type
    assert restored.operations[0].fingerprint == plan.operations[0].fingerprint
    assert restored.metadata == {"methodology": "none"}


def test_validate_plan_rejects_source_hash_change_when_metadata_is_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello")
    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=tmp_path / "out",
        processed=[_processed(source)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
        file_hashes={source: "expected-hash"},
    )

    stat = source.stat()
    plan.operations[0].fingerprint = SourceFingerprint(
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256="expected-hash",
    )
    monkeypatch.setattr("file_organizer.core.plan._sha256", lambda path: "actual-hash")

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "Source content hash changed after preview." in validation.error_message
    assert "expected-hash" in validation.error_message
    assert "actual-hash" in validation.error_message


def test_plan_collision_skip_existing_is_decided_at_plan_time(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello")
    existing = tmp_path / "out" / "Docs" / "input.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing")

    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=tmp_path / "out",
        processed=[_processed(source)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )

    operation = plan.operations[0]
    assert operation.status == OrganizationOperationStatus.SKIPPED
    assert operation.collision_action == CollisionAction.SKIP_EXISTING
    assert plan.organized_structure() == {}


def test_plan_collision_rename_is_decided_at_plan_time(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello")
    existing = tmp_path / "out" / "Docs" / "input.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing")

    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=tmp_path / "out",
        processed=[_processed(source)],
        skip_existing=False,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )

    operation = plan.operations[0]
    assert operation.status == OrganizationOperationStatus.READY
    assert operation.collision_action == CollisionAction.RENAME_WITH_COUNTER
    assert operation.destination_path == str(tmp_path / "out" / "Docs" / "input_1.txt")
    assert plan.organized_structure() == {"Docs": ["input_1.txt"]}


def test_plan_same_run_collision_renames_even_when_skip_existing(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one")
    second.write_text("two")

    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=tmp_path / "out",
        processed=[_processed(first, name="shared"), _processed(second, name="shared")],
        skip_existing=True,
        use_hardlinks=False,
        total_files=2,
        skipped_files=0,
        deduplicated_files=0,
    )

    assert [operation.status for operation in plan.operations] == [
        OrganizationOperationStatus.READY,
        OrganizationOperationStatus.READY,
    ]
    assert [operation.file_name for operation in plan.operations] == [
        "shared.txt",
        "shared_1.txt",
    ]
    assert plan.processed_files == 2
    assert plan.skipped_files == 0


def test_execute_plan_rejects_modified_source_before_mutation(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello")
    output = tmp_path / "out"
    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=output,
        processed=[_processed(source)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )
    source.write_text("changed")

    with pytest.raises(PlanValidationError) as exc_info:
        execute_plan(plan, undo_manager=UndoManager(history=OperationHistory(tmp_path / "h.db")))

    assert "source_changed" in str(exc_info.value)
    assert not (output / "Docs" / "input.txt").exists()


def test_validate_plan_rejects_destination_outside_output(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello")
    output = tmp_path / "out"
    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=output,
        processed=[_processed(source)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )
    plan.operations[0].destination_path = str(tmp_path / "elsewhere" / "input.txt")

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "destination_outside_output" in validation.error_message


def test_validate_plan_rejects_source_outside_input(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("hello")
    plan = build_plan_from_processed(
        input_path=input_dir,
        output_path=tmp_path / "out",
        processed=[_processed(outside)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "source_outside_input" in validation.error_message


def test_execute_plan_applies_exact_destination_and_logs_history(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello")
    output = tmp_path / "out"
    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=output,
        processed=[_processed(source)],
        skip_existing=False,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))

    organized, transaction_id, errors = execute_plan(plan, undo_manager=manager)

    destination = output / "Docs" / "input.txt"
    assert errors == []
    assert organized == {"Docs": ["input.txt"]}
    assert destination.read_text() == "hello"
    operations = manager.history.get_operations(transaction_id=transaction_id)
    assert len(operations) == 1
    assert operations[0].destination_path == destination
    assert operations[0].metadata["plan_id"] == plan.plan_id


def test_execute_plan_cleans_up_destination_when_history_logging_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello")
    output = tmp_path / "out"
    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=output,
        processed=[_processed(source)],
        skip_existing=False,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))

    def fail_log(*_: object, **__: object) -> None:
        raise RuntimeError("history unavailable")

    monkeypatch.setattr(manager.history, "log_operation", fail_log)

    organized, _, errors = execute_plan(plan, undo_manager=manager)

    assert organized == {}
    assert errors == [(str(source), "history unavailable")]
    assert not (output / "Docs" / "input.txt").exists()
