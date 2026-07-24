"""Integration regressions for executable organization plan review fixes."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.organize import router
from file_organizer.core.file_ops import collect_files
from file_organizer.core.organization_service import count_files_by_type
from file_organizer.core.organize_options import OrganizeOptions
from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import (
    CollisionAction,
    OrganizationOperationStatus,
    OrganizationPlan,
    PlanValidationResult,
    build_plan_from_processed,
    execute_plan,
    validate_plan,
)
from file_organizer.history.tracker import OperationHistory
from file_organizer.services.text_processor import ProcessedFile
from file_organizer.undo import UndoManager
from file_organizer.web.organize_services import (
    _ORGANIZE_PLAN_STORE,
    _delete_organize_plan,
    _get_organize_plan,
    _parse_delay_minutes,
    _prune_plan_store,
    _store_organize_plan,
)

pytestmark = [pytest.mark.integration, pytest.mark.ci]

# ``execute_plan`` transfers files through SafeDir, which needs POSIX dir_fd /
# O_NOFOLLOW; the Windows port is deferred (#264). CI Full Matrix runs this
# ci-marked file on Windows, where SafeDir raises NotImplementedError — and
# because that subclasses RuntimeError it surfaces as a confusing
# "regex did not match" inside pytest.raises rather than a clear skip.
requires_safedir = pytest.mark.skipif(
    sys.platform == "win32", reason="execute_plan uses SafeDir, which is POSIX-only (#264)"
)


def _processed(path: Path, folder: str = "Docs") -> ProcessedFile:
    return ProcessedFile(
        file_path=path,
        description=f"Categorized into {folder}",
        folder_name=folder,
        filename=path.stem,
    )


def _single_plan(tmp_path: Path, *, use_hardlinks: bool = False):
    source = tmp_path / "input" / "notes.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("reviewed")
    return build_plan_from_processed(
        input_path=source.parent,
        output_path=tmp_path / "output",
        processed=[_processed(source)],
        skip_existing=True,
        use_hardlinks=use_hardlinks,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
        file_hashes={source: hashlib.sha256(b"reviewed").hexdigest()},
        options=OrganizeOptions(
            use_hardlinks=use_hardlinks,
            text_model="test-model:latest",
            vision_model="vis:3b",
            text_provider="ollama",
            vision_provider="ollama",
        ),
    )


@requires_safedir
def test_execute_plan_cleans_up_when_commit_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _single_plan(tmp_path)
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))

    monkeypatch.setattr(manager.history, "commit_transaction", lambda _: False)

    with pytest.raises(RuntimeError, match="Failed to commit organization transaction"):
        execute_plan(plan, undo_manager=manager)

    assert not (tmp_path / "output" / "Docs" / "notes.txt").exists()


@requires_safedir
def test_execute_plan_verifies_open_source_before_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _single_plan(tmp_path)
    source = tmp_path / "input" / "notes.txt"

    def replace_after_validation(_: object) -> PlanValidationResult:
        source.write_text("swapped")
        return PlanValidationResult(can_proceed=True)

    monkeypatch.setattr("file_organizer.core.plan.validate_plan", replace_after_validation)

    organized, _, errors = execute_plan(
        plan,
        undo_manager=UndoManager(history=OperationHistory(tmp_path / "history.db")),
    )

    assert organized == {}
    assert errors == [(str(source), "Source metadata changed after preview.")]
    assert not (tmp_path / "output" / "Docs" / "notes.txt").exists()


@requires_safedir
def test_execute_plan_hardlinks_verified_source(tmp_path: Path) -> None:
    plan = _single_plan(tmp_path, use_hardlinks=True)

    organized, _, errors = execute_plan(
        plan,
        undo_manager=UndoManager(history=OperationHistory(tmp_path / "history.db")),
    )

    destination = tmp_path / "output" / "Docs" / "notes.txt"
    assert errors == []
    assert organized == {"Docs": ["notes.txt"]}
    assert destination.stat().st_ino == (tmp_path / "input" / "notes.txt").stat().st_ino


def test_file_organizer_empty_scan_returns_noop_plan(tmp_path: Path) -> None:
    input_dir = tmp_path / "empty"
    input_dir.mkdir()

    result = FileOrganizer(dry_run=True, use_hardlinks=False).organize(
        input_path=input_dir,
        output_path=tmp_path / "output",
    )

    assert result.total_files == 0
    assert result.plan is not None
    assert result.plan.operations == []


def test_api_preview_plan_executes_round_trip(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    plan = _single_plan(tmp_path)
    settings = ApiSettings(
        environment="test",
        auth_enabled=False,
        allowed_paths=[str(tmp_path)],
        auth_jwt_secret="test-secret",
        rate_limit_enabled=False,
    )
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_active_user] = lambda: MagicMock(
        is_active=True,
        is_admin=True,
    )
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    with patch("file_organizer.api.routers.organize.FileOrganizer") as organizer_cls:
        organizer = organizer_cls.return_value
        organizer.organize.return_value = MagicMock(
            total_files=1,
            processed_files=1,
            skipped_files=0,
            failed_files=0,
            deduplicated_files=0,
            processing_time=0.0,
            organized_structure=plan.organized_structure(),
            errors=[],
            plan=plan,
            transaction_id=None,
        )
        organizer.execute_plan.return_value = organizer.organize.return_value

        preview = client.post(
            "/api/v1/organize/preview",
            json={"input_dir": str(input_dir), "output_dir": str(output_dir)},
        )
        response = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(input_dir),
                "output_dir": str(output_dir),
                "run_in_background": False,
                "plan": preview.json()["plan"],
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    organizer.execute_plan.assert_called_once()


def test_plan_deserialization_rejects_missing_or_invalid_fingerprint(tmp_path: Path) -> None:
    plan_data = _single_plan(tmp_path).to_dict()
    plan_data["operations"][0]["fingerprint"] = None

    with pytest.raises(ValueError, match="source fingerprint"):
        OrganizationPlan.from_dict(plan_data)

    plan_data = _single_plan(tmp_path).to_dict()
    plan_data["operations"][0]["fingerprint"]["size"] = "large"

    with pytest.raises(ValueError, match="Invalid source fingerprint"):
        OrganizationPlan.from_dict(plan_data)


def test_plan_records_skipped_collisions_and_fingerprint_errors(tmp_path: Path) -> None:
    source = tmp_path / "input" / "notes.txt"
    source.parent.mkdir(parents=True)
    source.write_text("reviewed")
    destination = tmp_path / "output" / "Docs" / "notes.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("existing")
    missing = tmp_path / "input" / "missing.txt"

    plan = build_plan_from_processed(
        input_path=source.parent,
        output_path=tmp_path / "output",
        processed=[_processed(source), _processed(missing)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=2,
        skipped_files=0,
        deduplicated_files=0,
    )

    operations = {operation.source: operation for operation in plan.operations}
    assert operations[source].status == OrganizationOperationStatus.SKIPPED
    assert operations[source].collision_action == CollisionAction.SKIP_EXISTING
    assert operations[missing].status == OrganizationOperationStatus.ERROR
    assert "Unable to fingerprint source" in (operations[missing].error or "")


def test_validate_plan_reports_source_and_destination_conflicts(tmp_path: Path) -> None:
    plan = _single_plan(tmp_path)
    source = tmp_path / "input" / "notes.txt"
    extra_source = tmp_path / "input" / "extra.txt"
    extra_source.write_text("extra")
    source.unlink()
    (tmp_path / "output" / "Docs").mkdir(parents=True)
    (tmp_path / "output" / "Docs" / "notes.txt").write_text("existing")
    plan.operations.append(
        build_plan_from_processed(
            input_path=tmp_path / "input",
            output_path=tmp_path / "output",
            processed=[_processed(extra_source)],
            skip_existing=True,
            use_hardlinks=False,
            total_files=1,
            skipped_files=0,
            deduplicated_files=0,
        ).operations[0]
    )
    (tmp_path / "output" / "Docs" / "extra.txt").write_text("existing")

    validation = validate_plan(plan)

    conflict_types = {conflict.conflict_type.value for conflict in validation.conflicts}
    assert "source_missing" in conflict_types
    assert "destination_exists" in conflict_types
    assert "source_missing" in validation.error_message


@requires_safedir
def test_execute_plan_cleans_destination_when_history_logging_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _single_plan(tmp_path)
    manager = UndoManager(history=OperationHistory(tmp_path / "history.db"))

    def fail_log(*_: object, **__: object) -> None:
        raise RuntimeError("history unavailable")

    monkeypatch.setattr(manager.history, "log_operation", fail_log)

    organized, _, errors = execute_plan(plan, undo_manager=manager)

    assert organized == {}
    assert errors == [(str(tmp_path / "input" / "notes.txt"), "history unavailable")]
    assert not (tmp_path / "output" / "Docs" / "notes.txt").exists()


@requires_safedir
def test_file_organizer_plan_helpers_execute_and_restore_state(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "notes.txt"
    source.write_text("reviewed")
    organizer = FileOrganizer(dry_run=False, use_hardlinks=False)

    plan = organizer.build_plan(input_dir, tmp_path / "preview-output")
    result = organizer.execute_plan(plan)

    assert organizer.dry_run is False
    assert result.processed_files == 1
    assert any((tmp_path / "preview-output").rglob("*.txt"))


def test_web_organize_helpers_cover_scan_and_store_paths(tmp_path: Path) -> None:
    visible = tmp_path / "visible.txt"
    hidden = tmp_path / ".hidden.txt"
    cad = tmp_path / "drawing.dwg"
    visible.write_text("visible")
    hidden.write_text("hidden")
    cad.write_text("cad")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "clip.mp4").write_text("video")

    files = collect_files(tmp_path, recursive=True, include_hidden=False)
    counts = count_files_by_type(files)
    plan = build_plan_from_processed(
        input_path=tmp_path,
        output_path=tmp_path / "out",
        processed=[_processed(visible, "Documents")],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )
    record = _store_organize_plan({"payload": True})
    fetched = _get_organize_plan(record["plan_id"])
    _delete_organize_plan(record["plan_id"])

    assert hidden not in files
    assert counts["text"] == 1
    assert counts["cad"] == 1
    assert counts["video"] == 1
    assert plan.movements()[0]["destination"].endswith("visible.txt")
    assert fetched is not None and fetched["payload"] is True
    assert _get_organize_plan(record["plan_id"]) is None


def test_web_organize_helper_validation_branches(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="whole number"):
        _parse_delay_minutes("later")
    with pytest.raises(Exception, match="between"):
        _parse_delay_minutes("-1")

    assert _parse_delay_minutes(None) == 0
    assert _parse_delay_minutes("  ") == 0
    _ORGANIZE_PLAN_STORE.clear()
    for index in range(205):
        _ORGANIZE_PLAN_STORE[str(index)] = {"index": index}
    _prune_plan_store()

    assert len(_ORGANIZE_PLAN_STORE) == 200


def test_plan_store_ttl_evicts_expired_records() -> None:
    from datetime import UTC, datetime

    past = datetime(2000, 1, 1, tzinfo=UTC)

    record = _store_organize_plan({"ttl_test": True})
    plan_id = record["plan_id"]
    try:
        _ORGANIZE_PLAN_STORE[plan_id]["created_at"] = past
        _prune_plan_store()
        assert _ORGANIZE_PLAN_STORE.get(plan_id) is None
    finally:
        _delete_organize_plan(plan_id)

    record2 = _store_organize_plan({"ttl_test": True})
    plan_id2 = record2["plan_id"]
    try:
        _ORGANIZE_PLAN_STORE[plan_id2]["created_at"] = past
        result = _get_organize_plan(plan_id2)
        assert result is None
    finally:
        _delete_organize_plan(plan_id2)
