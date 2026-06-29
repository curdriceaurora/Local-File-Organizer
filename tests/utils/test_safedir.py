"""Tests for ``utils.safedir`` — POSIX-safe directory-fd filesystem operations.

Implementation of #266 in the security hardening series (#264).

`SafeDir` holds an open directory file descriptor and exposes operations
that route through `dir_fd=` + `O_NOFOLLOW`. The invariant: every operation
takes a single path *component*, never a path string, so attacker-controlled
segments can't escape the held directory.

Threat model coverage anchored by these tests:

- Symlink swap between enumeration and read — `open_for_reader` /
  `open_child` raise `SymlinkRejected` rather than dereferencing.
- Component-name injection — names containing `/`, `\\`, `..`, or NUL are
  rejected with `ValueError` before any syscall.
- File-descriptor leaks — context-manager exit releases the held fd.
- Cross-directory atomicity — `rename_into` between two `SafeDir`s uses
  `os.rename` with both source and destination `dir_fd`.

Platform: POSIX only. Windows has no equivalent for `O_NOFOLLOW` /
`dir_fd=`; the `SafeDir.open_root` factory raises `NotImplementedError`
there (see #264 for the deferral).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from file_organizer.utils.safedir import SafeDir, SymlinkRejected

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only primitive"),
]


# ---------------------------------------------------------------------------
# Component-name validation
# ---------------------------------------------------------------------------


class TestNameValidation:
    """Every method that takes a *name* must reject path-component injection."""

    @pytest.fixture
    def sd(self, tmp_path: Path):
        with SafeDir.open_root(tmp_path) as sd:
            yield sd

    @pytest.mark.parametrize(
        "bad_name",
        [
            "a/b",
            "../escape",
            "..",
            ".",
            "",
            "a\x00b",
            "foo\\bar",
            "/abs",
        ],
    )
    def test_open_child_rejects_bad_name(self, sd: SafeDir, bad_name: str) -> None:
        with pytest.raises(
            ValueError,
            match=r"reserved component name|forbidden character|requires a non-empty relative path|requires a relative path|refuses '\\.\\.'|absolute",
        ):
            sd.open_child(bad_name)

    @pytest.mark.parametrize("bad_name", ["a/b", "..", "", "x\x00y"])
    def test_open_for_reader_rejects_bad_name(self, sd: SafeDir, bad_name: str) -> None:
        with pytest.raises(
            ValueError,
            match=r"forbidden character|reserved component name|requires a non-empty relative path|refuses '\\.\\.'",
        ):
            sd.open_for_reader(bad_name)

    @pytest.mark.parametrize("bad_name", ["a/b", "..", "."])
    def test_open_subdir_rejects_bad_name(self, sd: SafeDir, bad_name: str) -> None:
        with pytest.raises(
            ValueError,
            match=r"forbidden character|reserved component name|requires a non-empty relative path|refuses '\\.\\.'",
        ):
            sd.open_subdir(bad_name)

    @pytest.mark.parametrize("bad_name", ["a/b", ".."])
    def test_lstat_rejects_bad_name(self, sd: SafeDir, bad_name: str) -> None:
        with pytest.raises(
            ValueError, match=r"forbidden character|reserved component name|refuses '\\.\\.'"
        ):
            sd.lstat(bad_name)

    @pytest.mark.parametrize("bad_name", ["a/b", "..", ""])
    def test_unlink_rejects_bad_name(self, sd: SafeDir, bad_name: str) -> None:
        with pytest.raises(
            ValueError,
            match=r"forbidden character|reserved component name|requires a non-empty relative path|refuses '\\.\\.'",
        ):
            sd.unlink(bad_name)

    @pytest.mark.parametrize("bad_name", ["a/b", "..", ""])
    def test_mkdir_rejects_bad_name(self, sd: SafeDir, bad_name: str) -> None:
        with pytest.raises(
            ValueError,
            match=r"forbidden character|reserved component name|requires a non-empty relative path|refuses '\\.\\.'",
        ):
            sd.mkdir(bad_name)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_open_root_and_close_on_context_exit(self, tmp_path: Path) -> None:
        """Context exit closes the held fd."""
        sd = SafeDir.open_root(tmp_path)
        fd = sd.fd
        sd.__exit__(None, None, None)
        with pytest.raises(OSError, match="Bad file descriptor"):
            # Closed fd — fstat raises EBADF.
            os.fstat(fd)

    def test_open_for_reader_returns_readable_fd(self, tmp_path: Path) -> None:
        (tmp_path / "data.txt").write_bytes(b"hello")
        with SafeDir.open_root(tmp_path) as sd:
            fd = sd.open_for_reader("data.txt")
            try:
                assert os.read(fd, 5) == b"hello"
            finally:
                os.close(fd)

    def test_open_for_reader_via_fdopen(self, tmp_path: Path) -> None:
        """Confirms the canonical 'pass to library reader' pattern works."""
        (tmp_path / "data.txt").write_bytes(b"payload")
        with SafeDir.open_root(tmp_path) as sd:
            fd = sd.open_for_reader("data.txt")
            with os.fdopen(fd, "rb") as f:
                assert f.read() == b"payload"

    def test_scandir_yields_names(self, tmp_path: Path) -> None:
        (tmp_path / "a").write_text("x")
        (tmp_path / "b").write_text("y")
        with SafeDir.open_root(tmp_path) as sd:
            names = sorted(sd.scandir())
        assert names == ["a", "b"]
        # Yielded values are plain strings, not DirEntry objects —
        # callers can't reach symlink-following helpers.
        for name in names:
            assert isinstance(name, str)

    def test_scandir_materializes_eagerly_so_iteration_cannot_outlive_safedir(
        self, tmp_path: Path
    ) -> None:
        """``os.scandir(fd)`` dup's the fd, so a lazy generator could
        keep yielding entries after ``SafeDir.__exit__`` closed the
        SafeDir. Materializing names eagerly is the lifecycle
        guarantee: the iterator returned by ``scandir()`` doesn't hold
        an OS handle and can be safely consumed after the SafeDir is
        closed (the data is already in memory; only future *operations*
        on the SafeDir fail).
        """
        (tmp_path / "a").write_text("x")
        (tmp_path / "b").write_text("y")
        sd = SafeDir.open_root(tmp_path)
        try:
            it = sd.scandir()
        finally:
            sd.__exit__(None, None, None)
        # Iterator survives SafeDir exit (names are already materialized);
        # this is the contract — data is safe to consume, but no further
        # syscalls happen.
        assert sorted(it) == ["a", "b"]

    def test_scandir_filters_symlinks(self, tmp_path: Path) -> None:
        """``DirEntry.is_file()`` / ``.stat()`` default to following
        symlinks; filtering them out of scandir prevents naive callers
        from classifying a symlink-to-file as a regular file (which
        would bypass the SafeDir invariant before reaching
        ``open_for_reader``).
        """
        (tmp_path / "honey").write_bytes(b"do_not_exfiltrate")
        organize = tmp_path / "organize"
        organize.mkdir()
        (organize / "regular.txt").write_text("real")
        try:
            (organize / "link").symlink_to(tmp_path / "honey")
            (organize / "link_to_dir").symlink_to(tmp_path, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")

        with SafeDir.open_root(organize) as sd:
            names = list(sd.scandir())
        assert names == ["regular.txt"]

    def test_lstat_does_not_follow_symlink(self, tmp_path: Path) -> None:
        (tmp_path / "target").write_text("target content")
        try:
            (tmp_path / "link").symlink_to(tmp_path / "target")
        except OSError:
            pytest.skip("symlink creation not supported")
        with SafeDir.open_root(tmp_path) as sd:
            st = sd.lstat("link")
        import stat as _stat

        assert _stat.S_ISLNK(st.st_mode), "lstat should report the symlink, not the target"

    def test_unlink_removes_via_dir_fd(self, tmp_path: Path) -> None:
        target = tmp_path / "doomed"
        target.write_text("x")
        with SafeDir.open_root(tmp_path) as sd:
            sd.unlink("doomed")
        assert not target.exists()

    def test_mkdir_creates_subdir(self, tmp_path: Path) -> None:
        with SafeDir.open_root(tmp_path) as sd:
            sd.mkdir("new_category")
        assert (tmp_path / "new_category").is_dir()

    def test_open_subdir_returns_new_safedir(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "leaf.txt").write_bytes(b"leaf content")
        with SafeDir.open_root(tmp_path) as root, root.open_subdir("sub") as sub:
            fd = sub.open_for_reader("leaf.txt")
            try:
                assert os.read(fd, 12) == b"leaf content"
            finally:
                os.close(fd)

    def test_rename_into_same_dir(self, tmp_path: Path) -> None:
        (tmp_path / "old").write_text("data")
        with SafeDir.open_root(tmp_path) as sd:
            sd.rename_into("old", sd, "new")
        assert not (tmp_path / "old").exists()
        assert (tmp_path / "new").read_text() == "data"

    def test_rename_into_cross_dir(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()
        (src_dir / "doc.txt").write_text("moved")
        with (
            SafeDir.open_root(src_dir) as src,
            SafeDir.open_root(dst_dir) as dst,
        ):
            src.rename_into("doc.txt", dst, "doc.txt")
        assert not (src_dir / "doc.txt").exists()
        assert (dst_dir / "doc.txt").read_text() == "moved"

    def test_rename_into_rejects_symlinked_source(self, tmp_path: Path) -> None:
        """``os.rename`` has no O_NOFOLLOW. A TOCTOU swap (scandir
        yields a regular file, then attacker replaces it with a symlink
        before rename) would otherwise move the symlink into the
        managed destination — contaminating the trusted output tree
        with a pointer outside the SafeDir root.
        """
        (tmp_path / "honey").write_bytes(b"do_not_exfiltrate")
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()
        try:
            (src_dir / "report.pdf").symlink_to(tmp_path / "honey")
        except OSError:
            pytest.skip("symlink creation not supported")

        with (
            SafeDir.open_root(src_dir) as src,
            SafeDir.open_root(dst_dir) as dst,
            pytest.raises(SymlinkRejected),
        ):
            src.rename_into("report.pdf", dst, "report.pdf")

        # Destination must remain empty — no symlink leaked through.
        assert list(dst_dir.iterdir()) == []
        # Source symlink remains in place (rename refused).
        assert (src_dir / "report.pdf").is_symlink()


# ---------------------------------------------------------------------------
# Symlink rejection — the headline security guarantee
# ---------------------------------------------------------------------------


class TestSymlinkRejection:
    """`O_NOFOLLOW` on every open. A swapped symlink raises `SymlinkRejected`."""

    def test_open_for_reader_rejects_symlinked_file(self, tmp_path: Path) -> None:
        honey = tmp_path / "honey"
        honey.write_bytes(b"do_not_exfiltrate")
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "report.pdf").symlink_to(honey)
        except OSError:
            pytest.skip("symlink creation not supported")
        with SafeDir.open_root(organize) as sd:
            with pytest.raises(SymlinkRejected):
                sd.open_for_reader("report.pdf")

    def test_open_child_rejects_symlinked_file(self, tmp_path: Path) -> None:
        (tmp_path / "honey").write_bytes(b"do_not_exfiltrate")
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "link").symlink_to(tmp_path / "honey")
        except OSError:
            pytest.skip("symlink creation not supported")
        with SafeDir.open_root(organize) as sd:
            with pytest.raises(SymlinkRejected):
                sd.open_child("link")

    def test_open_subdir_rejects_symlinked_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "honey_dir"
        target.mkdir()
        (target / "secret.txt").write_text("oops")
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "documents").symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")
        with SafeDir.open_root(organize) as sd:
            with pytest.raises(SymlinkRejected):
                sd.open_subdir("documents")

    def test_open_root_rejects_symlinked_root(self, tmp_path: Path) -> None:
        """If the root passed to ``open_root`` is itself a symlink, refuse."""
        real_root = tmp_path / "real"
        real_root.mkdir()
        try:
            link = tmp_path / "link"
            link.symlink_to(real_root, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")
        with pytest.raises(SymlinkRejected):
            SafeDir.open_root(link)

    def test_open_root_rejects_symlinked_root_when_passed_as_string(self, tmp_path: Path) -> None:
        """``open_root`` accepts str / PathLike callers too.

        Before the boundary-normalization fix, the ``ENOTDIR`` error path
        called ``path.is_symlink()`` directly — which would raise
        ``AttributeError`` instead of the documented ``SymlinkRejected``
        when a CLI/config caller passed an un-typed string.
        """
        real_root = tmp_path / "real"
        real_root.mkdir()
        try:
            link = tmp_path / "link"
            link.symlink_to(real_root, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")
        # Pass the path as a string, not a Path object.
        with pytest.raises(SymlinkRejected):
            SafeDir.open_root(str(link))

    def test_symlink_rejected_is_oserror(self) -> None:
        """``SymlinkRejected`` subclasses ``OSError`` so existing handlers work."""
        assert issubclass(SymlinkRejected, OSError)

    def test_open_child_rejects_o_path(self, tmp_path: Path) -> None:
        """``O_PATH | O_NOFOLLOW`` on Linux returns an fd for the symlink
        itself instead of raising ELOOP — that would silently violate the
        documented "no symlinks" contract. The public API must refuse it.

        On platforms without ``O_PATH`` (macOS, BSD) the bug doesn't exist;
        ``_O_PATH == 0`` makes this skip cleanly.
        """
        if not hasattr(os, "O_PATH"):
            pytest.skip("O_PATH is Linux-only; bug doesn't exist on this platform")

        (tmp_path / "regular").write_text("x")
        with SafeDir.open_root(tmp_path) as sd:
            with pytest.raises(ValueError, match="O_PATH"):
                sd.open_child("regular", flags=os.O_PATH)

    def test_open_child_rejects_o_path_even_for_real_files(self, tmp_path: Path) -> None:
        """Predicate-negative: the rejection fires on the flag, not on whether
        the entry is a symlink. A regular file with ``O_PATH`` must still be
        refused so callers can't 'just happen to' use the flag safely and
        later trip on it with an attacker-controlled symlink (T10).
        """
        if not hasattr(os, "O_PATH"):
            pytest.skip("O_PATH is Linux-only")

        (tmp_path / "regular").write_text("x")
        with SafeDir.open_root(tmp_path) as sd:
            with pytest.raises(ValueError, match="O_PATH"):
                sd.open_child("regular", flags=os.O_PATH | os.O_RDONLY)

    def test_open_child_excl_create_rejects_symlinked_target(self, tmp_path: Path) -> None:
        """``O_CREAT|O_EXCL`` returns EEXIST (not ELOOP) on an existing
        symlink. The documented contract is "symlink → SymlinkRejected",
        so this case must disambiguate via lstat rather than leak through
        as ``FileExistsError``. Otherwise an exclusive-create caller might
        treat ``EEXIST`` as benign "file already exists" and miss the
        symlink-swap attack.
        """
        (tmp_path / "honey").write_bytes(b"do_not_exfiltrate")
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "out.txt").symlink_to(tmp_path / "honey")
        except OSError:
            pytest.skip("symlink creation not supported")

        excl_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        with SafeDir.open_root(organize) as sd, pytest.raises(SymlinkRejected):
            sd.open_child("out.txt", flags=excl_flags)

    def test_open_child_excl_create_passes_through_real_file_eexist(self, tmp_path: Path) -> None:
        """T10 predicate-negative: when the existing entry is a regular
        file (not a symlink), ``O_CREAT|O_EXCL`` must still surface
        ``FileExistsError``, not ``SymlinkRejected``. The disambiguation
        check fires only on actual symlinks.
        """
        (tmp_path / "out.txt").write_text("already here")
        excl_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        with SafeDir.open_root(tmp_path) as sd, pytest.raises(FileExistsError):
            sd.open_child("out.txt", flags=excl_flags)

    def test_open_child_excl_create_succeeds_for_new_name(self, tmp_path: Path) -> None:
        """T10 positive control: ``O_CREAT|O_EXCL`` on a non-existent name
        succeeds (no symlink, no existing file). Confirms the new error
        path doesn't break the happy case.
        """
        with SafeDir.open_root(tmp_path) as sd:
            fd = sd.open_child("fresh.txt", flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            try:
                os.write(fd, b"hello")
            finally:
                os.close(fd)
        assert (tmp_path / "fresh.txt").read_bytes() == b"hello"

    def test_open_child_creates_files_with_non_executable_mode(self, tmp_path: Path) -> None:
        """`os.open` defaults `mode=0o777`; with the typical 022 umask
        that gives 0o755 — files created via SafeDir would be
        unexpectedly executable. The default must match the high-level
        `open()` builtin (0o666 pre-umask → 0o644 post-umask).
        """
        with SafeDir.open_root(tmp_path) as sd:
            fd = sd.open_child("output.txt", flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            os.close(fd)
        st = (tmp_path / "output.txt").stat()
        import stat as _stat

        # The exact mode depends on the test environment's umask, but
        # under no reasonable umask (000 through 077) does 0o666 produce
        # an executable file. Assert no execute bits anywhere.
        exec_bits = _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH
        assert (st.st_mode & exec_bits) == 0, (
            f"file created with executable bits: {oct(st.st_mode)}"
        )

    def test_open_child_honors_explicit_mode(self, tmp_path: Path) -> None:
        """Callers can request stricter permissions (e.g. 0o600 for
        secret-bearing files). The explicit mode is passed through to
        `os.open` so the umask is still applied.
        """
        # Set a permissive umask so the explicit mode is what we observe.
        # umask is restored by the conftest fixture isolation; for this
        # test we just need to know the umask doesn't strip our bits.
        prev_umask = os.umask(0)
        try:
            with SafeDir.open_root(tmp_path) as sd:
                fd = sd.open_child(
                    "secret.txt",
                    flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    mode=0o600,
                )
                os.close(fd)
        finally:
            os.umask(prev_umask)
        st = (tmp_path / "secret.txt").stat()
        assert (st.st_mode & 0o777) == 0o600, (
            f"explicit mode 0o600 not honored: {oct(st.st_mode & 0o777)}"
        )

    def test_open_child_directory_flag_rejects_symlinked_target(self, tmp_path: Path) -> None:
        """``O_DIRECTORY`` against a symlink returns ENOTDIR (not ELOOP) —
        the symlink inode itself isn't a directory. Disambiguate via lstat
        so the contract holds: callers using the generic ``open_child``
        helper with ``O_DIRECTORY`` get the documented ``SymlinkRejected``
        rather than ``NotADirectoryError`` for symlinked targets.
        """
        honey_dir = tmp_path / "honey"
        honey_dir.mkdir()
        (honey_dir / "secret.txt").write_text("do_not_exfiltrate")
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "documents").symlink_to(honey_dir, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")

        with SafeDir.open_root(organize) as sd, pytest.raises(SymlinkRejected):
            sd.open_child("documents", flags=os.O_DIRECTORY)

    def test_open_child_directory_flag_propagates_enotdir_for_regular_file(
        self, tmp_path: Path
    ) -> None:
        """T10 predicate-negative: ``O_DIRECTORY`` against a regular file
        must still surface ``NotADirectoryError``, not ``SymlinkRejected``.
        Disambiguation fires only on actual symlinks.
        """
        (tmp_path / "regular.txt").write_text("not a directory")
        with SafeDir.open_root(tmp_path) as sd, pytest.raises(NotADirectoryError):
            sd.open_child("regular.txt", flags=os.O_DIRECTORY)


# ---------------------------------------------------------------------------
# Resource lifetime
# ---------------------------------------------------------------------------


class TestResourceLifetime:
    """Verify the held fd is released on context-manager exit and on subdir
    chains.

    `T13` from `test-generation-patterns.md` — using `tmp_path` everywhere
    rather than hardcoded paths.
    """

    def _count_fds(self) -> int | None:
        """Return the number of open fds for this process, or None on platforms
        where ``/proc/self/fd`` is unavailable (e.g. macOS).
        """
        proc = Path("/") / "proc" / "self" / "fd"
        if not proc.is_dir():
            return None
        return len(list(proc.iterdir()))

    def test_context_manager_releases_root_fd(self, tmp_path: Path) -> None:
        before = self._count_fds()
        if before is None:
            pytest.skip("/proc/self/fd not available on this platform")
        for _ in range(20):
            with SafeDir.open_root(tmp_path):
                pass
        after = self._count_fds()
        assert after is not None
        # Allow a small slack for any incidental fd churn (logging, gc).
        assert after - before <= 2, f"fd leak: before={before} after={after}"

    def test_context_manager_releases_subdir_fd(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        before = self._count_fds()
        if before is None:
            pytest.skip("/proc/self/fd not available on this platform")
        with SafeDir.open_root(tmp_path) as root:
            for _ in range(20):
                with root.open_subdir("sub"):
                    pass
        after = self._count_fds()
        assert after is not None
        assert after - before <= 2, f"fd leak: before={before} after={after}"

    def test_close_does_not_doublefree(self, tmp_path: Path) -> None:
        """Exiting the context manager twice is harmless."""
        sd = SafeDir.open_root(tmp_path)
        sd.__exit__(None, None, None)
        # Calling exit again must NOT raise (it could happen if the user
        # writes their own try/finally + with-statement).
        sd.__exit__(None, None, None)


class TestUseAfterClose:
    """Methods must refuse to operate on a closed SafeDir.

    POSIX recycles fd numbers eagerly — if a caller retains a closed
    ``SafeDir`` and then invokes a method on it, the stale ``self._fd``
    could address an unrelated directory that the kernel reassigned
    that number to (after any subsequent ``os.open`` in the same
    process). Each method calls ``self._check_open()`` first so the
    failure is loud rather than silently operating on the wrong dir.
    """

    @pytest.fixture
    def closed_sd(self, tmp_path: Path) -> SafeDir:
        sd = SafeDir.open_root(tmp_path)
        sd.__exit__(None, None, None)
        return sd

    def test_fd_property_raises(self, closed_sd: SafeDir) -> None:
        with pytest.raises(ValueError, match="closed"):
            _ = closed_sd.fd

    def test_open_child_raises(self, closed_sd: SafeDir) -> None:
        with pytest.raises(ValueError, match="closed"):
            closed_sd.open_child("anything")

    def test_open_for_reader_raises(self, closed_sd: SafeDir) -> None:
        with pytest.raises(ValueError, match="closed"):
            closed_sd.open_for_reader("anything")

    def test_open_subdir_raises(self, closed_sd: SafeDir) -> None:
        with pytest.raises(ValueError, match="closed"):
            closed_sd.open_subdir("anything")

    def test_scandir_raises(self, closed_sd: SafeDir) -> None:
        with pytest.raises(ValueError, match="closed"):
            list(closed_sd.scandir())

    def test_lstat_raises(self, closed_sd: SafeDir) -> None:
        with pytest.raises(ValueError, match="closed"):
            closed_sd.lstat("anything")

    def test_mkdir_raises(self, closed_sd: SafeDir) -> None:
        with pytest.raises(ValueError, match="closed"):
            closed_sd.mkdir("anything")

    def test_unlink_raises(self, closed_sd: SafeDir) -> None:
        with pytest.raises(ValueError, match="closed"):
            closed_sd.unlink("anything")

    def test_rename_into_raises_on_closed_self(self, tmp_path: Path) -> None:
        closed = SafeDir.open_root(tmp_path)
        closed.__exit__(None, None, None)
        with SafeDir.open_root(tmp_path) as live:
            with pytest.raises(ValueError, match="closed"):
                closed.rename_into("a", live, "b")

    def test_rename_into_raises_on_closed_other(self, tmp_path: Path) -> None:
        other = SafeDir.open_root(tmp_path)
        other.__exit__(None, None, None)
        with SafeDir.open_root(tmp_path) as live:
            with pytest.raises(ValueError, match="closed"):
                live.rename_into("a", other, "b")

    def test_underlying_fd_invalidated_to_neg_one(self, tmp_path: Path) -> None:
        """Defense in depth: even if ``_check_open`` is bypassed via
        direct attribute access, the stored fd is -1 so any syscall
        fails with EBADF rather than operating on a recycled fd."""
        sd = SafeDir.open_root(tmp_path)
        sd.__exit__(None, None, None)
        assert sd._fd == -1


# ---------------------------------------------------------------------------
# Error semantics: missing entries
# ---------------------------------------------------------------------------


class TestMissingEntries:
    def test_open_for_reader_missing_file_raises_filenotfound(self, tmp_path: Path) -> None:
        with SafeDir.open_root(tmp_path) as sd:
            with pytest.raises(FileNotFoundError, match="nope.txt"):
                sd.open_for_reader("nope.txt")

    def test_open_subdir_missing_raises_filenotfound(self, tmp_path: Path) -> None:
        with SafeDir.open_root(tmp_path) as sd:
            with pytest.raises(FileNotFoundError, match="nope"):
                sd.open_subdir("nope")

    def test_unlink_missing_raises_filenotfound(self, tmp_path: Path) -> None:
        with SafeDir.open_root(tmp_path) as sd:
            with pytest.raises(FileNotFoundError, match="nope"):
                sd.unlink("nope")

    def test_lstat_missing_raises_filenotfound(self, tmp_path: Path) -> None:
        with SafeDir.open_root(tmp_path) as sd:
            with pytest.raises(FileNotFoundError, match="nope"):
                sd.lstat("nope")


# ---------------------------------------------------------------------------
# T10 predicate-negative cases for the symlink rejection
# ---------------------------------------------------------------------------


class TestPredicateNegatives:
    """`test-generation-patterns.md` T10: every predicate needs a negative
    case with the same surface shape but wrong context.

    The predicate here is "is this entry a symlink that we should refuse?"
    The wrong-context cases below all look like potentially-dangerous
    operations but are in fact safe and must succeed.
    """

    def test_regular_file_named_like_symlink_not_rejected(self, tmp_path: Path) -> None:
        """A regular file whose name is "link" or "shortcut" is fine."""
        (tmp_path / "link").write_bytes(b"actually a regular file")
        with SafeDir.open_root(tmp_path) as sd:
            fd = sd.open_for_reader("link")
            try:
                assert os.read(fd, 64) == b"actually a regular file"
            finally:
                os.close(fd)

    def test_regular_directory_named_like_symlink_not_rejected(self, tmp_path: Path) -> None:
        """A regular directory at a name that *looks* like a link is fine."""
        (tmp_path / "documents_link").mkdir()
        (tmp_path / "documents_link" / "x").write_text("x")
        with SafeDir.open_root(tmp_path) as sd, sd.open_subdir("documents_link") as sub:
            assert set(sub.scandir()) == {"x"}

    def test_root_at_real_path_not_rejected(self, tmp_path: Path) -> None:
        """`open_root` on a real directory (whatever the parent has done) is fine.

        Same surface shape as `test_open_root_rejects_symlinked_root` — a
        directory at the supplied path. Wrong context: the directory is real.
        """
        real = tmp_path / "organize"
        real.mkdir()
        with SafeDir.open_root(real) as sd:
            # Verify the fd actually points at the right inode.
            assert os.fstat(sd.fd).st_ino == real.stat().st_ino
