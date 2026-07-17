"""Tests for extracted organize web service helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.core.plan import (
    CollisionAction,
    OrganizationOperationStatus,
    build_plan_from_processed,
)
from file_organizer.services.text_processor import ProcessedFile
from file_organizer.web.organize_services import (
    ORGANIZE_MAX_DELAY_MIN,
    _apply_plan_methodology,
    _apply_preview_methodology,
    _build_plan_movements,
    _counts_by_type,
    _delete_organize_plan,
    _get_organize_plan,
    _job_report_payload,
    _methodology_preview_bucket,
    _parse_delay_minutes,
    _result_to_response,
    _scan_directory,
    _split_name_suffix,
    _store_organize_plan,
    build_organize_plan,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


def _preview_result(structure: dict[str, list[str]]) -> MagicMock:
    result = MagicMock()
    result.total_files = sum(len(names) for names in structure.values())
    result.processed_files = result.total_files
    result.skipped_files = 0
    result.failed_files = 0
    result.processing_time = 0.01
    result.organized_structure = structure
    result.errors = []
    return result


def _preview_result_with_plan(input_dir, output_dir, folder: str = "docs") -> MagicMock:
    source = input_dir / "notes.txt"
    plan = build_plan_from_processed(
        input_path=input_dir,
        output_path=output_dir,
        processed=[
            ProcessedFile(
                file_path=source,
                description=f"Categorized into {folder}",
                folder_name=folder,
                filename=source.stem,
            )
        ],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )
    result = _preview_result(plan.organized_structure())
    result.plan = plan
    return result


def test_parse_delay_minutes_validates_bounds_and_defaults() -> None:
    assert _parse_delay_minutes(None) == 0
    assert _parse_delay_minutes(" ") == 0
    assert _parse_delay_minutes("7") == 7

    with pytest.raises(ApiError) as invalid:
        _parse_delay_minutes("soon")
    assert invalid.value.error == "invalid_schedule_delay"

    with pytest.raises(ApiError) as out_of_range:
        _parse_delay_minutes(str(ORGANIZE_MAX_DELAY_MIN + 1))
    assert out_of_range.value.error == "invalid_schedule_delay"


def test_scan_directory_handles_files_hidden_entries_and_recursive(tmp_path) -> None:
    visible = tmp_path / "visible.txt"
    hidden = tmp_path / ".hidden.txt"
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested = nested_dir / "nested.txt"
    for path in (visible, hidden, nested):
        path.write_text("data")

    assert _scan_directory(visible, recursive=False, include_hidden=False) == [visible]
    assert _scan_directory(hidden, recursive=False, include_hidden=False) == []
    assert _scan_directory(hidden, recursive=False, include_hidden=True) == [hidden]
    assert _scan_directory(tmp_path, recursive=False, include_hidden=False) == [visible]
    assert set(_scan_directory(tmp_path, recursive=True, include_hidden=True)) == {
        visible,
        hidden,
        nested,
    }


def test_counts_by_type_covers_all_buckets(tmp_path) -> None:
    files = [
        tmp_path / "notes.txt",
        tmp_path / "photo.jpg",
        tmp_path / "clip.mp4",
        tmp_path / "song.mp3",
        tmp_path / "part.step",
        tmp_path / "archive.bin",
    ]

    assert _counts_by_type(files) == {
        "text": 1,
        "image": 1,
        "video": 1,
        "audio": 1,
        "cad": 1,
        "other": 1,
    }


def test_methodology_preview_preserves_existing_methodology_buckets() -> None:
    assert _methodology_preview_bucket("Projects/Build", "para") == "Projects/Build"
    assert _methodology_preview_bucket("11.01 Notes", "jd") == "11.01 Notes"
    assert _methodology_preview_bucket("docs", "none") == "docs"

    preview = _apply_preview_methodology(
        _result_to_response(_preview_result({"Projects": ["plan.txt"], "docs": ["notes.txt"]})),
        "para",
    )
    assert preview.organized_structure == {
        "Projects": ["plan.txt"],
        "Resources/docs": ["notes.txt"],
    }


def test_build_plan_movements_uses_name_when_source_is_unknown(tmp_path) -> None:
    preview = _preview_result({"docs": ["missing.txt"]})

    assert _build_plan_movements([], tmp_path, preview) == [
        {
            "file_name": "missing.txt",
            "source": "missing.txt",
            "destination": str(tmp_path / "docs" / "missing.txt"),
            "reason": "Categorized into docs",
        }
    ]


def test_apply_plan_methodology_preserves_error_operations(tmp_path) -> None:
    source = tmp_path / "input" / "notes.txt"
    output = tmp_path / "output"
    source.parent.mkdir()
    source.write_text("hello")
    plan = build_plan_from_processed(
        input_path=source.parent,
        output_path=output,
        processed=[ProcessedFile(source, "failed", "docs", source.stem, error="boom")],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )

    remapped = _apply_plan_methodology(plan, "para")

    operation = remapped.operations[0]
    assert operation.status == OrganizationOperationStatus.ERROR
    assert operation.folder_name == "Resources/docs"
    assert operation.destination_path == str(output / "Resources" / "docs" / "notes.txt")
    assert remapped.failed_files == 1


def test_apply_plan_methodology_skips_existing_after_remap(tmp_path) -> None:
    source = tmp_path / "input" / "notes.txt"
    output = tmp_path / "output"
    source.parent.mkdir()
    source.write_text("hello")
    existing = output / "Resources" / "docs" / "notes.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("already there")
    plan = build_plan_from_processed(
        input_path=source.parent,
        output_path=output,
        processed=[ProcessedFile(source, "Categorized into docs", "docs", source.stem)],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )

    remapped = _apply_plan_methodology(plan, "para")

    operation = remapped.operations[0]
    assert operation.status == OrganizationOperationStatus.SKIPPED
    assert operation.collision_action == CollisionAction.SKIP_EXISTING
    assert remapped.processed_files == 0
    assert remapped.skipped_files == 1


def test_apply_plan_methodology_renames_same_run_collision_after_remap(tmp_path) -> None:
    first = tmp_path / "input" / "a"
    second = tmp_path / "input" / "b"
    first.mkdir(parents=True)
    second.mkdir()
    first_source = first / "notes"
    second_source = second / "notes"
    first_source.write_text("one")
    second_source.write_text("two")
    plan = build_plan_from_processed(
        input_path=tmp_path / "input",
        output_path=tmp_path / "output",
        processed=[
            ProcessedFile(first_source, "Categorized into docs", "docs", "notes"),
            ProcessedFile(
                second_source,
                "Categorized into Resources/docs",
                "Resources/docs",
                "notes",
            ),
        ],
        skip_existing=True,
        use_hardlinks=False,
        total_files=2,
        skipped_files=0,
        deduplicated_files=0,
    )

    remapped = _apply_plan_methodology(plan, "para")

    assert [operation.file_name for operation in remapped.operations] == ["notes", "notes_1"]
    assert remapped.operations[1].collision_action == CollisionAction.RENAME_WITH_COUNTER
    assert remapped.processed_files == 2
    assert remapped.skipped_files == 0


def test_split_name_suffix_handles_extensionless_and_hidden_names() -> None:
    assert _split_name_suffix("archive.tar.gz") == ("archive.tar", ".gz")
    assert _split_name_suffix("README") == ("README", "")
    assert _split_name_suffix(".env") == (".env", "")


def test_plan_store_prunes_and_missing_lookup_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("file_organizer.web.organize_services.ORGANIZE_PLAN_LIMIT", 1)
    first = _store_organize_plan({"input_dir": "a"})
    second = _store_organize_plan({"input_dir": "b"})

    try:
        assert _get_organize_plan(first["plan_id"]) is None
        assert _get_organize_plan(second["plan_id"]) is not None
        assert _get_organize_plan("missing") is None
    finally:
        _delete_organize_plan(first["plan_id"])
        _delete_organize_plan(second["plan_id"])


def test_job_report_payload_extracts_report_fields() -> None:
    job = {
        "job_id": "job-1",
        "status": "completed",
        "created_at": "then",
        "updated_at": "now",
        "methodology": "none",
        "input_dir": "/in",
        "output_dir": "/out",
        "dry_run": False,
        "processed_files": 1,
        "total_files": 1,
        "failed_files": 0,
        "skipped_files": 0,
        "error": None,
        "result": {"ok": True},
    }

    assert _job_report_payload(job) == job


class TestBuildOrganizePlan:
    def test_builds_and_stores_plan_without_http(self, tmp_path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "notes.txt").write_text("hello")
        (input_dir / "photo.jpg").write_bytes(b"image")

        organizer = MagicMock()
        organizer.organize.return_value = _preview_result_with_plan(input_dir, output_dir)
        organizer_factory = MagicMock(return_value=organizer)

        plan = build_organize_plan(
            input_dir=str(input_dir),
            output_dir=str(output_dir),
            methodology="content_based",
            recursive="0",
            include_hidden="0",
            skip_existing="1",
            use_hardlinks="0",
            allowed_paths=[str(tmp_path)],
            organizer_factory=organizer_factory,
        )

        try:
            assert _get_organize_plan(plan["plan_id"]) is not None
            assert plan["methodology"] == "none"
            assert plan["recursive"] is False
            assert plan["skip_existing"] is True
            assert plan["use_hardlinks"] is False
            assert plan["scan_counts"]["text"] == 1
            assert plan["scan_counts"]["image"] == 1
            assert plan["scan_total_files"] == 2
            assert plan["movements"] == [
                {
                    "operation_id": plan["movements"][0]["operation_id"],
                    "file_name": "notes.txt",
                    "source": str(input_dir / "notes.txt"),
                    "destination": str(output_dir / "docs" / "notes.txt"),
                    "reason": "Categorized into docs",
                    "status": "ready",
                }
            ]
            organizer_factory.assert_called_once_with(
                dry_run=True,
                use_hardlinks=False,
            )
            organizer.organize.assert_called_once_with(
                input_path=input_dir,
                output_path=output_dir,
                skip_existing=True,
            )
        finally:
            _delete_organize_plan(plan["plan_id"])

    def test_applies_normalized_methodology_to_preview_movements(self, tmp_path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "notes.txt").write_text("hello")

        organizer = MagicMock()
        organizer.organize.return_value = _preview_result_with_plan(input_dir, output_dir)
        organizer_factory = MagicMock(return_value=organizer)

        plan = build_organize_plan(
            input_dir=str(input_dir),
            output_dir=str(output_dir),
            methodology="johnny_decimal",
            recursive="0",
            include_hidden="0",
            skip_existing="1",
            use_hardlinks="0",
            allowed_paths=[str(tmp_path)],
            organizer_factory=organizer_factory,
        )

        try:
            assert plan["methodology"] == "jd"
            organizer_factory.assert_called_once_with(
                dry_run=True,
                use_hardlinks=False,
            )
            assert plan["movements"][0]["destination"] == str(
                output_dir / "30 Operations & Projects" / "docs" / "notes.txt"
            )
        finally:
            _delete_organize_plan(plan["plan_id"])

    def test_applies_para_methodology_to_preview_movements(self, tmp_path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "notes.txt").write_text("hello")

        organizer = MagicMock()
        organizer.organize.return_value = _preview_result_with_plan(input_dir, output_dir)
        organizer_factory = MagicMock(return_value=organizer)

        plan = build_organize_plan(
            input_dir=str(input_dir),
            output_dir=str(output_dir),
            methodology="para",
            recursive="0",
            include_hidden="0",
            skip_existing="1",
            use_hardlinks="0",
            allowed_paths=[str(tmp_path)],
            organizer_factory=organizer_factory,
        )

        try:
            assert plan["methodology"] == "para"
            assert plan["movements"][0]["destination"] == str(
                output_dir / "Resources" / "docs" / "notes.txt"
            )
        finally:
            _delete_organize_plan(plan["plan_id"])

    def test_para_methodology_recomputes_skip_collision_after_remap(self, tmp_path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        (input_dir / "notes.txt").write_text("hello")
        existing = output_dir / "docs" / "notes.txt"
        existing.parent.mkdir(parents=True)
        existing.write_text("already there")

        organizer = MagicMock()
        organizer.organize.return_value = _preview_result_with_plan(input_dir, output_dir)
        organizer_factory = MagicMock(return_value=organizer)

        plan = build_organize_plan(
            input_dir=str(input_dir),
            output_dir=str(output_dir),
            methodology="para",
            recursive="0",
            include_hidden="0",
            skip_existing="1",
            use_hardlinks="0",
            allowed_paths=[str(tmp_path)],
            organizer_factory=organizer_factory,
        )

        try:
            movement = plan["movements"][0]
            assert movement["status"] == "ready"
            assert movement["destination"] == str(output_dir / "Resources" / "docs" / "notes.txt")
            assert plan["preview"]["processed_files"] == 1
            assert plan["preview"]["skipped_files"] == 0
        finally:
            _delete_organize_plan(plan["plan_id"])

    def test_rejects_missing_input_before_preview(self, tmp_path) -> None:
        organizer_factory = MagicMock()

        with pytest.raises(ApiError) as exc_info:
            build_organize_plan(
                input_dir=" ",
                output_dir=str(tmp_path),
                methodology="none",
                recursive="1",
                include_hidden="0",
                skip_existing="1",
                use_hardlinks="1",
                allowed_paths=[str(tmp_path)],
                organizer_factory=organizer_factory,
            )

        assert exc_info.value.error == "missing_input_dir"
        organizer_factory.assert_not_called()

    def test_rejects_missing_output_before_preview(self, tmp_path) -> None:
        organizer_factory = MagicMock()

        with pytest.raises(ApiError) as exc_info:
            build_organize_plan(
                input_dir=str(tmp_path),
                output_dir=" ",
                methodology="none",
                recursive="1",
                include_hidden="0",
                skip_existing="1",
                use_hardlinks="1",
                allowed_paths=[str(tmp_path)],
                organizer_factory=organizer_factory,
            )

        assert exc_info.value.error == "missing_output_dir"
        organizer_factory.assert_not_called()

    def test_rejects_missing_input_path_before_preview(self, tmp_path) -> None:
        organizer_factory = MagicMock()

        with pytest.raises(ApiError) as exc_info:
            build_organize_plan(
                input_dir=str(tmp_path / "missing"),
                output_dir=str(tmp_path),
                methodology="none",
                recursive="1",
                include_hidden="0",
                skip_existing="1",
                use_hardlinks="1",
                allowed_paths=[str(tmp_path)],
                organizer_factory=organizer_factory,
            )

        assert exc_info.value.error == "not_found"
        organizer_factory.assert_not_called()

    def test_rejects_hidden_inclusion_before_preview(self, tmp_path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        organizer_factory = MagicMock()

        with pytest.raises(ApiError) as exc_info:
            build_organize_plan(
                input_dir=str(input_dir),
                output_dir=str(output_dir),
                methodology="none",
                recursive="1",
                include_hidden="1",
                skip_existing="1",
                use_hardlinks="1",
                allowed_paths=[str(tmp_path)],
                organizer_factory=organizer_factory,
            )

        assert exc_info.value.error == "include_hidden_not_supported"
        organizer_factory.assert_not_called()
