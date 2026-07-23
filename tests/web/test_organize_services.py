"""Tests for extracted organize web service helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.core import file_ops
from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.organization_service import count_files_by_type
from file_organizer.core.organize_options import OrganizeOptions
from file_organizer.core.plan import build_plan_from_processed
from file_organizer.methodologies import apply_organization_methodology
from file_organizer.services.text_processor import ProcessedFile
from file_organizer.web.organize_services import (
    ORGANIZE_MAX_DELAY_MIN,
    _delete_organize_plan,
    _get_organize_plan,
    _job_report_payload,
    _parse_delay_minutes,
    _store_organize_plan,
    build_organize_plan,
    parse_organize_options,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _preview_result(structure: dict[str, list[str]]) -> MagicMock:
    result = MagicMock()
    result.total_files = sum(len(names) for names in structure.values())
    result.processed_files = result.total_files
    result.skipped_files = 0
    result.failed_files = 0
    result.processing_time = 0.01
    result.organized_structure = structure
    result.errors = []
    result.transaction_id = None
    return result


def _preview_result_with_plan(
    input_dir,
    output_dir,
    folder: str = "docs",
    methodology: str = "none",
    *,
    recursive: bool = False,
    include_hidden: bool = False,
) -> MagicMock:
    source = input_dir / "notes.txt"
    options = OrganizeOptions(
        recursive=recursive,
        include_hidden=include_hidden,
        transfer_mode="copy",
        methodology=methodology,
    )
    processed = apply_organization_methodology(
        [
            ProcessedFile(
                file_path=source,
                description=f"Categorized into {folder}",
                folder_name=folder,
                filename=source.stem,
            )
        ],
        input_root=input_dir,
        methodology=options.effective_methodology,
    )
    plan = build_plan_from_processed(
        input_path=input_dir,
        output_path=output_dir,
        processed=processed,
        skip_existing=True,
        use_hardlinks=False,
        options=options,
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

    assert file_ops.collect_files(visible, recursive=False, include_hidden=False) == [visible]
    assert file_ops.collect_files(hidden, recursive=False, include_hidden=False) == []
    assert file_ops.collect_files(hidden, recursive=False, include_hidden=True) == [hidden]
    assert file_ops.collect_files(tmp_path, recursive=False, include_hidden=False) == [visible]
    assert set(file_ops.collect_files(tmp_path, recursive=True, include_hidden=True)) == {
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

    assert count_files_by_type(files) == {
        "text": 1,
        "image": 1,
        "video": 1,
        "audio": 1,
        "cad": 1,
        "other": 1,
    }


def test_parse_organize_options_maps_complete_canonical_contract() -> None:
    options = parse_organize_options(
        methodology="johnny_decimal",
        recursive="0",
        include_hidden="1",
        skip_existing="0",
        transfer_mode="copy",
        use_hardlinks="1",
        enable_vision="0",
        transcribe_audio="1",
        max_transcribe_seconds="42.5",
        whisper_model="base",
        parallel_workers="3",
        prefetch_depth="4",
        text_model="text-test",
        vision_model="vision-test",
        text_provider="openai",
        vision_provider="mlx",
    )

    assert options.to_dict() == {
        "recursive": False,
        "include_hidden": True,
        "skip_existing": False,
        "transfer_mode": "copy",
        "methodology": "jd",
        "enable_vision": False,
        "transcribe_audio": True,
        "max_transcribe_seconds": 42.5,
        "whisper_model": "base",
        "parallel_workers": 3,
        "prefetch_depth": 4,
        "text_model": "text-test",
        "vision_model": "vision-test",
        "text_provider": "openai",
        "vision_provider": "mlx",
    }


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


def test_plan_store_ttl_expiry_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("file_organizer.web.organize_services.ORGANIZE_PLAN_TTL_SECONDS", -1)
    record = _store_organize_plan({"input_dir": "x"})
    try:
        assert _get_organize_plan(record["plan_id"]) is None
    finally:
        _delete_organize_plan(record["plan_id"])


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
            call = organizer_factory.call_args.kwargs
            assert call["dry_run"] is True
            assert call["use_hardlinks"] is False
            assert call["recursive"] is False
            assert call["include_hidden"] is False
            assert call["organize_options"].effective_methodology.value == "none"
            organizer.organize.assert_called_once_with(
                input_dir,
                output_dir,
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
        organizer.organize.return_value = _preview_result_with_plan(
            input_dir, output_dir, methodology="jd"
        )
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
            assert (
                organizer_factory.call_args.kwargs["organize_options"].effective_methodology.value
                == "jd"
            )
            assert plan["movements"][0]["destination"] == str(
                output_dir / "30 Operations & Projects" / "30.01 docs" / "notes.txt"
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
        organizer.organize.return_value = _preview_result_with_plan(
            input_dir, output_dir, methodology="para"
        )
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
        organizer.organize.return_value = _preview_result_with_plan(
            input_dir, output_dir, methodology="para"
        )
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

        with pytest.raises(DomainError) as exc_info:
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

        assert exc_info.value.code is DomainErrorCode.NOT_FOUND
        organizer_factory.assert_not_called()

    def test_supports_hidden_inclusion_through_canonical_options(self, tmp_path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / ".hidden.txt").write_text("hidden")
        organizer = MagicMock()
        organizer.organize.return_value = _preview_result_with_plan(
            input_dir,
            output_dir,
            recursive=True,
            include_hidden=True,
        )
        organizer_factory = MagicMock(return_value=organizer)

        plan = build_organize_plan(
            input_dir=str(input_dir),
            output_dir=str(output_dir),
            methodology="none",
            recursive="1",
            include_hidden="1",
            skip_existing="1",
            use_hardlinks="0",
            allowed_paths=[str(tmp_path)],
            organizer_factory=organizer_factory,
        )

        try:
            assert plan["include_hidden"] is True
            assert plan["scan_total_files"] == 1
            assert organizer_factory.call_args.kwargs["include_hidden"] is True
        finally:
            _delete_organize_plan(plan["plan_id"])
