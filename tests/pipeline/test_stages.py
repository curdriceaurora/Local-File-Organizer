"""Tests for composable pipeline stages.

Validates that each stage implements PipelineStage protocol, processes
files correctly, handles errors gracefully, and can be composed into
custom pipelines.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.interfaces.pipeline import PipelineStage, StageContext
from file_organizer.pipeline.stages.analyzer import AnalyzerStage
from file_organizer.pipeline.stages.postprocessor import PostprocessorStage
from file_organizer.pipeline.stages.preprocessor import PreprocessorStage
from file_organizer.pipeline.stages.writer import WriterStage

# ---------------------------------------------------------------------------
# StageContext
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestStageContext:
    """Test StageContext dataclass behavior."""

    def test_failed_property_false_by_default(self) -> None:
        ctx = StageContext(file_path=Path("test.txt"))
        assert ctx.failed is False

    def test_failed_property_true_when_error_set(self) -> None:
        ctx = StageContext(file_path=Path("test.txt"), error="boom")
        assert ctx.failed is True

    def test_defaults(self) -> None:
        ctx = StageContext(file_path=Path("test.txt"))
        assert ctx.metadata == {}
        assert ctx.analysis == {}
        assert ctx.destination is None
        assert ctx.category == ""
        assert ctx.filename == ""
        assert ctx.dry_run is True
        assert ctx.extra == {}

    def test_rejects_path_traversal_in_category(self) -> None:
        with pytest.raises(ValueError, match="Invalid category"):
            StageContext(file_path=Path("input/file.txt"), category="../etc")

    def test_rejects_path_traversal_in_filename(self) -> None:
        with pytest.raises(ValueError, match="Invalid filename"):
            StageContext(file_path=Path("input/file.txt"), filename="../../etc/passwd")

    def test_rejects_windows_drive_in_category(self) -> None:
        # Regression for #760: "C:" has no slash but still escapes output_dir / category
        # on Windows via PureWindowsPath.drive being non-empty.
        with pytest.raises(ValueError, match="Invalid category"):
            StageContext(file_path=Path("input/file.txt"), category="C:")

    def test_rejects_windows_drive_with_path_in_category(self) -> None:
        # Drive-qualified path without a separator also escapes containment.
        with pytest.raises(ValueError, match="Invalid category"):
            StageContext(file_path=Path("input/file.txt"), category="C:docs")

    def test_rejects_windows_drive_in_filename(self) -> None:
        with pytest.raises(ValueError, match="Invalid filename"):
            StageContext(file_path=Path("input/file.txt"), filename="C:")

    def test_rejects_windows_drive_in_filename_via_setattr(self) -> None:
        ctx = StageContext(file_path=Path("input/file.txt"))
        with pytest.raises(ValueError, match="Invalid filename"):
            ctx.filename = "C:evil"

    def test_accepts_normal_category(self) -> None:
        ctx = StageContext(file_path=Path("input/file.txt"), category="Documents")
        assert ctx.category == "Documents"

    def test_accepts_normal_filename(self) -> None:
        ctx = StageContext(file_path=Path("input/file.txt"), filename="report_2026")
        assert ctx.filename == "report_2026"


# ---------------------------------------------------------------------------
# PreprocessorStage
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPreprocessorStage:
    """Test PreprocessorStage validation and metadata extraction."""

    def test_satisfies_protocol(self) -> None:
        assert isinstance(PreprocessorStage(), PipelineStage)

    def test_name(self) -> None:
        assert PreprocessorStage().name == "preprocessor"

    def test_extracts_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world")

        ctx = StageContext(file_path=f)
        result = PreprocessorStage().process(ctx)

        assert result.error is None
        assert result.metadata["extension"] == ".txt"
        assert result.metadata["size_bytes"] == 11
        assert result.metadata["stem"] == "hello"
        assert result.filename == "hello"

    def test_file_not_found(self) -> None:
        ctx = StageContext(file_path=Path("nonexistent/file.txt"))
        result = PreprocessorStage().process(ctx)
        assert result.failed
        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_directory_rejected(self, tmp_path: Path) -> None:
        ctx = StageContext(file_path=tmp_path)
        result = PreprocessorStage().process(ctx)
        assert result.failed
        assert result.error is not None
        assert "Not a file" in result.error

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_text("data")

        stage = PreprocessorStage(supported_extensions=frozenset({".txt"}))
        ctx = StageContext(file_path=f)
        result = stage.process(ctx)
        assert result.failed
        assert result.error is not None
        assert "Unsupported" in result.error

    def test_no_extension_filter(self, tmp_path: Path) -> None:
        """When supported_extensions is None, all extensions pass."""
        f = tmp_path / "test.xyz"
        f.write_text("data")

        ctx = StageContext(file_path=f)
        result = PreprocessorStage().process(ctx)
        assert not result.failed

    def test_skips_when_already_failed(self) -> None:
        ctx = StageContext(file_path=Path("x.txt"), error="prior error")
        result = PreprocessorStage().process(ctx)
        assert result.error == "prior error"


# ---------------------------------------------------------------------------
# AnalyzerStage
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestAnalyzerStage:
    """Test AnalyzerStage routing and processor invocation."""

    def test_satisfies_protocol(self) -> None:
        assert isinstance(AnalyzerStage(), PipelineStage)

    def test_name(self) -> None:
        assert AnalyzerStage().name == "analyzer"

    def test_skips_when_no_router(self, tmp_path: Path) -> None:
        """Without a router, analyzer is a no-op."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        ctx = StageContext(file_path=f)
        result = AnalyzerStage().process(ctx)
        assert not result.failed

    def test_skips_when_context_already_failed(self, tmp_path: Path) -> None:
        ctx = StageContext(file_path=tmp_path / "x.txt", error="prior error")
        result = AnalyzerStage().process(ctx)
        assert result.error == "prior error"

    def test_processes_file_with_router_and_pool(self, tmp_path: Path) -> None:
        """When router and pool are configured, analyzer invokes processor."""
        from file_organizer.pipeline.processor_pool import ProcessorPool
        from file_organizer.pipeline.router import FileRouter

        f = tmp_path / "doc.txt"
        f.write_text("hello")

        mock_result = MagicMock()
        mock_result.folder_name = "Documents"
        mock_result.filename = "hello_doc"
        mock_result.error = None

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = mock_result

        router = FileRouter()
        pool = MagicMock(spec=ProcessorPool)
        pool.get_processor.return_value = mock_processor

        stage = AnalyzerStage(router=router, processor_pool=pool)
        ctx = StageContext(file_path=f)
        result = stage.process(ctx)

        assert not result.failed
        assert result.category == "Documents"
        assert result.filename == "hello_doc"
        mock_processor.process_file.assert_called_once_with(f)
        pool.get_processor.assert_called_once()


# ---------------------------------------------------------------------------
# PostprocessorStage
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPostprocessorStage:
    """Test PostprocessorStage path computation."""

    def test_satisfies_protocol(self) -> None:
        assert isinstance(PostprocessorStage(output_directory=Path("out")), PipelineStage)

    def test_name(self) -> None:
        assert PostprocessorStage(output_directory=Path("out")).name == "postprocessor"

    def test_builds_destination(self, tmp_path: Path) -> None:
        stage = PostprocessorStage(output_directory=tmp_path / "out")
        ctx = StageContext(
            file_path=Path("input/report.pdf"),
            category="Documents",
            filename="quarterly_report",
        )
        result = stage.process(ctx)

        assert result.destination == tmp_path / "out" / "Documents" / "quarterly_report.pdf"

    def test_defaults_to_uncategorized(self, tmp_path: Path) -> None:
        stage = PostprocessorStage(output_directory=tmp_path / "out")
        ctx = StageContext(file_path=Path("input/file.txt"))
        result = stage.process(ctx)

        assert "uncategorized" in str(result.destination)

    def test_deduplicates_existing_files(self, tmp_path: Path) -> None:
        out = tmp_path / "out" / "Docs"
        out.mkdir(parents=True)
        (out / "file.txt").write_text("existing")

        stage = PostprocessorStage(output_directory=tmp_path / "out")
        ctx = StageContext(
            file_path=Path("input/file.txt"),
            category="Docs",
            filename="file",
        )
        result = stage.process(ctx)
        assert result.destination == out / "file_1.txt"

    def test_skips_when_failed(self) -> None:
        stage = PostprocessorStage(output_directory=Path("out"))
        ctx = StageContext(file_path=Path("x.txt"), error="prior")
        result = stage.process(ctx)
        assert result.destination is None

    def test_sets_output_root_for_anchored_writer(self, tmp_path: Path) -> None:
        """The postprocessor declares the trusted output root so the writer can
        anchor its copy and refuse a symlinked ancestor (#1268). The computed
        destination must live under that root.
        """
        out = tmp_path / "out"
        stage = PostprocessorStage(output_directory=out)
        ctx = StageContext(
            file_path=Path("input/report.pdf"),
            category="Documents",
            filename="q3",
        )
        result = stage.process(ctx)

        assert result.output_root == out
        assert result.destination is not None
        # destination is reachable as a relative path under output_root
        assert result.destination.relative_to(result.output_root) == Path("Documents/q3.pdf")


# ---------------------------------------------------------------------------
# _copy_fd_xattrs (best-effort xattr copy error branches)
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestCopyFdXattrs:
    """Branch coverage for the best-effort xattr helper (no real FS needed)."""

    def test_noop_when_listxattr_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from file_organizer.pipeline.stages import writer as w

        monkeypatch.delattr(w.os, "listxattr", raising=False)
        w._copy_fd_xattrs(0, 1)  # returns early, no syscalls

    def test_listxattr_unsupported_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import errno as _errno

        from file_organizer.pipeline.stages import writer as w

        def _raise(_fd: int) -> list[str]:
            raise OSError(_errno.ENOTSUP, "unsupported")

        monkeypatch.setattr(w.os, "listxattr", _raise, raising=False)
        w._copy_fd_xattrs(0, 1)  # swallowed, no raise

    def test_listxattr_other_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import errno as _errno

        from file_organizer.pipeline.stages import writer as w

        def _raise(_fd: int) -> list[str]:
            raise OSError(_errno.EIO, "io error")

        monkeypatch.setattr(w.os, "listxattr", _raise, raising=False)
        with pytest.raises(OSError, match="io error"):
            w._copy_fd_xattrs(0, 1)

    def test_setxattr_permission_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import errno as _errno

        from file_organizer.pipeline.stages import writer as w

        monkeypatch.setattr(w.os, "listxattr", lambda _fd: ["user.x"], raising=False)
        monkeypatch.setattr(w.os, "getxattr", lambda _fd, _name: b"v", raising=False)

        def _raise(_fd: int, _name: str, _value: bytes) -> None:
            raise OSError(_errno.EPERM, "denied")

        monkeypatch.setattr(w.os, "setxattr", _raise, raising=False)
        w._copy_fd_xattrs(0, 1)  # swallowed

    def test_setxattr_other_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import errno as _errno

        from file_organizer.pipeline.stages import writer as w

        monkeypatch.setattr(w.os, "listxattr", lambda _fd: ["user.x"], raising=False)
        monkeypatch.setattr(w.os, "getxattr", lambda _fd, _name: b"v", raising=False)

        def _raise(_fd: int, _name: str, _value: bytes) -> None:
            raise OSError(_errno.EIO, "io error")

        monkeypatch.setattr(w.os, "setxattr", _raise, raising=False)
        with pytest.raises(OSError, match="io error"):
            w._copy_fd_xattrs(0, 1)


# ---------------------------------------------------------------------------
# WriterStage
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
@pytest.mark.integration
class TestWriterStage:
    """Test WriterStage file copy operations.

    Marked ``integration`` as well as ``unit``: these exercise the real
    SafeDir filesystem copy path, so they carry ``writer.py``'s integration
    coverage floor (the push-to-main Integration coverage gate measures only
    ``-m integration``).
    """

    def test_satisfies_protocol(self) -> None:
        assert isinstance(WriterStage(), PipelineStage)

    def test_name(self) -> None:
        assert WriterStage().name == "writer"

    def test_copies_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("content")

        dest = tmp_path / "dest" / "Docs" / "file.txt"
        ctx = StageContext(
            file_path=src,
            destination=dest,
            dry_run=False,
        )
        result = WriterStage().process(ctx)
        assert not result.failed
        assert dest.exists()
        assert dest.read_text() == "content"

    def test_dry_run_no_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "file.txt"
        src.write_text("content")
        dest = tmp_path / "out" / "file.txt"

        ctx = StageContext(file_path=src, destination=dest, dry_run=True)
        result = WriterStage().process(ctx)
        assert not result.failed
        assert not dest.exists()

    def test_error_when_no_destination(self) -> None:
        ctx = StageContext(file_path=Path("x.txt"), dry_run=False)
        result = WriterStage().process(ctx)
        assert result.failed
        assert result.error is not None
        assert "destination" in result.error.lower()

    def test_skips_when_already_failed(self) -> None:
        ctx = StageContext(
            file_path=Path("x.txt"),
            destination=Path("out/x.txt"),
            error="prior",
            dry_run=False,
        )
        result = WriterStage().process(ctx)
        assert result.error == "prior"


# ---------------------------------------------------------------------------
# WriterStage — anchored-traversal hardening (#1268)
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
@pytest.mark.integration
@pytest.mark.skipif(sys.platform == "win32", reason="SafeDir anchored write is POSIX-only")
class TestWriterStageAnchored:
    """When ``context.output_root`` is set, the writer descends from it
    component-by-component so a symlinked *ancestor* directory in the output
    tree is refused rather than traversed (#1268).
    """

    def _src(self, tmp_path: Path, content: bytes = b"payload") -> Path:
        src = tmp_path / "input" / "file.txt"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(content)
        return src

    def test_anchored_creates_nested_destination(self, tmp_path: Path) -> None:
        """Normal nested destinations are created under the trusted root."""
        src = self._src(tmp_path, b"hello")
        out_root = tmp_path / "out"
        out_root.mkdir()
        dest = out_root / "Docs" / "2026" / "file.txt"
        ctx = StageContext(file_path=src, destination=dest, output_root=out_root, dry_run=False)
        result = WriterStage().process(ctx)
        assert not result.failed, result.error
        assert dest.read_bytes() == b"hello"

    def test_anchored_refuses_symlinked_ancestor(self, tmp_path: Path) -> None:
        """The headline #1268 guard: a symlinked intermediate output directory
        is refused (SymlinkRejected → OSError → file marked failed) instead of
        redirecting the write outside the output tree.
        """
        src = self._src(tmp_path, b"do-not-leak")
        outside = tmp_path / "outside"
        outside.mkdir()
        out_root = tmp_path / "out"
        out_root.mkdir()
        # Attacker swaps the category dir for a symlink pointing outside.
        (out_root / "Docs").symlink_to(outside, target_is_directory=True)
        dest = out_root / "Docs" / "file.txt"
        ctx = StageContext(file_path=src, destination=dest, output_root=out_root, dry_run=False)
        result = WriterStage().process(ctx)

        assert result.failed
        # Nothing was written through the symlink into the outside tree.
        assert list(outside.iterdir()) == []

    def test_anchored_refuses_symlinked_leaf(self, tmp_path: Path) -> None:
        """A symlink pre-planted at the leaf is also refused (parity)."""
        src = self._src(tmp_path, b"data")
        honey = tmp_path / "honey"
        honey.write_bytes(b"secret")
        out_root = tmp_path / "out"
        (out_root / "Docs").mkdir(parents=True)
        (out_root / "Docs" / "file.txt").symlink_to(honey)
        dest = out_root / "Docs" / "file.txt"
        ctx = StageContext(file_path=src, destination=dest, output_root=out_root, dry_run=False)
        result = WriterStage().process(ctx)

        assert result.failed
        # The symlink target is untouched (not truncated/overwritten).
        assert honey.read_bytes() == b"secret"

    def test_falls_back_when_destination_outside_output_root(self, tmp_path: Path) -> None:
        """If ``destination`` is not under ``output_root`` (mismatched custom
        wiring), the writer uses the parent-rooted fallback rather than failing —
        the copy still succeeds with leaf protection.
        """
        src = self._src(tmp_path, b"fallback")
        out_root = tmp_path / "declared_root"
        out_root.mkdir()
        dest = tmp_path / "elsewhere" / "file.txt"  # NOT under out_root
        ctx = StageContext(file_path=src, destination=dest, output_root=out_root, dry_run=False)
        result = WriterStage().process(ctx)
        assert not result.failed, result.error
        assert dest.read_bytes() == b"fallback"

    def test_symlinked_output_root_is_honored(self, tmp_path: Path) -> None:
        """A legitimately symlinked output *root* (e.g. ``~/Organized -> /mnt/...``)
        must be followed, not refused: the root is the trusted, user-supplied
        anchor. Only attacker-influenced segments *below* it are O_NOFOLLOW-walked.
        Regression guard for the anchored path rejecting symlinked roots.
        """
        src = self._src(tmp_path, b"via-symlink-root")
        real_root = tmp_path / "real_storage"
        real_root.mkdir()
        out_root = tmp_path / "Organized"  # symlink -> real_storage
        out_root.symlink_to(real_root, target_is_directory=True)
        dest = out_root / "Docs" / "file.txt"
        ctx = StageContext(file_path=src, destination=dest, output_root=out_root, dry_run=False)
        result = WriterStage().process(ctx)
        assert not result.failed, result.error
        # Written through the symlinked root into the real storage tree.
        assert (real_root / "Docs" / "file.txt").read_bytes() == b"via-symlink-root"

    def test_metadata_parity_with_copy2(self, tmp_path: Path) -> None:
        """The anchored path replicates copy2's mode bits (no execute leak)."""
        src = self._src(tmp_path, b"x")
        os.chmod(src, 0o600)
        out_root = tmp_path / "out"
        out_root.mkdir()
        dest = out_root / "Docs" / "file.txt"
        ctx = StageContext(file_path=src, destination=dest, output_root=out_root, dry_run=False)
        result = WriterStage().process(ctx)
        assert not result.failed, result.error
        assert stat.S_IMODE(dest.stat().st_mode) == 0o600

    def test_preserves_mode_and_mtime(self, tmp_path: Path) -> None:
        """The hardened copy replicates copy2's mode + atime/mtime via fd ops."""
        src = tmp_path / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("content")
        os.chmod(src, 0o640)
        os.utime(src, (1_000_000, 1_234_567))

        dest = tmp_path / "dest" / "Docs" / "file.txt"
        ctx = StageContext(file_path=src, destination=dest, dry_run=False)
        result = WriterStage().process(ctx)

        assert not result.failed
        # Stat both before reading dest content (read_text would bump dest
        # atime, masking the atime-parity assertion below).
        dest_stat = dest.stat()
        src_stat = src.stat()
        if sys.platform != "win32":
            assert stat.S_IMODE(dest_stat.st_mode) == 0o640
            # copy2 copies the source's *post-read* atime; the helper re-fstats
            # the source after the read, so dest atime matches src atime.
            assert dest_stat.st_atime_ns == src_stat.st_atime_ns
        assert dest_stat.st_mtime == src_stat.st_mtime
        assert dest.read_text() == "content"

    @pytest.mark.skipif(sys.platform == "win32", reason="xattrs are POSIX-only")
    def test_preserves_user_xattrs(self, tmp_path: Path) -> None:
        """Extended attributes are copied (copy2/copystat parity, #1266)."""
        if not hasattr(os, "setxattr"):
            pytest.skip("xattrs unavailable on this platform")
        src = tmp_path / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("content")
        try:
            os.setxattr(src, "user.fo_test", b"keepme")
        except OSError:
            pytest.skip("filesystem does not support user xattrs")

        dest = tmp_path / "dest" / "file.txt"
        ctx = StageContext(file_path=src, destination=dest, dry_run=False)
        result = WriterStage().process(ctx)

        assert not result.failed
        assert os.getxattr(dest, "user.fo_test") == b"keepme"

    def test_overwrites_existing_regular_file(self, tmp_path: Path) -> None:
        """An existing regular destination is overwritten (copy2 parity)."""
        src = tmp_path / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("new content")
        dest = tmp_path / "dest" / "file.txt"
        dest.parent.mkdir()
        dest.write_text("old content")

        ctx = StageContext(file_path=src, destination=dest, dry_run=False)
        result = WriterStage().process(ctx)

        assert not result.failed
        assert dest.read_text() == "new content"

    @pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
    def test_refuses_symlinked_destination(self, tmp_path: Path) -> None:
        """A symlink pre-planted at the destination is refused, not followed:
        the attacker's target file must be left untouched (#322)."""
        src = tmp_path / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("payload")

        victim = tmp_path / "victim.txt"
        victim.write_text("secret")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        dest = dest_dir / "file.txt"
        try:
            dest.symlink_to(victim)
        except OSError:
            pytest.skip("symlink creation not supported")

        ctx = StageContext(file_path=src, destination=dest, dry_run=False)
        result = WriterStage().process(ctx)

        assert result.failed
        assert result.error is not None
        # The symlink target must NOT have been overwritten through the link.
        assert victim.read_text() == "secret"

    @pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
    def test_same_inode_copy_is_refused(self, tmp_path: Path) -> None:
        """A destination that is the same inode as the source (here a hard
        link) must be refused, not truncated-then-copied into a zero-byte
        file. Matches shutil.copy2's SameFileError (#1266 Codex P1)."""
        src = tmp_path / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("important content")
        dest = tmp_path / "dest" / "file.txt"
        dest.parent.mkdir()
        try:
            os.link(src, dest)  # hard link → same inode as source
        except OSError:
            pytest.skip("hard links not supported")

        ctx = StageContext(file_path=src, destination=dest, dry_run=False)
        result = WriterStage().process(ctx)

        assert result.failed
        # Source content must be intact (not truncated to zero bytes).
        assert src.read_text() == "important content"

    @pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
    def test_refuses_fifo_source(self, tmp_path: Path) -> None:
        """A source swapped to a FIFO is refused (SpecialFileError) instead of
        blocking the worker on a reader-less open (#1266 Codex P2)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        src = src_dir / "pipe"
        try:
            os.mkfifo(src)
        except (AttributeError, OSError):
            pytest.skip("FIFOs not supported")

        dest = tmp_path / "dest" / "pipe"
        ctx = StageContext(file_path=src, destination=dest, dry_run=False)
        result = WriterStage().process(ctx)

        assert result.failed
        assert not dest.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
    def test_refuses_fifo_destination(self, tmp_path: Path) -> None:
        """An existing FIFO destination is refused instead of blocking the
        worker on a reader-less O_WRONLY open (#1266 Codex P2)."""
        src = tmp_path / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("content")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        dest = dest_dir / "pipe"
        try:
            os.mkfifo(dest)
        except (AttributeError, OSError):
            pytest.skip("FIFOs not supported")

        ctx = StageContext(file_path=src, destination=dest, dry_run=False)
        result = WriterStage().process(ctx)

        assert result.failed

    @pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
    def test_refuses_symlinked_source(self, tmp_path: Path) -> None:
        """A symlinked source is refused rather than dereferenced into the
        output tree (#354)."""
        real = tmp_path / "real.txt"
        real.write_text("attacker secret")
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        src = src_dir / "file.txt"
        try:
            src.symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported")

        dest = tmp_path / "dest" / "file.txt"
        ctx = StageContext(file_path=src, destination=dest, dry_run=False)
        result = WriterStage().process(ctx)

        assert result.failed
        assert not dest.exists()


# ---------------------------------------------------------------------------
# Composition tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPipelineComposition:
    """Test composing stages into custom pipelines."""

    def test_preprocessor_plus_writer_skipping_analyzer(self, tmp_path: Path) -> None:
        """Custom pipeline with only preprocessor + postprocessor + writer."""
        src = tmp_path / "input" / "file.txt"
        src.parent.mkdir()
        src.write_text("hello")

        out = tmp_path / "output"
        stages: list[PipelineStage] = [
            PreprocessorStage(),
            PostprocessorStage(output_directory=out),
            WriterStage(),
        ]

        ctx = StageContext(file_path=src, dry_run=False, category="Quick")
        for stage in stages:
            ctx = stage.process(ctx)

        assert not ctx.failed
        assert ctx.destination is not None
        assert ctx.destination.exists()
        assert ctx.destination.read_text() == "hello"

    def test_custom_stage_without_orchestrator_changes(self, tmp_path: Path) -> None:
        """Adding a custom stage doesn't require orchestrator changes."""

        class UppercaseStage:
            @property
            def name(self) -> str:
                return "uppercase"

            def process(self, context: StageContext) -> StageContext:
                context.filename = context.filename.upper()
                return context

        assert isinstance(UppercaseStage(), PipelineStage)

        src = tmp_path / "report.txt"
        src.write_text("data")

        stages: list[PipelineStage] = [
            PreprocessorStage(),
            UppercaseStage(),
            PostprocessorStage(output_directory=tmp_path / "out"),
        ]

        ctx = StageContext(file_path=src, category="Docs")
        for stage in stages:
            ctx = stage.process(ctx)

        assert ctx.filename == "REPORT"
        assert "REPORT" in str(ctx.destination)

    def test_orchestrator_with_stages(self, tmp_path: Path) -> None:
        """PipelineOrchestrator delegates to stages when configured."""
        from file_organizer.pipeline.config import PipelineConfig
        from file_organizer.pipeline.orchestrator import PipelineOrchestrator

        src = tmp_path / "file.txt"
        src.write_text("hello")

        config = PipelineConfig(
            output_directory=tmp_path / "out",
            dry_run=True,
        )

        pipeline = PipelineOrchestrator(
            config,
            stages=[
                PreprocessorStage(),
                PostprocessorStage(output_directory=config.output_directory),
                WriterStage(),
            ],
        )

        result = pipeline.process_file(src)
        assert result.success
        assert result.destination is not None
        assert result.dry_run is True

    def test_error_propagation_through_stages(self) -> None:
        """Error in early stage propagates; later stages skip."""
        stages: list[PipelineStage] = [
            PreprocessorStage(),
            AnalyzerStage(),
            PostprocessorStage(output_directory=Path("out")),
            WriterStage(),
        ]

        ctx = StageContext(file_path=Path("nonexistent.txt"))
        for stage in stages:
            ctx = stage.process(ctx)

        assert ctx.failed
        assert ctx.destination is None  # postprocessor skipped
