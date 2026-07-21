"""Tests for executable organization plans."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.core.organize_options import OrganizeOptions
from file_organizer.core.plan import (
    PLAN_SCHEMA_VERSION,
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

# The integration marker keeps core/plan.py above its 85% integration
# coverage floor: these lifecycle tests are the primary coverage of the
# plan module in the integration gate.
pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


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


def test_plan_serializes_behavior_affecting_options(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    plan.options = OrganizeOptions(
        recursive=False,
        include_hidden=True,
        use_hardlinks=plan.use_hardlinks,
        enable_vision=False,
        text_model="qwen",
        vision_model="llava",
    )

    restored = OrganizationPlan.from_dict(plan.to_dict())

    assert restored.options == plan.options


def test_schema_one_plan_is_upgraded_with_legacy_defaults(tmp_path: Path) -> None:
    data = _single_op_plan(tmp_path).to_dict()
    data["schema_version"] = 1
    data.pop("options")
    data["metadata"] = {"enable_vision": False, "prefetch_depth": 0}

    restored = OrganizationPlan.from_dict(data)

    assert restored.schema_version == PLAN_SCHEMA_VERSION
    assert restored.options.enable_vision is False
    assert restored.options.prefetch_depth == 0
    assert restored.options.skip_existing is True


def test_current_plan_requires_matching_options(tmp_path: Path) -> None:
    data = _single_op_plan(tmp_path).to_dict()
    data["options"]["skip_existing"] = False

    with pytest.raises(ValueError, match="skip_existing does not match"):
        OrganizationPlan.from_dict(data)


def test_schema_two_plan_upgrades_legacy_transfer_selector(tmp_path: Path) -> None:
    data = _single_op_plan(tmp_path).to_dict()
    data["schema_version"] = 2
    data["options"].pop("transfer_mode")
    data["options"].pop("methodology")
    data["options"]["use_hardlinks"] = data["use_hardlinks"]

    restored = OrganizationPlan.from_dict(data)

    assert restored.schema_version == PLAN_SCHEMA_VERSION
    assert restored.options.to_dict()["transfer_mode"] == "copy"
    assert restored.options.to_dict()["methodology"] == "none"


def test_plan_operations_are_sorted_by_source_path(tmp_path: Path) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("a")
    second.write_text("b")

    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=tmp_path / "out",
        processed=[_processed(second), _processed(first)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=2,
        skipped_files=0,
        deduplicated_files=0,
    )

    assert [operation.source for operation in plan.operations] == [first, second]


def test_from_dict_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    data = plan.to_dict()
    data["schema_version"] = 999

    with pytest.raises(ValueError, match="Unsupported organization plan schema_version"):
        OrganizationPlan.from_dict(data)


def test_from_dict_rejects_ready_operation_without_fingerprint(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    data = plan.to_dict()
    data["operations"][0]["fingerprint"] = None

    with pytest.raises(ValueError, match="require a source fingerprint"):
        OrganizationPlan.from_dict(data)


def test_from_dict_rejects_invalid_ready_operation_fingerprint(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    data = plan.to_dict()
    data["operations"][0]["fingerprint"] = {"size": "not-an-int", "mtime_ns": 1}

    with pytest.raises(ValueError, match="Invalid source fingerprint"):
        OrganizationPlan.from_dict(data)


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


def test_movements_expose_exact_source_destination_identity(tmp_path: Path) -> None:
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
    )

    rows = plan.movements()

    assert len(rows) == 1
    row = rows[0]
    assert row["operation_id"] == plan.operations[0].operation_id
    assert row["source"] == str(source)
    assert row["destination"] == str(tmp_path / "out" / "Docs" / "input.txt")
    assert row["status"] == "ready"
    assert row["reason"] == "Categorized into Docs"


def test_error_message_summarizes_first_three_conflicts() -> None:
    from file_organizer.core.plan import (
        PlanConflict,
        PlanConflictType,
        PlanValidationResult,
    )

    conflicts = [
        PlanConflict(PlanConflictType.SOURCE_MISSING, f"path-{i}", "gone") for i in range(5)
    ]
    result = PlanValidationResult(can_proceed=False, conflicts=conflicts)

    assert "and 2 more" in result.error_message
    assert PlanValidationResult(can_proceed=True).error_message == ""
    empty = PlanValidationResult(can_proceed=False)
    assert empty.error_message == "Organization plan validation failed."


def test_conflict_str_includes_expected_and_actual() -> None:
    from file_organizer.core.plan import PlanConflict, PlanConflictType

    conflict = PlanConflict(
        PlanConflictType.SOURCE_CHANGED,
        "/p",
        "changed",
        expected="size=1",
        actual="size=2",
    )
    assert "(expected: size=1, actual: size=2)" in str(conflict)


def _single_op_plan(tmp_path: Path, *, use_hardlinks: bool = False):
    source = tmp_path / "input.txt"
    if not source.exists():
        source.write_text("hello")
    return build_plan_from_processed(
        input_path=tmp_path,
        output_path=tmp_path / "out",
        processed=[_processed(source)],
        skip_existing=True,
        use_hardlinks=use_hardlinks,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )


def test_validate_plan_rejects_missing_source(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    (tmp_path / "input.txt").unlink()

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "source_missing" in validation.error_message


def test_validate_plan_rejects_source_replaced_by_symlink(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    source = tmp_path / "input.txt"
    target = tmp_path / "elsewhere.txt"
    target.write_text("other")
    source.unlink()
    source.symlink_to(target)

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "source_symlink" in validation.error_message


def test_validate_plan_rejects_source_replaced_by_directory(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    source = tmp_path / "input.txt"
    source.unlink()
    source.mkdir()

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "source_not_file" in validation.error_message


def test_validate_plan_rejects_destination_created_after_preview(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    destination = tmp_path / "out" / "Docs" / "input.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("raced in")

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "destination_exists" in validation.error_message


def test_validate_plan_rejects_output_root_blocked_by_file(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    (tmp_path / "out").write_text("not a directory")

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert any(c.conflict_type.value == "destination_parent_blocked" for c in validation.conflicts)


def test_validate_plan_rejects_destination_parent_symlink(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    # Symlink target stays inside the output root so the containment check
    # passes and validation reaches the parent-symlink rejection.
    real_docs = output / "real_docs"
    real_docs.mkdir()
    (output / "Docs").symlink_to(real_docs, target_is_directory=True)

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "destination_parent_symlink" in validation.error_message


def test_validate_plan_rejects_destination_parent_blocked_by_file(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    (output / "Docs").write_text("not a directory")

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert any(c.conflict_type.value == "destination_parent_blocked" for c in validation.conflicts)


def test_validate_plan_rejects_content_hash_change(tmp_path: Path) -> None:
    import os

    from file_organizer.core.plan import SourceFingerprint

    plan = _single_op_plan(tmp_path)
    source = tmp_path / "input.txt"
    stat = source.stat()
    operation = plan.operations[0]
    operation.fingerprint = SourceFingerprint(
        size=stat.st_size, mtime_ns=stat.st_mtime_ns, sha256="0" * 64
    )
    # Keep size/mtime matching so validation reaches the content-hash check.
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "content hash changed" in validation.error_message


def test_build_plan_marks_unfingerprintable_source_as_error(tmp_path: Path) -> None:
    missing = tmp_path / "vanished.txt"

    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=tmp_path / "out",
        processed=[_processed(missing)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )

    operation = plan.operations[0]
    assert operation.status == OrganizationOperationStatus.ERROR
    assert operation.error is not None
    assert "Unable to fingerprint source" in operation.error
    assert plan.failed_files == 1


def test_build_plan_preserves_processing_error(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello")
    failed = _processed(source)
    failed.error = "model failed"

    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=tmp_path / "out",
        processed=[failed],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )

    operation = plan.operations[0]
    assert operation.status == OrganizationOperationStatus.ERROR
    assert operation.error == "model failed"


def test_execute_plan_uses_hardlinks_when_requested(tmp_path: Path) -> None:
    plan = _single_op_plan(tmp_path, use_hardlinks=True)
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))

    organized, _, errors = execute_plan(plan, undo_manager=manager)

    destination = tmp_path / "out" / "Docs" / "input.txt"
    assert errors == []
    assert organized == {"Docs": ["input.txt"]}
    assert destination.stat().st_ino == (tmp_path / "input.txt").stat().st_ino


def test_execute_plan_copy_preserves_source_and_creates_independent_file(
    tmp_path: Path,
) -> None:
    plan = _single_op_plan(tmp_path)
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))

    organized, _, errors = execute_plan(plan, undo_manager=manager)

    source = tmp_path / "input.txt"
    destination = tmp_path / "out" / "Docs" / "input.txt"
    assert errors == []
    assert organized == {"Docs": ["input.txt"]}
    assert source.read_text() == destination.read_text() == "hello"
    assert source.stat().st_ino != destination.stat().st_ino


@pytest.mark.parametrize("use_hardlinks", [False, True])
def test_undo_transfer_removes_destination_but_preserves_source(
    tmp_path: Path, use_hardlinks: bool
) -> None:
    plan = _single_op_plan(tmp_path, use_hardlinks=use_hardlinks)
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))
    _, transaction_id, errors = execute_plan(plan, undo_manager=manager)

    assert errors == []
    assert transaction_id is not None
    assert manager.undo_transaction(transaction_id)
    assert (tmp_path / "input.txt").read_text() == "hello"
    assert not (tmp_path / "out" / "Docs" / "input.txt").exists()


def test_validate_plan_rejects_cross_device_hardlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _single_op_plan(tmp_path, use_hardlinks=True)
    source_device = (tmp_path / "input.txt").stat().st_dev
    monkeypatch.setattr("file_organizer.core.plan._filesystem_device", lambda _: source_device + 1)

    validation = validate_plan(plan)

    assert not validation.can_proceed
    assert "hardlink_cross_device" in validation.error_message


def test_plan_rejects_operation_type_that_disagrees_with_transfer_mode(
    tmp_path: Path,
) -> None:
    data = _single_op_plan(tmp_path).to_dict()
    data["operations"][0]["operation_type"] = "hardlink"

    with pytest.raises(ValueError, match="do not match transfer_mode"):
        OrganizationPlan.from_dict(data)


def test_plan_serialization_derives_legacy_transfer_flag_from_options(
    tmp_path: Path,
) -> None:
    plan = _single_op_plan(tmp_path)
    plan.use_hardlinks = True

    assert plan.to_dict()["use_hardlinks"] is False


def test_execute_plan_records_error_when_operation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _single_op_plan(tmp_path)
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))

    def fail_copy(*_: object, **__: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("file_organizer.core.plan._copy_operation_anchored", fail_copy)

    organized, _, errors = execute_plan(plan, undo_manager=manager)

    assert organized == {}
    assert errors == [(str(tmp_path / "input.txt"), "disk full")]


def test_execute_plan_cleans_up_when_history_logging_raises_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _single_op_plan(tmp_path)
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))

    def fail_log(*_: object, **__: object) -> None:
        raise OSError("log disk full")

    monkeypatch.setattr(manager.history, "log_operation", fail_log)

    organized, _, errors = execute_plan(plan, undo_manager=manager)

    assert organized == {}
    assert errors == [(str(tmp_path / "input.txt"), "log disk full")]
    assert not (tmp_path / "out" / "Docs" / "input.txt").exists()


def test_execute_plan_cleans_up_when_commit_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _single_op_plan(tmp_path)
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))

    def fail_commit(_: str) -> None:
        raise OSError("commit disk full")

    monkeypatch.setattr(manager.history, "commit_transaction", fail_commit)

    with pytest.raises(OSError, match="commit disk full"):
        execute_plan(plan, undo_manager=manager)

    assert not (tmp_path / "out" / "Docs" / "input.txt").exists()


def test_sha256_hashes_regular_file_and_none_for_missing(tmp_path: Path) -> None:
    import hashlib

    from file_organizer.core.plan import _sha256

    source = tmp_path / "input.txt"
    source.write_text("hello")

    assert _sha256(source) == hashlib.sha256(b"hello").hexdigest()
    assert _sha256(tmp_path / "missing.txt") is None


def test_parents_from_root_returns_leaf_when_outside_root(tmp_path: Path) -> None:
    from file_organizer.core.plan import _parents_from_root

    root = tmp_path / "out"
    inside = root / "a" / "b"
    outside = tmp_path / "elsewhere"

    assert _parents_from_root(root, outside) == [outside]
    assert _parents_from_root(root, inside) == [root, root / "a", root / "a" / "b"]
