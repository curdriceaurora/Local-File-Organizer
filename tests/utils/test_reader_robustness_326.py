"""WP-3.1 archive reader resource caps + decompression-bomb guard (#1229).

The size-cap infrastructure (``_check_file_size``/``_check_fd_size``) already
covered the scientific/document/ebook readers; this work adds:

- ``_check_decompression_bomb`` in ``_base`` — refuses archives whose *declared*
  expansion is bomb-like (absolute cap or implausible ratio above a floor);
- path-branch ``_check_file_size`` parity for every archive reader;
- ``FileTooLargeError`` propagation through the archive readers (not wrapped in
  ``FileReadError``).

RAR reading needs an external ``unrar`` backend, so the rar tests drive a fake
``RarFile`` to exercise the new lines deterministically.
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from file_organizer.utils.readers import archives as _arc
from file_organizer.utils.readers._base import (
    MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    FileTooLargeError,
    _check_decompression_bomb,
)
from file_organizer.utils.readers.archives import (
    read_7z_file,
    read_rar_file,
    read_tar_file,
    read_zip_file,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_MB = 1024 * 1024


# --------------------------------------------------------------------------- #
# _check_decompression_bomb (pure logic — deterministic, no archive libs)
# --------------------------------------------------------------------------- #


def test_bomb_absolute_cap_trips() -> None:
    with pytest.raises(FileTooLargeError, match="expands to"):
        _check_decompression_bomb(MAX_ARCHIVE_UNCOMPRESSED_BYTES + 1, 1000, "x")


def test_bomb_ratio_above_floor_trips() -> None:
    # 100 MB expanded from 10 KB → ratio ~10000:1, above the 64 MB floor.
    with pytest.raises(FileTooLargeError, match="compression ratio"):
        _check_decompression_bomb(100 * _MB, 10 * 1024, "x")


def test_bomb_high_ratio_below_floor_ok() -> None:
    # Huge ratio but only 10 MB expanded (< 64 MB floor) → not flagged.
    _check_decompression_bomb(10 * _MB, 1, "x")


def test_bomb_normal_archive_ok() -> None:
    _check_decompression_bomb(1 * _MB, 100 * 1024, "x")


def test_bomb_tar_style_absolute_trips() -> None:
    # compressed=0 (tar) → only the absolute trigger applies.
    with pytest.raises(FileTooLargeError, match="expands to"):
        _check_decompression_bomb(MAX_ARCHIVE_UNCOMPRESSED_BYTES + 1, 0, "x")


def test_bomb_tar_style_small_ok() -> None:
    _check_decompression_bomb(10 * _MB, 0, "x")


# --------------------------------------------------------------------------- #
# ZIP (stdlib)
# --------------------------------------------------------------------------- #


def _make_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.txt", "hello world")
        zf.writestr("b/c.txt", "more text")


def test_read_zip_normal_path_and_fileobj(tmp_path: Path) -> None:
    p = tmp_path / "x.zip"
    _make_zip(p)
    out_path = read_zip_file(p)
    assert "ZIP Archive" in out_path and "Total files: 2" in out_path
    with p.open("rb") as fh:
        out_fd = read_zip_file(fileobj=fh, file_path=p)
    assert "ZIP Archive" in out_fd


def test_read_zip_bomb_propagates_both_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "x.zip"
    _make_zip(p)

    def _boom(*_a: object, **_k: object) -> None:
        raise FileTooLargeError("bomb")

    monkeypatch.setattr(_arc, "_check_decompression_bomb", _boom)
    # Propagates as FileTooLargeError, not wrapped in FileReadError.
    with pytest.raises(FileTooLargeError):
        read_zip_file(p)
    with p.open("rb") as fh, pytest.raises(FileTooLargeError):
        read_zip_file(fileobj=fh, file_path=p)


# --------------------------------------------------------------------------- #
# TAR (stdlib)
# --------------------------------------------------------------------------- #


def _make_tar(path: Path) -> None:
    with tarfile.open(path, "w") as tf:
        data = b"hello world"
        info = tarfile.TarInfo("a.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))


def test_read_tar_normal_path(tmp_path: Path) -> None:
    p = tmp_path / "x.tar"
    _make_tar(p)
    out = read_tar_file(p)
    assert "TAR Archive" in out and "Total files: 1" in out


def test_read_tar_bomb_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "x.tar"
    _make_tar(p)

    def _boom(*_a: object, **_k: object) -> None:
        raise FileTooLargeError("bomb")

    monkeypatch.setattr(_arc, "_check_decompression_bomb", _boom)
    with pytest.raises(FileTooLargeError):
        read_tar_file(p)
    with p.open("rb") as fh, pytest.raises(FileTooLargeError):
        read_tar_file(fileobj=fh, file_path=p)


# --------------------------------------------------------------------------- #
# 7Z (py7zr installed)
# --------------------------------------------------------------------------- #


def _make_7z(path: Path) -> None:
    import py7zr

    with py7zr.SevenZipFile(path, "w") as archive:
        archive.writestr(b"hello world", "a.txt")


def test_read_7z_normal_path(tmp_path: Path) -> None:
    p = tmp_path / "x.7z"
    _make_7z(p)
    out = read_7z_file(p)
    assert "7Z Archive" in out


def test_read_7z_bomb_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "x.7z"
    _make_7z(p)

    def _boom(*_a: object, **_k: object) -> None:
        raise FileTooLargeError("bomb")

    monkeypatch.setattr(_arc, "_check_decompression_bomb", _boom)
    with pytest.raises(FileTooLargeError):
        read_7z_file(p)
    with p.open("rb") as fh, pytest.raises(FileTooLargeError):
        read_7z_file(fileobj=fh, file_path=p)


# --------------------------------------------------------------------------- #
# RAR (faked — real reading needs an external unrar backend)
# --------------------------------------------------------------------------- #


class _FakeRarInfo:
    def __init__(self, file_size: int, compress_size: int, filename: str = "f.txt") -> None:
        self.file_size = file_size
        self.compress_size = compress_size
        self.filename = filename


class _FakeRarFile:
    def __init__(self, infos: list[_FakeRarInfo]) -> None:
        self._infos = infos

    def __enter__(self) -> _FakeRarFile:
        return self

    def __exit__(self, *_a: object) -> bool:
        return False

    def infolist(self) -> list[_FakeRarInfo]:
        return self._infos

    def needs_password(self) -> bool:
        return False


def _install_fake_rar(monkeypatch: pytest.MonkeyPatch, infos: list[_FakeRarInfo]) -> None:
    monkeypatch.setattr(_arc, "RARFILE_AVAILABLE", True)

    class _Mod:
        RarCannotExec = RuntimeError

        @staticmethod
        def RarFile(_fileobj: object, _mode: str = "r") -> _FakeRarFile:
            return _FakeRarFile(infos)

    monkeypatch.setattr(_arc, "rarfile", _Mod)


def test_read_rar_normal_path_and_fileobj(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_rar(monkeypatch, [_FakeRarInfo(11, 8)])
    p = tmp_path / "x.rar"
    p.write_bytes(b"Rar!\x1a\x07\x00fake")  # content irrelevant; RarFile is faked
    out_path = read_rar_file(p)
    assert "RAR Archive" in out_path
    with p.open("rb") as fh:
        out_fd = read_rar_file(fileobj=fh, file_path=p)
    assert "RAR Archive" in out_fd


def test_read_rar_bomb_trips_real_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Declared expansion over the absolute cap → real guard fires, FileTooLargeError
    # propagates (not wrapped). Exercises the rar bomb-call + except lines.
    _install_fake_rar(monkeypatch, [_FakeRarInfo(MAX_ARCHIVE_UNCOMPRESSED_BYTES + 1, 1000)])
    p = tmp_path / "x.rar"
    p.write_bytes(b"Rar!\x1a\x07\x00fake")
    with pytest.raises(FileTooLargeError):
        read_rar_file(p)
    with p.open("rb") as fh, pytest.raises(FileTooLargeError):
        read_rar_file(fileobj=fh, file_path=p)
