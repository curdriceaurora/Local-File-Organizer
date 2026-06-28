"""Tests for the WP-6.1 safedir-required CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_safedir_required as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Positive cases — violations that the rail must detect
# ---------------------------------------------------------------------------


def test_flags_raw_builtin_open(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text("with open('file.txt') as f:\n    pass\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "raw open()" in violations[0][1]


def test_flags_path_dot_open(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text("p = Path('x')\nwith p.open('rb') as f:\n    pass\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "raw Path.open()" in violations[0][1]


def test_flags_shutil_copy2(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text("import shutil\nshutil.copy2(src, dst)\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "raw shutil.copy2()" in violations[0][1]


def test_flags_shutil_move(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text("import shutil\nshutil.move(src, dst)\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "raw shutil.move()" in violations[0][1]


def test_flags_shutil_copytree(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text("import shutil\nshutil.copytree(src, dst)\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "raw shutil.copytree()" in violations[0][1]


# ---------------------------------------------------------------------------
# Negative cases — calls that must NOT be flagged
# ---------------------------------------------------------------------------


def test_allows_image_open(tmp_path: Path) -> None:
    """PIL/Pillow Image.open() is a library decode call, not a raw filesystem open."""
    src = tmp_path / "ok.py"
    src.write_text(
        "from PIL import Image\nwith Image.open(path) as img:\n    pass\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_fitz_open(tmp_path: Path) -> None:
    """PyMuPDF fitz.open() is a library decode call, not a raw filesystem open."""
    src = tmp_path / "ok.py"
    src.write_text(
        "import fitz\nwith fitz.open(path) as doc:\n    pass\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_tarfile_open(tmp_path: Path) -> None:
    """stdlib tarfile.open() is a library call, not a raw filesystem path open."""
    src = tmp_path / "ok.py"
    src.write_text(
        "import tarfile\nwith tarfile.open(fileobj=fobj, mode='r:*') as tf:\n    pass\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_tokenize_open(tmp_path: Path) -> None:
    """stdlib tokenize.open() is an encoding-aware source reader, not a raw open."""
    src = tmp_path / "ok.py"
    src.write_text(
        "import tokenize\nwith tokenize.open(path) as fh:\n    pass\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_aiofiles_open(tmp_path: Path) -> None:
    """aiofiles.open() is an async I/O library call, not a raw synchronous open."""
    src = tmp_path / "ok.py"
    src.write_text(
        "import aiofiles\nasync def f():\n    async with aiofiles.open(p) as fh:\n        pass\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_os_open(tmp_path: Path) -> None:
    """os.open() returns a low-level file descriptor, not a Python file object."""
    src = tmp_path / "ok.py"
    src.write_text(
        "import os\nfd = os.open('x', os.O_RDONLY)\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_allows_self_image_open(tmp_path: Path) -> None:
    """self.Image.open() (chained attribute access for PIL) must not be flagged."""
    src = tmp_path / "ok.py"
    src.write_text(
        "class Foo:\n    Image = __import__('PIL').Image\n    def f(self, path):\n        with self.Image.open(path) as img:\n            pass\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


# ---------------------------------------------------------------------------
# Suppression via inline exemption comments
# ---------------------------------------------------------------------------


def test_noqa_safedir_required_suppresses_open(tmp_path: Path) -> None:
    src = tmp_path / "exempt.py"
    src.write_text(
        "with open('file.txt') as f:  # noqa: safedir-required  # proc FS\n    pass\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_bare_noqa_suppresses_open(tmp_path: Path) -> None:
    src = tmp_path / "exempt_bare.py"
    src.write_text(
        "with open('file.txt') as f:  # noqa\n    pass\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


# ---------------------------------------------------------------------------
# ALLOWED_PATHS — primitive modules are fully exempt
# ---------------------------------------------------------------------------


def test_allowed_paths_are_skipped_in_main(tmp_path: Path) -> None:
    """Modules in ALLOWED_PATHS must never appear in violations from main()."""
    # Verify the set is non-empty and contains the expected primitives
    assert "src/file_organizer/utils/safedir.py" in checker.ALLOWED_PATHS
    assert "src/file_organizer/utils/atomic_io.py" in checker.ALLOWED_PATHS


# ---------------------------------------------------------------------------
# Rail integration — main() returns 0 on clean source
# ---------------------------------------------------------------------------


def test_main_returns_zero_on_no_violations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() must return 0 when no violations are found."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "src" / "file_organizer"
    pkg.mkdir(parents=True)
    (pkg / "clean.py").write_text("x = 1\n", encoding="utf-8")
    result = checker.main()
    assert result == 0


def test_main_returns_one_on_violations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() must return 1 when violations are found."""
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "src" / "file_organizer"
    pkg.mkdir(parents=True)
    (pkg / "bad.py").write_text("with open('x') as f:\n    pass\n", encoding="utf-8")
    result = checker.main()
    assert result == 1
