"""Integration tests for utils/readers/archives.py.

Covers:
- read_zip_file: basic read, multiple files, max_files truncation,
  empty archive, total_files > max_files, invalid file raises FileReadError,
  compression statistics, PY7ZR_AVAILABLE / RARFILE_AVAILABLE flags
- read_tar_file: plain tar, gzipped tar, bz2 tar, with directories,
  max_files truncation, invalid file raises FileReadError,
  compression type detection
- read_7z_file: raises ImportError if py7zr unavailable (mocked)
- read_rar_file: raises ImportError if rarfile unavailable (mocked)
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip(tmp_path: Path, name: str, files: dict[str, bytes]) -> Path:
    """Create a ZIP archive at tmp_path/name with given filename→content mapping."""
    zip_path = tmp_path / name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)
    return zip_path


def _make_tar(tmp_path: Path, name: str, files: dict[str, bytes], mode: str = "w") -> Path:
    """Create a TAR archive at tmp_path/name."""
    tar_path = tmp_path / name
    with tarfile.open(tar_path, mode) as tf:
        for filename, content in files.items():
            info = tarfile.TarInfo(name=filename)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return tar_path


# ---------------------------------------------------------------------------
# read_zip_file
# ---------------------------------------------------------------------------


class TestReadZipFile:
    def test_basic_zip_returns_string(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(tmp_path, "test.zip", {"a.txt": b"hello"})
        result = read_zip_file(zp)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_zip_contains_filename_in_header(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(tmp_path, "myarchive.zip", {"note.txt": b"content"})
        result = read_zip_file(zp)
        assert "myarchive.zip" in result

    def test_zip_total_files_count(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(
            tmp_path,
            "multi.zip",
            {"a.txt": b"aaa", "b.txt": b"bbb", "c.txt": b"ccc"},
        )
        result = read_zip_file(zp)
        assert "Total files: 3" in result

    def test_zip_lists_files(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(tmp_path, "list.zip", {"readme.md": b"# README"})
        result = read_zip_file(zp)
        assert "readme.md" in result

    def test_zip_max_files_truncates(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        files = {f"{i}.txt": f"file {i}".encode() for i in range(10)}
        zp = _make_zip(tmp_path, "many.zip", files)
        result = read_zip_file(zp, max_files=3)
        assert "and 7 more files" in result

    def test_zip_no_truncation_when_max_files_large(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(tmp_path, "few.zip", {"x.txt": b"x", "y.txt": b"y"})
        result = read_zip_file(zp, max_files=100)
        assert "more files" not in result

    def test_zip_encrypted_field_present(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(tmp_path, "enc.zip", {"data.bin": b"data"})
        result = read_zip_file(zp)
        assert "Encrypted:" in result

    def test_zip_compression_ratio_present(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        # Large content compresses well
        zp = _make_zip(tmp_path, "comp.zip", {"big.txt": b"A" * 10000})
        result = read_zip_file(zp)
        assert "Compression ratio:" in result

    def test_zip_empty_archive(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(tmp_path, "empty.zip", {})
        result = read_zip_file(zp)
        assert "Total files: 0" in result

    def test_zip_accepts_string_path(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(tmp_path, "str.zip", {"f.txt": b"hello"})
        result = read_zip_file(str(zp))
        assert isinstance(result, str)
        assert "f.txt" in result

    def test_zip_accepts_fileobj_with_display_label(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(tmp_path, "safe-opened.zip", {"f.txt": b"hello"})
        with zp.open("rb") as fileobj:
            result = read_zip_file("display-name.zip", fileobj=fileobj)

        assert "ZIP Archive: display-name.zip" in result
        assert "f.txt" in result

    def test_zip_requires_path_or_fileobj(self) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_zip_file()

    def test_zip_invalid_file_raises_file_read_error(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers._base import FileReadError
        from file_organizer.utils.readers.archives import read_zip_file

        broken = tmp_path / "broken.zip"
        broken.write_bytes(b"this is not a zip file")
        with pytest.raises(FileReadError):
            read_zip_file(broken)

    def test_zip_missing_file_raises_file_read_error(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers._base import FileReadError
        from file_organizer.utils.readers.archives import read_zip_file

        with pytest.raises(FileReadError):
            read_zip_file(tmp_path / "nonexistent.zip")

    def test_zip_max_files_zero(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_zip_file

        zp = _make_zip(tmp_path, "zero.zip", {"a.txt": b"a"})
        result = read_zip_file(zp, max_files=0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_py7zr_available_flag_is_bool(self) -> None:
        from file_organizer.utils.readers.archives import PY7ZR_AVAILABLE

        assert PY7ZR_AVAILABLE is True or PY7ZR_AVAILABLE is False

    def test_rarfile_available_flag_is_bool(self) -> None:
        from file_organizer.utils.readers.archives import RARFILE_AVAILABLE

        assert RARFILE_AVAILABLE is True or RARFILE_AVAILABLE is False


# ---------------------------------------------------------------------------
# read_tar_file
# ---------------------------------------------------------------------------


class TestReadTarFile:
    def test_plain_tar_returns_string(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "test.tar", {"doc.txt": b"hello tar"})
        result = read_tar_file(tp)
        assert isinstance(result, str)
        assert "test.tar" in result

    def test_tar_total_files_count(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "multi.tar", {"a.txt": b"a", "b.txt": b"b", "c.txt": b"c"})
        result = read_tar_file(tp)
        assert "Total files: 3" in result

    def test_tar_lists_files(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "list.tar", {"notes.txt": b"notes"})
        result = read_tar_file(tp)
        assert "notes.txt" in result

    def test_tar_gz_compression_detected(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "archive.tar.gz", {"f.txt": b"hello"}, mode="w:gz")
        result = read_tar_file(tp)
        assert "GZ" in result

    def test_tgz_compression_detected(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "archive.tgz", {"f.txt": b"hello"}, mode="w:gz")
        result = read_tar_file(tp)
        assert "GZ" in result

    def test_tar_bz2_compression_detected(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "archive.tar.bz2", {"f.txt": b"hello"}, mode="w:bz2")
        result = read_tar_file(tp)
        assert "BZ2" in result

    def test_plain_tar_no_compression(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "plain.tar", {"f.txt": b"data"})
        result = read_tar_file(tp)
        assert "None" in result

    def test_tar_max_files_truncates(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        files = {f"{i}.txt": f"file {i}".encode() for i in range(10)}
        tp = _make_tar(tmp_path, "many.tar", files)
        result = read_tar_file(tp, max_files=4)
        assert "and 6 more files" in result

    def test_tar_accepts_string_path(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "str.tar", {"f.txt": b"x"})
        result = read_tar_file(str(tp))
        assert isinstance(result, str)
        assert "x" in result

    def test_tar_accepts_fileobj_without_path_uses_unknown_compression(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "stream.tar", {"f.txt": b"x"})
        with tp.open("rb") as fileobj:
            result = read_tar_file(fileobj=fileobj)

        assert "TAR Archive: <fileobj>" in result
        assert "Compression: Unknown" in result
        assert "f.txt" in result

    def test_tar_xz_compression_detected(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "archive.tar.xz", {"f.txt": b"hello"}, mode="w:xz")
        result = read_tar_file(tp)
        assert "XZ" in result

    def test_tar_requires_path_or_fileobj(self) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_tar_file()

    def test_tar_invalid_file_raises_file_read_error(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers._base import FileReadError
        from file_organizer.utils.readers.archives import read_tar_file

        broken = tmp_path / "broken.tar"
        broken.write_bytes(b"not a tar")
        with pytest.raises(FileReadError):
            read_tar_file(broken)

    def test_tar_missing_file_raises_file_read_error(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers._base import FileReadError
        from file_organizer.utils.readers.archives import read_tar_file

        with pytest.raises(FileReadError):
            read_tar_file(tmp_path / "ghost.tar")

    def test_tar_with_directory_members(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tar_path = tmp_path / "withdir.tar"
        with tarfile.open(tar_path, "w") as tf:
            dir_info = tarfile.TarInfo(name="subdir")
            dir_info.type = tarfile.DIRTYPE
            tf.addfile(dir_info)
            file_info = tarfile.TarInfo(name="subdir/file.txt")
            file_info.size = 5
            tf.addfile(file_info, io.BytesIO(b"hello"))

        result = read_tar_file(tar_path)
        assert "Total files: 1" in result
        assert "Total directories: 1" in result

    def test_tar_total_size_reported(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers.archives import read_tar_file

        tp = _make_tar(tmp_path, "size.tar", {"big.txt": b"X" * 2048})
        result = read_tar_file(tp)
        assert "Total size:" in result


# ---------------------------------------------------------------------------
# read_7z_file (ImportError path when py7zr not available)
# ---------------------------------------------------------------------------


class TestRead7zFile:
    def test_raises_import_error_when_py7zr_unavailable(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from file_organizer.utils.readers import archives
        from file_organizer.utils.readers.archives import read_7z_file

        with patch.object(archives, "PY7ZR_AVAILABLE", False):
            with pytest.raises(ImportError, match="py7zr"):
                read_7z_file(tmp_path / "dummy.7z")

    def test_7z_metadata_uses_archive_listing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from file_organizer.utils.readers import archives

        class FakeSevenZipFile:
            password_protected = True

            def __init__(self, fileobj: object, mode: str) -> None:
                assert fileobj is not None
                assert mode == "r"

            def __enter__(self) -> FakeSevenZipFile:
                return self

            def __exit__(self, *exc_info: object) -> None:
                return None

            def list(self) -> list[SimpleNamespace]:
                return [
                    SimpleNamespace(filename="a.txt", compressed=10, uncompressed=100),
                    SimpleNamespace(filename="b.txt", compressed=5, uncompressed=50),
                ]

        monkeypatch.setattr(archives, "PY7ZR_AVAILABLE", True)
        monkeypatch.setattr(
            archives,
            "py7zr",
            SimpleNamespace(SevenZipFile=FakeSevenZipFile),
            raising=False,
        )

        result = archives.read_7z_file("sample.7z", max_files=1, fileobj=io.BytesIO(b"7z"))

        assert "7Z Archive: sample.7z" in result
        assert "Encrypted: Yes" in result
        assert "a.txt" in result
        assert "and 1 more files" in result

    def test_7z_requires_path_or_fileobj_when_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from file_organizer.utils.readers import archives

        monkeypatch.setattr(archives, "PY7ZR_AVAILABLE", True)

        with pytest.raises(ValueError, match="file_path or fileobj"):
            archives.read_7z_file()


# ---------------------------------------------------------------------------
# read_rar_file (ImportError path when rarfile not available)
# ---------------------------------------------------------------------------


class TestReadRarFile:
    def test_raises_import_error_when_rarfile_unavailable(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from file_organizer.utils.readers import archives
        from file_organizer.utils.readers.archives import read_rar_file

        with patch.object(archives, "RARFILE_AVAILABLE", False):
            with pytest.raises(ImportError, match="rarfile"):
                read_rar_file(tmp_path / "dummy.rar")

    def test_rar_metadata_uses_archive_listing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from file_organizer.utils.readers import archives

        class FakeRarFile:
            def __init__(self, fileobj: object, mode: str) -> None:
                assert fileobj is not None
                assert mode == "r"

            def __enter__(self) -> FakeRarFile:
                return self

            def __exit__(self, *exc_info: object) -> None:
                return None

            def infolist(self) -> list[SimpleNamespace]:
                return [
                    SimpleNamespace(filename="a.txt", compress_size=10, file_size=100),
                    SimpleNamespace(filename="b.txt", compress_size=5, file_size=50),
                ]

            def needs_password(self) -> bool:
                return True

        monkeypatch.setattr(archives, "RARFILE_AVAILABLE", True)
        monkeypatch.setattr(
            archives,
            "rarfile",
            SimpleNamespace(RarFile=FakeRarFile, RarCannotExec=RuntimeError),
            raising=False,
        )

        result = archives.read_rar_file("sample.rar", max_files=1, fileobj=io.BytesIO(b"rar"))

        assert "RAR Archive: sample.rar" in result
        assert "Encrypted: Yes" in result
        assert "a.txt" in result
        assert "and 1 more files" in result

    def test_rar_missing_unrar_error_is_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from file_organizer.utils.readers import archives
        from file_organizer.utils.readers._base import FileReadError

        class FakeRarCannotExec(Exception):
            pass

        class FakeRarFile:
            def __init__(self, fileobj: object, mode: str) -> None:
                raise FakeRarCannotExec("missing unrar")

        monkeypatch.setattr(archives, "RARFILE_AVAILABLE", True)
        monkeypatch.setattr(
            archives,
            "rarfile",
            SimpleNamespace(RarFile=FakeRarFile, RarCannotExec=FakeRarCannotExec),
            raising=False,
        )

        with pytest.raises(FileReadError, match="unrar tool not found"):
            archives.read_rar_file("sample.rar", fileobj=io.BytesIO(b"rar"))

    def test_rar_requires_path_or_fileobj_when_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from file_organizer.utils.readers import archives

        monkeypatch.setattr(archives, "RARFILE_AVAILABLE", True)

        with pytest.raises(ValueError, match="file_path or fileobj"):
            archives.read_rar_file()
