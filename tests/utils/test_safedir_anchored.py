"""Tests for anchored-traversal SafeDir helpers (#286).

Exercises ``SafeDir.open_anchored_reader(relative_path)`` and the
module-level ``read_file_via_safedir_anchored`` wrapper. Both walk a
relative path one component at a time via ``open_subdir`` so an
intermediate-component symlink is refused with ``SymlinkRejected``
rather than dereferenced — closes the nested-ancestor TOCTOU window
documented in #286, separate from the final-component protection that
``SafeDir.open_for_reader`` already provides.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from file_organizer.utils.readers import read_file_via_safedir_anchored
from file_organizer.utils.safedir import SafeDir, SymlinkRejected

# The suite exercises the anchored-traversal primitive end-to-end through
# real filesystem syscalls. Module-level marks apply to every class in
# this file:
#
# - ``ci``: included so the new SafeDir primitive + reader wrapper get
#   diff-coverage credit in the Test PR suite (``-m "ci and not benchmark"``).
# - ``unit``: local development sweep.
# - ``integration``: PR integration job. The per-module floor check in
#   pr-integration.yml drops below the baseline whenever this file's
#   source coverage isn't seen in the integration run.
pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only"),
]

posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SafeDir requires POSIX dir_fd / O_NOFOLLOW",
)


# ---------------------------------------------------------------------------
# SafeDir.open_anchored_reader
# ---------------------------------------------------------------------------


@posix_only
class TestOpenAnchoredReader:
    """Direct tests for the SafeDir.open_anchored_reader primitive."""

    def test_walks_simple_relative_path(self, tmp_path: Path) -> None:
        """Single-component relative_path opens the leaf via open_for_reader."""
        (tmp_path / "doc.txt").write_text("hello")
        with SafeDir.open_root(tmp_path) as root:
            fd = root.open_anchored_reader(Path("doc.txt"))
            try:
                fileobj = os.fdopen(fd, "rb", closefd=True)
            except OSError:
                os.close(fd)
                raise
            with fileobj:
                assert fileobj.read() == b"hello"

    def test_walks_nested_relative_path(self, tmp_path: Path) -> None:
        """Multi-component relative_path walks each intermediate via open_subdir."""
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        (tmp_path / "a" / "b" / "c" / "doc.txt").write_text("nested")
        with SafeDir.open_root(tmp_path) as root:
            fd = root.open_anchored_reader(Path("a/b/c/doc.txt"))
            try:
                fileobj = os.fdopen(fd, "rb", closefd=True)
            except OSError:
                os.close(fd)
                raise
            with fileobj:
                assert fileobj.read() == b"nested"

    def test_intermediate_symlink_refused(self, tmp_path: Path) -> None:
        """Ancestor swapped to symlink between enumeration and read is refused.

        This is the core anchored-traversal protection. The walk opens
        ``a`` first, sees it's a symlink, and raises SymlinkRejected
        before any subsequent component is opened.
        """
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("attacker content")

        inside = tmp_path / "inside"
        inside.mkdir()
        # Originally a directory; gets swapped to a symlink to `outside`
        try:
            (inside / "a").symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation not supported")
        # The "victim" leaf the caller intended to read
        (inside / "doc.txt").write_text("legitimate")

        with SafeDir.open_root(inside) as root:
            # Walking 'a/secret.txt' should refuse at 'a' (the symlink),
            # not dereference and open 'outside/secret.txt'.
            with pytest.raises(SymlinkRejected):
                root.open_anchored_reader(Path("a/secret.txt"))

    def test_final_component_symlink_refused(self, tmp_path: Path) -> None:
        """Leaf symlink is refused too (the existing final-component guard)."""
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("attacker content")
        inside = tmp_path / "inside"
        inside.mkdir()
        try:
            (inside / "doc.txt").symlink_to(outside / "secret.txt")
        except OSError:
            pytest.skip("symlink creation not supported")

        with SafeDir.open_root(inside) as root:
            with pytest.raises(SymlinkRejected):
                root.open_anchored_reader(Path("doc.txt"))

    def test_absolute_path_rejected(self, tmp_path: Path) -> None:
        """Absolute relative_path is a programmer error — reject early."""
        with SafeDir.open_root(tmp_path) as root:
            with pytest.raises(ValueError, match="relative"):
                root.open_anchored_reader(Path("/etc/passwd"))

    def test_parent_traversal_rejected(self, tmp_path: Path) -> None:
        """``..`` components would escape — must be refused before any open."""
        (tmp_path / "child").mkdir()
        (tmp_path / "doc.txt").write_text("data")
        with SafeDir.open_root(tmp_path / "child") as root:
            with pytest.raises(ValueError, match=r"\.\."):
                root.open_anchored_reader(Path("../doc.txt"))

    def test_empty_path_rejected(self, tmp_path: Path) -> None:
        """Empty relative_path doesn't identify any file."""
        with SafeDir.open_root(tmp_path) as root:
            with pytest.raises(ValueError, match="non-empty"):
                root.open_anchored_reader(Path(""))


# ---------------------------------------------------------------------------
# read_file_via_safedir_anchored
# ---------------------------------------------------------------------------


@posix_only
class TestReadFileViaSafedirAnchored:
    """Tests for the top-level anchored reader wrapper."""

    def test_reads_text_in_nested_dir(self, tmp_path: Path) -> None:
        (tmp_path / "docs" / "sub").mkdir(parents=True)
        leaf = tmp_path / "docs" / "sub" / "note.txt"
        leaf.write_text("hello anchored")

        out = read_file_via_safedir_anchored(leaf, trusted_root=tmp_path)
        assert out == "hello anchored"

    def test_intermediate_symlink_refused_via_helper(self, tmp_path: Path) -> None:
        """Same protection as the primitive, exercised through the wrapper.

        Ensures the wrapper actually uses the anchored walk (not a
        parent-rooted open of file_path.parent that would happily
        dereference the ancestor symlink).
        """
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("attacker content")

        inside = tmp_path / "inside"
        inside.mkdir()
        try:
            (inside / "evil").symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation not supported")

        # The leaf path the caller thinks they're reading
        victim = inside / "evil" / "secret.txt"
        with pytest.raises(SymlinkRejected):
            read_file_via_safedir_anchored(victim, trusted_root=inside)

    def test_file_outside_trusted_root_rejected(self, tmp_path: Path) -> None:
        """file_path outside trusted_root is a security violation — raise."""
        trusted = tmp_path / "trusted"
        trusted.mkdir()
        (trusted / "ok.txt").write_text("inside")
        elsewhere = tmp_path / "elsewhere.txt"
        elsewhere.write_text("outside")

        # ``Path.relative_to`` raises ValueError with a message containing
        # "is not in the subpath of" (3.11) or "is not in the descendants of"
        # (3.12+) — match the stable substring across Python versions.
        with pytest.raises(ValueError, match=r"not in (the subpath|the descendants)"):
            read_file_via_safedir_anchored(elsewhere, trusted_root=trusted)

    def test_unsupported_extension_returns_none(self, tmp_path: Path) -> None:
        """Same contract as read_file_via_safedir: None when no reader matches."""
        leaf = tmp_path / "data.unknownext"
        leaf.write_text("payload")

        out = read_file_via_safedir_anchored(leaf, trusted_root=tmp_path)
        assert out is None

    def test_traversal_with_unsupported_extension_rejected(self, tmp_path: Path) -> None:
        """A ``..`` escape with an unsupported suffix must raise up front —
        not silently return None into a caller's legacy path-read fallback
        (Codex P2, PR #1254). ``relative_to`` is lexical and does not raise
        on ``trusted_root / '../x'``, so the component guard must.
        """
        trusted = tmp_path / "trusted"
        trusted.mkdir()
        escaped = trusted / ".." / "secret.unknownext"

        with pytest.raises(ValueError, match="reserved component name"):
            read_file_via_safedir_anchored(escaped, trusted_root=trusted)


# NOTE: ``TestTextProcessorScanRoot`` lives in
# ``tests/services/test_text_processor_scan_root.py`` (kept off the
# ``ci`` mark to avoid #291's audio-model singleton ordering flake —
# see that file's module docstring for the full rationale).
