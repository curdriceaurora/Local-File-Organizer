"""Tests for extracted organize web service helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.web.organize_services import (
    _delete_organize_plan,
    _get_organize_plan,
    build_organize_plan,
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
    return result


class TestBuildOrganizePlan:
    def test_builds_and_stores_plan_without_http(self, tmp_path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "notes.txt").write_text("hello")
        (input_dir / "photo.jpg").write_bytes(b"image")

        organizer = MagicMock()
        organizer.organize.return_value = _preview_result({"docs": ["notes.txt"]})
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
                    "file_name": "notes.txt",
                    "source": str(input_dir / "notes.txt"),
                    "destination": str(output_dir / "docs" / "notes.txt"),
                    "reason": "Categorized into docs",
                }
            ]
            organizer_factory.assert_called_once_with(dry_run=True, use_hardlinks=False)
            organizer.organize.assert_called_once_with(
                input_path=input_dir,
                output_path=output_dir,
                skip_existing=True,
            )
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
