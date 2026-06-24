"""Unit tests for src/core/path_guard.py (Epic A.foundation, hardening roadmap #154).

The `path_guard` module provides two primitives:

- `validate_within_roots(path, allowed_roots)` — assert `path` is inside one
  of `allowed_roots` and return its resolved absolute form. Raises
  `PathTraversalError` otherwise. Used by A.cli to harden every CLI command
  that takes a path argument.
- `safe_walk(root, *, follow_symlinks, include_hidden)` — yield files under
  `root`, filtering symlinks and hidden entries by default. Used by A.walkers
  to replace raw `rglob("*")` calls that risk indexing `/etc/passwd` or
  `.env` / `.ssh/authorized_keys`.

These tests pin both the happy path and the security-boundary behavior
(symlinks resolve outside, `..` traversal, hidden-dir semantics when root
itself is hidden).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from file_organizer.core.path_guard import PathTraversalError, safe_walk, validate_within_roots

# --------------------------------------------------------------------------
# validate_within_roots
# --------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.integration
class TestValidateWithinRoots:
    def test_path_equal_to_root_is_allowed(self, tmp_path: Path) -> None:
        """A command invoked with its root as the path arg is legitimate."""
        assert validate_within_roots(tmp_path, [tmp_path]) == tmp_path.resolve()

    def test_path_strictly_inside_root_is_allowed(self, tmp_path: Path) -> None:
        nested = tmp_path / "sub" / "file.txt"
        nested.parent.mkdir()
        nested.write_text("hi")
        result = validate_within_roots(nested, [tmp_path])
        assert result == nested.resolve()

    def test_path_outside_root_raises(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "elsewhere"
        with pytest.raises(PathTraversalError, match="outside allowed roots"):
            validate_within_roots(outside, [tmp_path])

    def test_dotdot_traversal_is_normalized_and_rejected(self, tmp_path: Path) -> None:
        """`<tmp>/allowed/../outside` resolves to `<tmp>/outside`; must fail
        even though the literal string starts with an allowed-root prefix.
        """
        inside = tmp_path / "inside"
        inside.mkdir()
        traversal = inside / ".." / ".." / "etc"
        with pytest.raises(PathTraversalError):
            validate_within_roots(traversal, [inside])

    def test_multiple_roots_any_match_allows(self, tmp_path: Path) -> None:
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        target = root_b / "file.txt"
        target.write_text("x")
        # Matches the second root — must not raise.
        result = validate_within_roots(target, [root_a, root_b])
        assert result == target.resolve()

    def test_empty_allowed_roots_raises(self, tmp_path: Path) -> None:
        """A command with no declared roots cannot validate any path —
        refuse rather than silently accept everything.
        """
        with pytest.raises(PathTraversalError, match="No allowed roots"):
            validate_within_roots(tmp_path, [])

    def test_returns_resolved_absolute_path(self, tmp_path: Path) -> None:
        """Caller gets the canonical resolved form back, not the original
        (which may be relative or contain symlinks) — enables safe downstream
        use without re-resolving.
        """
        rel_cwd = tmp_path / "sub"
        rel_cwd.mkdir()
        result = validate_within_roots(rel_cwd, [tmp_path])
        assert result.is_absolute()
        assert result == rel_cwd.resolve()

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only symlink semantics")
    def test_symlink_inside_root_resolving_outside_raises(self, tmp_path: Path) -> None:
        """A symlink inside `allowed` that points at `/outside` must fail:
        resolve() follows the link, the comparison catches it.
        """
        inside = tmp_path / "inside"
        inside.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        link = inside / "escape"
        link.symlink_to(outside)
        with pytest.raises(PathTraversalError):
            validate_within_roots(link, [inside])

    def test_resolve_runtime_error_is_wrapped_as_path_traversal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cyclic symlinks make `Path.resolve()` raise `RuntimeError`, not
        `ValueError`. Callers expect `PathTraversalError` / `ValueError`
        uniformly, so the helper must wrap resolver failures.
        """
        path = tmp_path / "cyclic"
        original_resolve = Path.resolve

        def raise_cycle(self: Path, strict: bool = False) -> Path:
            if self == path:
                raise RuntimeError("symlink loop")
            return original_resolve(self, strict=strict)

        monkeypatch.setattr(Path, "resolve", raise_cycle)
        with pytest.raises(PathTraversalError, match="symlink cycle or stale handle"):
            validate_within_roots(path, [tmp_path])

    def test_allowed_root_resolve_failure_raises_path_traversal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broken allowed root (cyclic symlink, OS error) must also be
        surfaced as `PathTraversalError` — not a raw `RuntimeError`.
        """
        bad_root = tmp_path / "bad_root"
        original_resolve = Path.resolve

        def raise_for_bad(self: Path, strict: bool = False) -> Path:
            if self == bad_root:
                raise OSError("device offline")
            return original_resolve(self, strict=strict)

        monkeypatch.setattr(Path, "resolve", raise_for_bad)
        with pytest.raises(PathTraversalError, match="resolve allowed roots"):
            validate_within_roots(tmp_path / "x.txt", [bad_root])


# --------------------------------------------------------------------------
# safe_walk
# --------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.integration
class TestSafeWalk:
    def test_yields_plain_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result = sorted(p.name for p in safe_walk(tmp_path))
        assert result == ["a.txt", "b.txt"]

    def test_skips_hidden_files_by_default(self, tmp_path: Path) -> None:
        (tmp_path / "visible.txt").write_text("v")
        (tmp_path / ".hidden").write_text("h")
        names = {p.name for p in safe_walk(tmp_path)}
        assert names == {"visible.txt"}

    def test_skips_files_under_hidden_dirs_by_default(self, tmp_path: Path) -> None:
        (tmp_path / "visible.txt").write_text("v")
        hidden = tmp_path / ".git"
        hidden.mkdir()
        (hidden / "config").write_text("x")
        names = {p.name for p in safe_walk(tmp_path)}
        assert names == {"visible.txt"}

    def test_hidden_subtrees_are_not_descended_into(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify that hidden subtrees (e.g. `.git/`) are pruned up-front
        and never even scanned, avoiding O(N) filesystem work.
        """
        import os
        (tmp_path / "visible.txt").write_text("v")
        hidden = tmp_path / ".git"
        hidden.mkdir()
        (hidden / "sentinel.txt").write_text("s")

        scanned_paths = []
        original_scandir = os.scandir

        def mock_scandir(path):
            scanned_paths.append(Path(path).resolve())
            return original_scandir(path)

        monkeypatch.setattr(os, "scandir", mock_scandir)

        # Walk the directory
        result = list(safe_walk(tmp_path))
        
        # Verify the file was yielded but the hidden files were not
        assert [p.name for p in result] == ["visible.txt"]
        
        # Verify that we scanned tmp_path but NEVER scanned inside `.git`
        scanned_names = {p.name for p in scanned_paths}
        assert tmp_path.resolve() in scanned_paths
        assert ".git" not in scanned_names

    def test_include_hidden_returns_them(self, tmp_path: Path) -> None:
        (tmp_path / "visible.txt").write_text("v")
        (tmp_path / ".hidden").write_text("h")
        hidden_dir = tmp_path / ".git"
        hidden_dir.mkdir()
        (hidden_dir / "config").write_text("x")
        names = {p.name for p in safe_walk(tmp_path, include_hidden=True)}
        assert names == {"visible.txt", ".hidden", "config"}

    def test_hidden_filter_is_relative_to_root(self, tmp_path: Path) -> None:
        """If the user explicitly walks a hidden directory (e.g. they cd
        into `.git/` and run `fo analyze`), the files inside shouldn't all
        be filtered just because the root itself starts with a dot.
        """
        hidden_root = tmp_path / ".hidden_root"
        hidden_root.mkdir()
        (hidden_root / "normal.txt").write_text("x")
        (hidden_root / ".nested").write_text("skip-me")
        names = {p.name for p in safe_walk(hidden_root)}
        assert names == {"normal.txt"}

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only symlink semantics")
    def test_skips_symlinks_by_default(self, tmp_path: Path) -> None:
        (tmp_path / "real.txt").write_text("r")
        target = tmp_path / "target.txt"
        target.write_text("t")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        names = {p.name for p in safe_walk(tmp_path)}
        # target.txt is a real file; link.txt is a symlink and must be skipped.
        assert names == {"real.txt", "target.txt"}

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only symlink semantics")
    def test_skips_symlinked_directories(self, tmp_path: Path) -> None:
        """A symlinked directory's contents must not be yielded by default —
        the whole subtree could live outside the allowed root.
        """
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "inside.txt").write_text("x")
        link_dir = tmp_path / "link"
        link_dir.symlink_to(real_dir, target_is_directory=True)
        # The link itself is a symlink — rglob may or may not descend
        # depending on follow_symlinks default. Our helper skips any path
        # that has a symlink component.
        walked = list(safe_walk(tmp_path))
        names = {p.name for p in walked}
        assert "inside.txt" in names  # real subtree reachable directly
        # link/inside.txt would be a dup via the symlink — must be absent.
        rel_paths = {str(p.relative_to(tmp_path)) for p in walked}
        assert "link/inside.txt" not in rel_paths

    def test_follow_symlinks_flag_includes_linked_files(self, tmp_path: Path) -> None:
        if sys.platform == "win32":
            pytest.skip("POSIX-only symlink semantics")
        target = tmp_path / "target.txt"
        target.write_text("t")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        names = {p.name for p in safe_walk(tmp_path, follow_symlinks=True)}
        assert names == {"target.txt", "link.txt"}

    def test_nonexistent_root_yields_empty(self, tmp_path: Path) -> None:
        result = list(safe_walk(tmp_path / "does-not-exist"))
        assert result == []

    def test_empty_root_yields_empty(self, tmp_path: Path) -> None:
        result = list(safe_walk(tmp_path))
        assert result == []

    def test_directory_is_not_yielded_by_default(self, tmp_path: Path) -> None:
        """Default `only_files=True`: directories are never yielded."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "file.txt").write_text("x")
        yielded = list(safe_walk(tmp_path))
        assert len(yielded) == 1
        assert yielded[0].name == "file.txt"
        assert yielded[0].is_file()

    def test_only_files_false_yields_directories_too(self, tmp_path: Path) -> None:
        """`only_files=False` is used by empty-directory cleanup and similar
        callers that operate on directory entries.
        """
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").write_text("x")
        yielded = {p.name for p in safe_walk(tmp_path, only_files=False)}
        assert yielded == {"sub", "file.txt"}

    def test_non_recursive_yields_top_level_only(self, tmp_path: Path) -> None:
        (tmp_path / "top.txt").write_text("t")
        deep = tmp_path / "sub" / "deep.txt"
        deep.parent.mkdir()
        deep.write_text("d")
        yielded = {p.name for p in safe_walk(tmp_path, recursive=False)}
        assert yielded == {"top.txt"}

    def test_custom_pattern_filters(self, tmp_path: Path) -> None:
        """Callers that previously did `rglob("*.py")` or `rglob(query)`
        pass their pattern through `pattern=...` and keep the security
        filters.
        """
        (tmp_path / "keep.py").write_text("x")
        (tmp_path / "skip.txt").write_text("x")
        yielded = {p.name for p in safe_walk(tmp_path, pattern="*.py")}
        assert yielded == {"keep.py"}

    def test_custom_pattern_still_filters_symlinks(self, tmp_path: Path) -> None:
        """Security defaults hold even when a custom pattern is used."""
        if sys.platform == "win32":
            pytest.skip("POSIX-only symlink semantics")
        target = tmp_path / "real.py"
        target.write_text("x")
        link = tmp_path / "link.py"
        link.symlink_to(target)
        yielded = {p.name for p in safe_walk(tmp_path, pattern="*.py")}
        assert yielded == {"real.py"}

    def test_symlinked_root_rejected_when_follow_symlinks_false(self, tmp_path: Path) -> None:
        """Security: a directory symlink passed as `root` must not enumerate
        its target. The per-entry symlink filter only catches descendants —
        `rglob()` on a symlink root yields paths from the target first, and
        the root itself is never checked unless we guard it upfront.
        """
        if sys.platform == "win32":
            pytest.skip("POSIX-only symlink semantics")
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret")
        inside = tmp_path / "inside"
        inside.mkdir()
        linked_root = inside / "link_root"
        linked_root.symlink_to(outside, target_is_directory=True)

        # Default follow_symlinks=False → walking a symlinked root yields
        # nothing (rather than leaking `outside/secret.txt`).
        assert list(safe_walk(linked_root)) == []

        # With follow_symlinks=True the caller opts into traversal.
        walked = list(safe_walk(linked_root, follow_symlinks=True))
        assert any(p.name == "secret.txt" for p in walked)

    def test_nonexistent_root_after_stat_error_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`root.exists()` / `root.is_symlink()` can themselves raise OSError
        (e.g. stale NFS handle). The helper must yield nothing instead of
        propagating.
        """
        ghost = tmp_path / "ghost"

        def raise_exists(self: Path) -> bool:
            if self == ghost:
                raise OSError("stale handle")
            return True

        monkeypatch.setattr(Path, "exists", raise_exists)
        assert list(safe_walk(ghost)) == []

    def test_per_entry_permission_error_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One inaccessible entry must not abort the whole walk.

        Callers like `doctor.scan_directory` scan directories that may
        contain entries whose `is_symlink()` / `is_file()` raise
        `PermissionError`. The walker skips those entries and keeps going.
        """
        good = tmp_path / "good.txt"
        good.write_text("x")
        bad = tmp_path / "bad.txt"
        bad.write_text("x")

        original_is_symlink = Path.is_symlink

        def _raise_for_bad(self: Path) -> bool:
            if self.name == "bad.txt":
                raise PermissionError(f"denied: {self}")
            return original_is_symlink(self)

        monkeypatch.setattr(Path, "is_symlink", _raise_for_bad)
        yielded = {p.name for p in safe_walk(tmp_path)}
        assert yielded == {"good.txt"}

    def test_per_entry_os_error_in_is_dir_and_is_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify that OSErrors during is_dir() and is_file() are caught and handled gracefully."""
        good = tmp_path / "good.txt"
        good.write_text("x")
        bad_dir = tmp_path / "bad_dir"
        bad_dir.mkdir()
        bad_file = tmp_path / "bad_file.txt"
        bad_file.write_text("x")
        
        original_is_dir = Path.is_dir
        original_is_file = Path.is_file
        
        def mock_is_dir(self: Path) -> bool:
            if self.name == "bad_dir":
                raise OSError("device error on is_dir")
            return original_is_dir(self)
            
        def mock_is_file(self: Path) -> bool:
            if self.name == "bad_file.txt":
                raise OSError("device error on is_file")
            return original_is_file(self)
            
        monkeypatch.setattr(Path, "is_dir", mock_is_dir)
        monkeypatch.setattr(Path, "is_file", mock_is_file)
        
        yielded = {p.name for p in safe_walk(tmp_path)}
        assert "good.txt" in yielded
        assert "bad_dir" not in yielded
        assert "bad_file.txt" not in yielded

    def test_scandir_os_error_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify that an OSError during os.scandir is caught and yields nothing for that subtree."""
        import os
        original_scandir = os.scandir
        
        def mock_scandir(path):
            raise OSError("scandir failed")
            
        monkeypatch.setattr(os, "scandir", mock_scandir)
        assert list(safe_walk(tmp_path)) == []


@pytest.mark.ci
@pytest.mark.integration
class TestPathTraversalError:
    def test_is_value_error_subclass(self) -> None:
        """Downstream code that catches ValueError continues to work —
        PathTraversalError just adds a dedicated class for precise except
        clauses.
        """
        assert issubclass(PathTraversalError, ValueError)


# --------------------------------------------------------------------------
# Sanity: the helper must not rely on cwd-relative paths
# --------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.integration
def test_helpers_work_regardless_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The helpers resolve absolute paths internally, so changing cwd
    shouldn't change the outcome.
    """
    root = tmp_path / "project"
    root.mkdir()
    inside = root / "file.txt"
    inside.write_text("x")
    monkeypatch.chdir(os.sep)  # root of filesystem
    result = validate_within_roots(inside, [root])
    assert result == inside.resolve()
    walked = list(safe_walk(root))
    assert walked == [inside.resolve()]
