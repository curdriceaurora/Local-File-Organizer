"""Regression tests for the SafeDir-routed read in
``services.search.hybrid_retriever.read_text_safe`` (PR3h).

The corpus text extractor reads up to ``CORPUS_TEXT_LIMIT`` bytes via
``SafeDir.open_root`` + ``open_for_reader`` so a symlink swapped between
corpus enumeration and the content read is refused rather than
dereferenced (closes the LLM-exfiltration vector documented in #264).

This file exercises every branch the SafeDir migration introduced:
- happy path on a real on-disk file (no mocks)
- ``SymlinkRejected`` returning ``""`` and logging a warning
- ``NotImplementedError`` falling back to the legacy path-based open
- ``os.fdopen`` raising ``OSError`` after the bare fd has been
  obtained (cleanup must not leak the fd)
- legacy path-based ``open`` raising ``OSError`` (returns ``""``)
- defensive limit clamp: ``limit <= 0`` returns ``""`` without reading
- defensive limit clamp: ``limit > CORPUS_TEXT_LIMIT`` is capped
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ``hybrid_retriever`` transitively imports BM25 / sklearn / numpy via its
# ``VectorIndex`` and ``BM25Index`` siblings. The security regression suite
# below must run wherever the corpus read path is exercised, so fail loudly
# (rather than silently skipping the whole module) when the required search
# extra is absent — the gated CI suites install ``.[dev,search]``. Per repo
# convention, missing required test deps are a hard error, not a skip.
try:
    import rank_bm25  # noqa: F401
    import sklearn  # noqa: F401
except ImportError as exc:  # pragma: no cover - deps present in the gated CI suite
    pytest.fail(
        "Missing required test dependency for the read_text_safe security "
        f"regression suite: {exc}. Install the search extra "
        "(pip install -e '.[dev,search]') before running these tests.",
        pytrace=False,
    )

from file_organizer.services.search.hybrid_retriever import (
    CORPUS_TEXT_LIMIT,
    read_text_safe,
)
from file_organizer.utils.safedir import SymlinkRejected

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.integration,
]


class TestReadTextSafeHappyPath:
    """Sanity checks: real on-disk files must still work end-to-end."""

    def test_reads_text_file(self, tmp_path: Path) -> None:
        target = tmp_path / "hello.txt"
        target.write_text("hello world")
        assert read_text_safe(target) == "hello world"

    def test_returns_empty_for_binary_file(self, tmp_path: Path) -> None:
        target = tmp_path / "bin"
        target.write_bytes(b"\x00\x01\x02\x03prefix")
        assert read_text_safe(target) == ""

    def test_caps_at_limit(self, tmp_path: Path) -> None:
        target = tmp_path / "big.txt"
        target.write_text("a" * (CORPUS_TEXT_LIMIT + 1000))
        assert len(read_text_safe(target, limit=128)) == 128


class TestReadTextSafeLimitClamp:
    """Defensive limit handling: non-positive or oversized values must
    not let the underlying ``read(n)`` call read the entire file (S3
    corpus-cap rule)."""

    def test_zero_limit_returns_empty(self, tmp_path: Path) -> None:
        target = tmp_path / "x.txt"
        target.write_text("content")
        assert read_text_safe(target, limit=0) == ""

    def test_negative_limit_returns_empty(self, tmp_path: Path) -> None:
        target = tmp_path / "x.txt"
        target.write_text("content")
        assert read_text_safe(target, limit=-1) == ""

    def test_oversized_limit_clamped_to_corpus_text_limit(self, tmp_path: Path) -> None:
        target = tmp_path / "big.txt"
        target.write_text("a" * (CORPUS_TEXT_LIMIT * 2))
        # An oversized limit must NOT let us read more than CORPUS_TEXT_LIMIT.
        out = read_text_safe(target, limit=CORPUS_TEXT_LIMIT * 2)
        assert len(out) <= CORPUS_TEXT_LIMIT


@pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
class TestReadTextSafeSafedirBranches:
    """Each SafeDir error branch is mocked so we can prove the function
    handles it the way the security contract demands (return ``""``,
    log, no fd leak)."""

    def test_symlink_rejected_returns_empty_string(self, tmp_path: Path) -> None:
        target = tmp_path / "real.txt"
        target.write_text("secret")
        with patch(
            "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
            side_effect=SymlinkRejected("name"),
        ):
            assert read_text_safe(target) == ""

    def test_not_implemented_falls_back_to_legacy_open(self, tmp_path: Path) -> None:
        """When SafeDir is unavailable (e.g. macOS without dir_fd), the
        function must read the file via the legacy ``path.open(...)``
        fallback rather than returning empty.
        """
        target = tmp_path / "fallback.txt"
        target.write_text("fallback content")
        with patch(
            "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
            side_effect=NotImplementedError("no dir_fd"),
        ):
            assert read_text_safe(target) == "fallback content"

    def test_fdopen_failure_closes_bare_fd(self, tmp_path: Path) -> None:
        """If ``os.fdopen`` raises after ``open_for_reader`` already
        returned a raw fd, the function must close that fd explicitly
        (otherwise we leak file descriptors). We verify the cleanup by
        spying on ``os.close``.
        """
        target = tmp_path / "real.txt"
        target.write_text("never read")
        sentinel_fd = 4242

        # Build a fake SafeDir context whose open_for_reader returns
        # our sentinel fd. We don't actually have an OS fd at that
        # number, so we patch os.close to swallow it.
        fake_safe_dir = MagicMock()
        fake_safe_dir.open_for_reader.return_value = sentinel_fd
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_safe_dir
        fake_cm.__exit__.return_value = False

        with (
            patch(
                "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
                return_value=fake_cm,
            ),
            patch(
                "file_organizer.services.search.hybrid_retriever.os.fdopen",
                side_effect=OSError("fdopen blew up"),
            ),
            patch("file_organizer.services.search.hybrid_retriever.os.close") as mock_close,
        ):
            assert read_text_safe(target) == ""
            mock_close.assert_called_once_with(sentinel_fd)

    def test_safedir_oserror_returns_empty(self, tmp_path: Path) -> None:
        """Any non-symlink OSError from the SafeDir branch (e.g. file
        not found at open_for_reader) returns ``""`` — same shape as
        the legacy path's ``except OSError: return ""``."""
        target = tmp_path / "x.txt"
        target.write_text("data")
        with patch(
            "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
            side_effect=OSError("no such file"),
        ):
            assert read_text_safe(target) == ""

    def test_safedir_valueerror_returns_empty(self, tmp_path: Path) -> None:
        """SafeDir's name validation raises ``ValueError`` for
        filenames containing backslash / NUL / path separators. On
        POSIX such filenames are legal in the filesystem, so a corpus
        enumerator can yield them. The helper must return ``""``
        rather than letting the ``ValueError`` abort the caller."""
        target = tmp_path / "ok.txt"
        target.write_text("data")
        with patch(
            "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
            side_effect=ValueError("name 'a\\b' contains path separator"),
        ):
            assert read_text_safe(target) == ""


@pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
class TestReadTextSafeLegacyFallback:
    """When the function falls through to the legacy ``path.open(...)``
    branch (e.g. via ``NotImplementedError``), it must still return
    ``""`` on OSError, matching the original PR1 behavior."""

    def test_legacy_open_oserror_returns_empty(self, tmp_path: Path) -> None:
        target = tmp_path / "x.txt"
        # File never created — Path.open will OSError. We also disable
        # the SafeDir path so we reach the legacy fallback.
        with patch(
            "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
            side_effect=NotImplementedError(),
        ):
            assert read_text_safe(target) == ""


@pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
class TestReadTextSafeAnchoredTraversal:
    """Regression tests for issue #325: component-wise O_NOFOLLOW traversal
    when scan_root is supplied.

    A symlink swapped into an intermediate directory between scan_root and
    the file must be refused (returns ``""``) rather than followed — closes
    the nested-ancestor TOCTOU window documented in #286/#325.
    """

    def test_reads_file_via_scan_root(self, tmp_path: Path) -> None:
        """Happy path: a real file nested under scan_root is read correctly."""
        scan_root = tmp_path / "corpus"
        subdir = scan_root / "sub"
        subdir.mkdir(parents=True)
        target = subdir / "note.txt"
        target.write_text("anchored corpus text")

        result = read_text_safe(target, scan_root=scan_root)
        assert "anchored corpus text" in result

    def test_symlinked_intermediate_dir_is_refused(self, tmp_path: Path) -> None:
        """A symlink swapped into an intermediate directory between scan_root
        and the leaf is refused — regression for the nested-ancestor TOCTOU
        window documented in #286/#325.

        Layout::

            tmp_path/outside/secret.txt    <- sensitive file OUTSIDE scan_root
            tmp_path/scan_root/            <- trusted scan root
            tmp_path/scan_root/evil -> tmp_path/outside   <- symlinked subdir
            apparent path: scan_root/evil/secret.txt

        Without anchored traversal, ``SafeDir.open_root(path.parent)`` would
        open ``evil`` as a plain directory and read secret.txt through it.
        With anchored traversal ``open_anchored_reader`` calls
        ``open_subdir("evil")`` which detects the symlink and raises
        ``SymlinkRejected`` → ``read_text_safe`` returns ``""``.
        """
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("SHOULD_NOT_BE_EXFILTRATED")

        scan_root = tmp_path / "scan_root"
        scan_root.mkdir()

        try:
            (scan_root / "evil").symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        apparent_path = scan_root / "evil" / "secret.txt"
        result = read_text_safe(apparent_path, scan_root=scan_root)
        assert result == ""
        assert "SHOULD_NOT_BE_EXFILTRATED" not in result

    def test_scan_root_none_uses_parent_rooted_safedir(self, tmp_path: Path) -> None:
        """Default (scan_root=None) still uses the parent-rooted SafeDir path —
        no regression on existing callers that don't supply scan_root.
        """
        target = tmp_path / "plain.txt"
        target.write_text("parent rooted")

        from file_organizer.utils.safedir import SafeDir as _SafeDir

        with patch(
            "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
            wraps=_SafeDir.open_root,
        ) as mock_open_root:
            result = read_text_safe(target)

        assert "parent rooted" in result
        mock_open_root.assert_called_once_with(tmp_path)

    def test_scan_root_not_implemented_falls_back_to_legacy(self, tmp_path: Path) -> None:
        """When SafeDir raises NotImplementedError in the anchored branch the
        function falls through to the legacy path.open() read.
        """
        scan_root = tmp_path / "root"
        scan_root.mkdir()
        target = scan_root / "f.txt"
        target.write_text("fallback content")

        with patch(
            "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
            side_effect=NotImplementedError("no dir_fd"),
        ):
            result = read_text_safe(target, scan_root=scan_root)
        assert result == "fallback content"

    def test_scan_root_oserror_returns_empty(self, tmp_path: Path) -> None:
        """An OSError from the anchored SafeDir branch returns ``""``."""
        scan_root = tmp_path / "root"
        scan_root.mkdir()
        target = scan_root / "f.txt"
        target.write_text("data")

        with patch(
            "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
            side_effect=OSError("permission denied"),
        ):
            result = read_text_safe(target, scan_root=scan_root)
        assert result == ""

    def test_path_outside_scan_root_returns_empty(self, tmp_path: Path) -> None:
        """If path does not lie under scan_root, relative_to raises ValueError
        which is caught and ``""`` is returned.
        """
        scan_root = tmp_path / "root"
        scan_root.mkdir()
        outside_dir = tmp_path / "other"
        outside_dir.mkdir()
        outside = outside_dir / "f.txt"
        outside.write_text("outside content")

        result = read_text_safe(outside, scan_root=scan_root)
        assert result == ""

    def test_scan_root_fdopen_failure_closes_bare_fd(self, tmp_path: Path) -> None:
        """When ``os.fdopen`` raises after ``open_anchored_reader`` already
        returned a raw fd, the function must close that fd explicitly to avoid
        leaking it.  Mirrors ``test_fdopen_failure_closes_bare_fd`` but
        exercises the ``scan_root is not None`` branch (lines 97-99).
        """
        scan_root = tmp_path / "root"
        scan_root.mkdir()
        target = scan_root / "f.txt"
        target.write_text("never read")
        sentinel_fd = 4243

        # Build a fake SafeDir context whose open_anchored_reader returns
        # our sentinel fd.  We patch os.close so the sentinel int doesn't
        # reach the real close() syscall.
        fake_safe_dir = MagicMock()
        fake_safe_dir.open_anchored_reader.return_value = sentinel_fd
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_safe_dir
        fake_cm.__exit__.return_value = False

        with (
            patch(
                "file_organizer.services.search.hybrid_retriever.SafeDir.open_root",
                return_value=fake_cm,
            ),
            patch(
                "file_organizer.services.search.hybrid_retriever.os.fdopen",
                side_effect=OSError("fdopen blew up in anchored branch"),
            ),
            patch("file_organizer.services.search.hybrid_retriever.os.close") as mock_close,
        ):
            result = read_text_safe(target, scan_root=scan_root)
        assert result == ""
        mock_close.assert_called_once_with(sentinel_fd)
