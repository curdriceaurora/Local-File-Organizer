"""Focused tests for profile avatar helper logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.web.profile_avatars import avatar_path, resolve_avatar_for_read

pytestmark = [pytest.mark.unit]


def test_avatar_path_rejects_path_separators(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid user_id"):
        avatar_path("../bad", tmp_path)


def test_resolve_avatar_for_read_uses_contained_filename(tmp_path: Path) -> None:
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir()
    stored = avatar_dir / "user-id.png"
    stored.write_bytes(b"png-data")

    result = resolve_avatar_for_read("user-id", avatar_dir)

    assert result == stored.resolve()


def test_resolve_avatar_for_read_fails_closed_when_safedir_unavailable(tmp_path: Path) -> None:
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir()
    (avatar_dir / "user-id.png").write_bytes(b"png-data")

    def unavailable(_path: Path):
        raise NotImplementedError

    with pytest.raises(FileNotFoundError, match="Avatar not found"):
        resolve_avatar_for_read("user-id", avatar_dir, safe_dir_open=unavailable)
