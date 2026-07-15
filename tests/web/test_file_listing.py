"""Tests for web file listing service helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.web.file_listing import collect_entries, normalized_extension

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def test_normalized_extension_preserves_supported_compound_archives() -> None:
    assert normalized_extension(Path("backup.tar.gz")) == ".tar.gz"
    assert normalized_extension(Path("backup.tar.bz2")) == ".tar.bz2"
    assert normalized_extension(Path("backup.tar.xz")) == ".xz"


def test_collect_entries_filters_hidden_query_and_type(tmp_path: Path) -> None:
    (tmp_path / "Projects").mkdir()
    (tmp_path / ".Hidden").mkdir()
    (tmp_path / "project-notes.txt").write_text("notes")
    (tmp_path / "project-image.png").write_bytes(b"png")
    (tmp_path / ".project-secret.txt").write_text("secret")

    entries, total = collect_entries(
        tmp_path,
        query="project",
        file_type=".txt",
        sort_by="name",
        sort_order="asc",
        include_hidden=False,
        limit=10,
    )

    assert total == 2
    assert [entry["name"] for entry in entries] == ["Projects", "project-notes.txt"]


def test_collect_entries_keeps_directories_before_limited_files(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "zeta.txt").write_text("z")

    entries, total = collect_entries(
        tmp_path,
        query=None,
        file_type=None,
        sort_by="name",
        sort_order="asc",
        include_hidden=False,
        limit=2,
    )

    assert total == 3
    assert [entry["name"] for entry in entries] == ["alpha", "beta"]
