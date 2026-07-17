"""Tests for Core Organizer logic.

After the God Object decomposition, tests are organized by module:
- FileOrganizer facade (public API)
- file_ops (collect, organize, simulate, fallback, cleanup)
- display (Rich UI helpers)
- initializer (processor startup)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import build_plan_from_processed
from file_organizer.core.types import OrganizationResult
from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.services.text_processor import ProcessedFile
from file_organizer.services.vision_processor import ProcessedImage

# Organizer flow tests exercise real filesystem operations through the
# facade; also counted for the integration coverage gate so the plan-based
# live-execution paths added for #1504 keep core/organizer.py above its
# integration floor.
pytestmark = pytest.mark.ci


@pytest.fixture
def text_config() -> ModelConfig:
    return ModelConfig(name="test-text", model_type=ModelType.TEXT)


@pytest.fixture
def vision_config() -> ModelConfig:
    return ModelConfig(name="test-vision", model_type=ModelType.VISION)


@pytest.fixture
def organizer(text_config: ModelConfig, vision_config: ModelConfig) -> FileOrganizer:
    """FileOrganizer instance configured for testing."""
    return FileOrganizer(
        text_model_config=text_config,
        vision_model_config=vision_config,
        dry_run=True,
        use_hardlinks=False,
    )


# ---------------------------------------------------------------------------
# FileOrganizer facade tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestFileOrganizer:
    """Tests for FileOrganizer class."""

    def test_init(self, text_config: ModelConfig, vision_config: ModelConfig) -> None:
        """Test default and custom initialization."""
        with patch(
            "file_organizer.config.provider_env.get_model_configs",
            return_value=(
                ModelConfig(name="qwen2.5:3b-instruct-q4_K_M", model_type=ModelType.TEXT),
                ModelConfig(name="qwen2.5vl:7b-q4_K_M", model_type=ModelType.VISION),
            ),
        ):
            org = FileOrganizer()
        assert org.text_model_config.name == "qwen2.5:3b-instruct-q4_K_M"
        assert org.dry_run is True

        org = FileOrganizer(
            text_model_config=text_config,
            vision_model_config=vision_config,
            dry_run=False,
            use_hardlinks=True,
            parallel_workers=2,
            prefetch_depth=3,
        )
        assert org.text_model_config == text_config
        assert org.dry_run is False
        assert org.use_hardlinks is True
        assert org.parallel_config.max_workers == 2
        assert org.parallel_config.prefetch_depth == 3

        no_prefetch_org = FileOrganizer(
            text_model_config=text_config,
            vision_model_config=vision_config,
            no_prefetch=True,
            prefetch_depth=5,
        )
        assert no_prefetch_org.parallel_config.prefetch_depth == 0

        # Backward-compat positional shape: (..., parallel_workers, no_prefetch)
        legacy_positional = FileOrganizer(
            text_config,
            vision_config,
            True,
            True,
            None,
            True,
        )
        assert legacy_positional.no_prefetch is True
        assert legacy_positional.prefetch_depth == 0

    def test_organize_input_missing(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        """Test organizing fails when input path does not exist."""
        with pytest.raises(ValueError, match="Input path does not exist"):
            organizer.organize(tmp_path / "missing", tmp_path / "out")

    @patch("file_organizer.core.file_ops.collect_files")
    def test_organize_empty_directory(
        self, mock_collect: MagicMock, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """Test organizing an empty directory returns early."""
        mock_collect.return_value = []

        result = organizer.organize(tmp_path, tmp_path / "out")

        mock_collect.assert_called_once()
        assert result.total_files == 0

    def test_process_audio_files_falls_back_when_audio_extra_missing(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """When transcription is requested but faster-whisper is unavailable,
        organizer should warn and fall back to metadata-only processing.
        """
        organizer.transcribe_audio = True
        audio = tmp_path / "clip.mp3"
        audio.write_bytes(b"fake audio bytes")

        with (
            patch("file_organizer.services.audio.transcriber._FASTER_WHISPER_AVAILABLE", False),
            patch("file_organizer.core.organizer.dispatcher.process_audio_files") as mock_proc,
            patch.object(organizer.console, "print") as mock_print,
        ):
            organizer._process_audio_files([audio])

        assert mock_proc.call_args.kwargs["transcriber"] is None
        mock_print.assert_called_once()

    @patch("file_organizer.core.organizer.dispatcher.process_text_files")
    @patch("file_organizer.core.file_ops.collect_files")
    def test_single_file_input_anchors_scan_root_at_parent(
        self,
        mock_collect: MagicMock,
        mock_dispatch: MagicMock,
        organizer: FileOrganizer,
        tmp_path: Path,
    ) -> None:
        """A single-file ``input_path`` must anchor SafeDir reads at its parent
        directory, not the file itself (``SafeDir.open_root`` needs a directory;
        passing the file would raise ENOTDIR). Regression for PR #1259 review.
        """
        doc = tmp_path / "notes.txt"
        doc.write_text("hi")
        mock_collect.return_value = [doc]
        mock_dispatch.return_value = []

        def _fake_init() -> None:
            tp = MagicMock()
            tp.text_model.is_initialized = True
            organizer.text_processor = tp

        with patch.object(organizer, "_init_text_processor", side_effect=_fake_init):
            organizer.organize(doc, tmp_path / "out")

        assert mock_dispatch.call_args.kwargs["scan_root"] == tmp_path

    def test_extension_classvars_are_sets(self, organizer: FileOrganizer) -> None:
        """Verify extension ClassVars are backward-compatible sets."""
        assert isinstance(FileOrganizer.TEXT_EXTENSIONS, set)
        assert ".pdf" in FileOrganizer.TEXT_EXTENSIONS
        assert ".jpg" in FileOrganizer.IMAGE_EXTENSIONS
        assert ".mp4" in FileOrganizer.VIDEO_EXTENSIONS
        assert ".mp3" in FileOrganizer.AUDIO_EXTENSIONS
        assert ".dwg" in FileOrganizer.CAD_EXTENSIONS

    def test_no_vision_uses_extension_fallback_for_images(self, tmp_path: Path) -> None:
        """When vision is disabled, image files should route through fallback."""
        src = tmp_path / "src"
        src.mkdir()
        image = src / "photo.jpg"
        image.write_bytes(b"\xff\xd8\xff\xe0")

        out = tmp_path / "out"
        organizer = FileOrganizer(dry_run=True, enable_vision=False)

        with (
            patch.object(
                organizer,
                "_fallback_by_extension",
                wraps=organizer._fallback_by_extension,
            ) as mock_fallback,
            patch.object(organizer, "_process_image_files") as mock_process_images,
        ):
            result = organizer.organize(src, out)

        assert result.failed_files == 0
        mock_process_images.assert_not_called()
        mock_fallback.assert_called_once()
        assert mock_fallback.call_args.args[0] == [image]

    def test_build_plan_forces_dry_run_and_restores_original_setting(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """Preview planning should not permanently mutate the organizer mode."""
        source = tmp_path / "notes.txt"
        source.write_text("hello")
        plan = build_plan_from_processed(
            input_path=tmp_path,
            output_path=tmp_path / "out",
            processed=[
                ProcessedFile(
                    file_path=source,
                    description="Categorized into Docs",
                    folder_name="Docs",
                    filename=source.stem,
                )
            ],
            skip_existing=True,
            use_hardlinks=False,
            total_files=1,
            skipped_files=0,
            deduplicated_files=0,
        )
        result = OrganizationResult(
            total_files=1,
            processed_files=1,
            organized_structure={"Docs": ["notes.txt"]},
            plan=plan,
        )
        organizer.dry_run = False

        with patch.object(organizer, "organize", return_value=result) as mock_organize:
            assert organizer.build_plan(tmp_path, tmp_path / "out", skip_existing=False) == plan

        assert organizer.dry_run is False
        mock_organize.assert_called_once_with(tmp_path, tmp_path / "out", skip_existing=False)

    def test_build_plan_restores_mode_when_preview_fails(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """Preview errors should leave the facade reusable in its original mode."""
        organizer.dry_run = False

        with (
            patch.object(organizer, "organize", side_effect=RuntimeError("preview failed")),
            pytest.raises(RuntimeError, match="preview failed"),
        ):
            organizer.build_plan(tmp_path, tmp_path / "out")

        assert organizer.dry_run is False

    def test_execute_plan_builds_result_from_exact_plan(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """Executing a reviewed plan should report the exact plan outcome."""
        source = tmp_path / "notes.txt"
        source.write_text("hello")
        plan = build_plan_from_processed(
            input_path=tmp_path,
            output_path=tmp_path / "out",
            processed=[
                ProcessedFile(
                    file_path=source,
                    description="Categorized into Docs",
                    folder_name="Docs",
                    filename=source.stem,
                )
            ],
            skip_existing=True,
            use_hardlinks=False,
            total_files=1,
            skipped_files=0,
            deduplicated_files=0,
        )

        with (
            patch(
                "file_organizer.core.organizer.execute_plan",
                return_value=({}, "txn-1", [(str(source), "copy failed")]),
            ) as mock_execute,
            patch("file_organizer.core.organizer.display.show_summary") as mock_summary,
        ):
            result = organizer.execute_plan(plan)

        assert result.total_files == 1
        assert result.processed_files == 0
        assert result.failed_files == 1
        assert result.organized_structure == {}
        assert result.errors == [(str(source), "copy failed")]
        assert result.plan == plan
        assert organizer._last_transaction_id == "txn-1"
        assert organizer._last_output_path == tmp_path / "out"
        mock_execute.assert_called_once()
        mock_summary.assert_called_once()


# ---------------------------------------------------------------------------
# file_ops module tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestFileOps:
    """Tests for core.file_ops module."""

    def test_collect_files(self, tmp_path: Path) -> None:
        """Test scanning files in a directory hierarchy."""
        from file_organizer.core.file_ops import collect_files

        (tmp_path / "file1.txt").touch()
        (tmp_path / ".hidden.txt").touch()
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file2.jpg").touch()

        console = MagicMock()
        files = collect_files(tmp_path, console)

        assert len(files) == 2
        names = {f.name for f in files}
        assert "file1.txt" in names
        assert "file2.jpg" in names
        assert ".hidden.txt" not in names

    def test_collect_files_skips_symlinks(self, tmp_path: Path) -> None:
        """A symlinked file in the scan tree (e.g. pointing outside the root)
        must not be collected — closing the symlink-exfiltration surface in the
        organize pipeline (fo-core#270, WP-2.2)."""
        import sys

        from file_organizer.core.file_ops import collect_files

        src = tmp_path / "src"
        src.mkdir()
        (src / "real.txt").write_text("real")
        outside = tmp_path / "secret.txt"
        outside.write_text("attacker secret")
        try:
            (src / "link.txt").symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation not supported")
        if sys.platform == "win32":
            pytest.skip("symlink filtering is POSIX-focused")

        files = collect_files(src, MagicMock())
        names = {f.name for f in files}
        assert "real.txt" in names
        assert "link.txt" not in names

    def test_collect_files_rejects_symlinked_input(self, tmp_path: Path) -> None:
        """A symlink passed directly as the input path must not be collected:
        ``is_file()`` follows symlinks, so without an explicit guard the leaf
        would be copied (exfiltrating its target) downstream (fo-core#270)."""
        import sys

        from file_organizer.core.file_ops import collect_files

        outside = tmp_path / "secret.txt"
        outside.write_text("attacker secret")
        link = tmp_path / "input_link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation not supported")
        if sys.platform == "win32":
            pytest.skip("symlink filtering is POSIX-focused")

        files = collect_files(link, MagicMock())
        assert files == []

    def test_collect_files_rejects_symlinked_directory_input(self, tmp_path: Path) -> None:
        """A directory symlink passed as the scan root must not enumerate its
        target tree through ``safe_walk``'s default symlink guard."""
        import sys

        from file_organizer.core.file_ops import collect_files

        if sys.platform == "win32":
            pytest.skip("symlink filtering is POSIX-focused")

        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("attacker secret")
        linked_root = tmp_path / "linked_root"
        try:
            linked_root.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")

        files = collect_files(linked_root, MagicMock())
        assert files == []

    def test_simulate_organization(self, tmp_path: Path) -> None:
        """Test simulation builds output structure without creating files."""
        from file_organizer.core.file_ops import simulate_organization

        p1 = ProcessedFile(tmp_path / "f1.txt", "", "docs", "file_1")
        p2 = ProcessedFile(tmp_path / "f2.txt", "", "docs", "file_2")
        p3 = ProcessedImage(tmp_path / "i1.jpg", "", "images", "img_1")
        err = ProcessedFile(tmp_path / "e.txt", "", "errs", "e", error="fail")

        out_path = tmp_path / "out"
        structure = simulate_organization([p1, p2, p3, err], out_path)

        assert structure == {"docs": ["file_1.txt", "file_2.txt"], "images": ["img_1.jpg"]}
        assert not out_path.exists()

    @patch("file_organizer.core.file_ops.safe_copy2")
    def test_organize_files_copy(self, mock_copy: MagicMock, tmp_path: Path) -> None:
        """Test physical file copy organization."""
        from file_organizer.core.file_ops import organize_files

        out_path = tmp_path / "out"
        f1 = tmp_path / "f1.txt"

        proc = ProcessedFile(f1, "", "docs", "file_1")

        structure = organize_files(
            [proc],
            out_path,
            skip_existing=True,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )

        assert structure == {"docs": ["file_1.txt"]}
        mock_copy.assert_called_once_with(f1, out_path / "docs" / "file_1.txt", out_path)
        assert (out_path / "docs").is_dir()

    @patch("file_organizer.core.file_ops.os.link")
    def test_organize_files_hardlink(self, mock_link: MagicMock, tmp_path: Path) -> None:
        """Test physical file hardlink organization."""
        from file_organizer.core.file_ops import organize_files

        out_path = tmp_path / "out"
        f1 = tmp_path / "f1.txt"

        proc = ProcessedFile(f1, "", "docs", "file_1")

        structure = organize_files(
            [proc],
            out_path,
            skip_existing=True,
            use_hardlinks=True,
            undo_manager=None,
            transaction_id=None,
        )

        assert structure == {"docs": ["file_1.txt"]}
        mock_link.assert_called_once_with(f1, out_path / "docs" / "file_1.txt")

    @patch("file_organizer.core.file_ops.safe_copy2")
    def test_organize_files_collision(self, mock_copy: MagicMock, tmp_path: Path) -> None:
        """Test handling of identical filenames during copy."""
        from file_organizer.core.file_ops import organize_files

        out_path = tmp_path / "out"
        docs_dir = out_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "file_1.txt").touch()

        f1 = tmp_path / "f1.txt"
        proc = ProcessedFile(f1, "", "docs", "file_1")

        structure = organize_files(
            [proc],
            out_path,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )

        assert structure == {"docs": ["file_1_1.txt"]}
        mock_copy.assert_called_once_with(f1, out_path / "docs" / "file_1_1.txt", out_path)

    @pytest.mark.skipif(sys.platform == "win32", reason="SafeDir copy hardening is POSIX-only")
    def test_organize_files_refuses_dangling_symlink_destination(self, tmp_path: Path) -> None:
        """A symlink planted at the destination leaf is not followed."""
        from file_organizer.core.file_ops import organize_files

        src = tmp_path / "input.txt"
        src.write_text("payload")
        out_path = tmp_path / "out"
        docs = out_path / "docs"
        docs.mkdir(parents=True)
        escaped = tmp_path / "escaped.txt"
        try:
            (docs / "file_1.txt").symlink_to(escaped)
        except OSError:
            pytest.skip("symlink creation not supported")

        structure = organize_files(
            [ProcessedFile(src, "", "docs", "file_1")],
            out_path,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )

        assert structure == {}
        assert not escaped.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="SafeDir copy hardening is POSIX-only")
    def test_organize_files_refuses_symlinked_ancestor(self, tmp_path: Path) -> None:
        """A symlinked output subdirectory is refused instead of traversed."""
        from file_organizer.core.file_ops import organize_files

        src = tmp_path / "input.txt"
        src.write_text("payload")
        out_path = tmp_path / "out"
        outside = tmp_path / "outside"
        outside.mkdir()
        out_path.mkdir()
        try:
            (out_path / "docs").symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")

        structure = organize_files(
            [ProcessedFile(src, "", "docs", "file_1")],
            out_path,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )

        assert structure == {}
        assert list(outside.iterdir()) == []

    @pytest.mark.skipif(sys.platform == "win32", reason="SafeDir copy hardening is POSIX-only")
    def test_organize_files_refuses_symlinked_source(self, tmp_path: Path) -> None:
        """A symlinked source is refused instead of dereferenced."""
        from file_organizer.core.file_ops import organize_files

        real = tmp_path / "real.txt"
        real.write_text("secret")
        src = tmp_path / "input.txt"
        try:
            src.symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported")
        out_path = tmp_path / "out"

        structure = organize_files(
            [ProcessedFile(src, "", "docs", "file_1")],
            out_path,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )

        assert structure == {}
        assert not (out_path / "docs" / "file_1.txt").exists()

    def test_fallback_by_extension(self, tmp_path: Path) -> None:
        """Test extension-based fallback organization."""
        from file_organizer.core.file_ops import fallback_by_extension

        files = [tmp_path / "doc.pdf", tmp_path / "sheet.xlsx"]
        results = fallback_by_extension(files)

        assert len(results) == 2
        assert results[0].folder_name == "PDFs"
        assert results[1].folder_name == "Spreadsheets"

    def test_cleanup_empty_dirs(self, tmp_path: Path) -> None:
        """Test empty directory cleanup removes only empty subdirs."""
        from file_organizer.core.file_ops import cleanup_empty_dirs

        (tmp_path / "empty_sub").mkdir()
        (tmp_path / "non_empty_sub").mkdir()
        (tmp_path / "non_empty_sub" / "file.txt").touch()

        cleanup_empty_dirs(tmp_path)

        assert not (tmp_path / "empty_sub").exists()
        assert (tmp_path / "non_empty_sub").exists()
        assert tmp_path.exists()  # Root preserved

    def test_cleanup_empty_dirs_removes_hidden(self, tmp_path: Path) -> None:
        """Empty dot-prefixed dirs are still removed (safe_walk include_hidden):
        cleanup's contract is to remove *all* empty dirs below root (#1263)."""
        from file_organizer.core.file_ops import cleanup_empty_dirs

        (tmp_path / ".empty_hidden").mkdir()

        cleanup_empty_dirs(tmp_path)

        assert not (tmp_path / ".empty_hidden").exists()

    def test_cleanup_empty_dirs_skips_symlinked_directories(self, tmp_path: Path) -> None:
        """Cleanup must not traverse or remove a directory symlink entry."""
        import sys

        from file_organizer.core.file_ops import cleanup_empty_dirs

        if sys.platform == "win32":
            pytest.skip("symlink filtering is POSIX-focused")

        outside = tmp_path.parent / f"{tmp_path.name}-outside"
        outside.mkdir()
        linked_dir = tmp_path / "linked_dir"
        try:
            linked_dir.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not supported")

        cleanup_empty_dirs(tmp_path)

        assert linked_dir.exists()
        assert linked_dir.is_symlink()
        assert outside.exists()


# ---------------------------------------------------------------------------
# display module tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestDisplay:
    """Tests for core.display module."""

    def test_show_file_breakdown_renders_table(self, tmp_path: Path) -> None:
        """Ensure show_file_breakdown renders a Rich Table."""
        from rich.table import Table

        from file_organizer.core.display import show_file_breakdown

        console = MagicMock()
        show_file_breakdown(
            console,
            text_files=[tmp_path],
            image_files=[tmp_path],
            video_files=[tmp_path],
            audio_files=[tmp_path],
            cad_files=[tmp_path],
            other_files=[tmp_path],
        )
        console.print.assert_called_once()
        printed_arg = console.print.call_args[0][0]
        assert isinstance(printed_arg, Table)

    def test_show_summary_does_not_crash(self, tmp_path: Path) -> None:
        """Ensure show_summary renders statistics output."""
        from file_organizer.core.display import show_summary

        console = MagicMock()
        res = OrganizationResult(total_files=5, processing_time=1.0)
        show_summary(console, res, tmp_path, dry_run=True)
        # Should print multiple lines of summary stats
        assert console.print.call_count >= 2

    def test_show_summary_surfaces_deduplicated_count(self, tmp_path: Path) -> None:
        """show_summary prints deduplicated line when deduplicated_files > 0."""
        from file_organizer.core.display import show_summary

        console = MagicMock()
        res = OrganizationResult(total_files=5, processed_files=3, deduplicated_files=2)
        show_summary(console, res, tmp_path, dry_run=False)
        printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "2" in printed and "uplicate" in printed


# ---------------------------------------------------------------------------
# initializer module tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestInitializer:
    """Tests for core.initializer module."""

    @patch("file_organizer.core.initializer.TextProcessor")
    def test_init_text_processor_success(self, mock_text_cls: MagicMock) -> None:
        """Successful text processor init returns initialized processor."""
        from file_organizer.core.initializer import init_text_processor

        config = ModelConfig(name="test", model_type=ModelType.TEXT)
        console = MagicMock()
        result = init_text_processor(config, console)

        mock_text_cls.assert_called_once_with(config=config)
        mock_text_cls.return_value.initialize.assert_called_once()
        assert result is mock_text_cls.return_value

    @patch("file_organizer.core.initializer.TextProcessor")
    def test_init_text_processor_failure_returns_none(self, mock_text_cls: MagicMock) -> None:
        """Any exception during text init returns None."""
        from file_organizer.core.initializer import init_text_processor

        mock_text_cls.return_value.initialize.side_effect = ConnectionRefusedError("down")
        config = ModelConfig(name="test", model_type=ModelType.TEXT)
        console = MagicMock()
        result = init_text_processor(config, console)

        assert result is None

    @patch("file_organizer.core.initializer.VisionProcessor")
    def test_init_vision_processor_success(self, mock_vision_cls: MagicMock) -> None:
        """Successful vision processor init returns initialized processor."""
        from file_organizer.core.initializer import init_vision_processor

        config = ModelConfig(name="test", model_type=ModelType.VISION)
        console = MagicMock()
        result = init_vision_processor(config, console)

        mock_vision_cls.assert_called_once_with(config=config)
        mock_vision_cls.return_value.initialize.assert_called_once()
        assert result is mock_vision_cls.return_value

    @patch("file_organizer.core.initializer.VisionProcessor")
    def test_init_vision_processor_failure_returns_none(self, mock_vision_cls: MagicMock) -> None:
        """Any exception during vision init returns None."""
        from file_organizer.core.initializer import init_vision_processor

        mock_vision_cls.return_value.initialize.side_effect = ImportError("missing")
        config = ModelConfig(name="test", model_type=ModelType.VISION)
        console = MagicMock()
        result = init_vision_processor(config, console)

        assert result is None


# ---------------------------------------------------------------------------
# Plan-flow edge cases and thin delegation wrappers (#1504 coverage)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestOrganizerPlanEdgeCases:
    """Edge cases for the plan-based organize flow and small delegations."""

    def test_init_rejects_negative_max_transcribe_seconds(
        self, text_config: ModelConfig, vision_config: ModelConfig
    ) -> None:
        with pytest.raises(ValueError, match="max_transcribe_seconds must be >= 0"):
            FileOrganizer(
                text_model_config=text_config,
                vision_model_config=vision_config,
                max_transcribe_seconds=-1,
            )

    def test_init_subclass_requires_fallback_map_entries(self) -> None:
        with pytest.raises(TypeError, match="_TEXT_FALLBACK_MAP is missing entries"):

            class _BadOrganizer(FileOrganizer):
                TEXT_EXTENSIONS = FileOrganizer.TEXT_EXTENSIONS | {".weird"}

    def test_build_plan_raises_when_result_has_no_plan(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        result = OrganizationResult(total_files=0)
        with (
            patch.object(organizer, "organize", return_value=result),
            pytest.raises(RuntimeError, match="did not produce an executable plan"),
        ):
            organizer.build_plan(tmp_path, tmp_path / "out")

    def test_organize_reraises_execute_failure(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """A live-run execute failure propagates instead of being swallowed."""
        doc = tmp_path / "input" / "notes.txt"
        doc.parent.mkdir()
        doc.write_text("hi")
        organizer.dry_run = False

        def _fake_init() -> None:
            tp = MagicMock()
            tp.text_model.is_initialized = True
            organizer.text_processor = tp

        processed = ProcessedFile(
            file_path=doc,
            description="Categorized into Docs",
            folder_name="Docs",
            filename=doc.stem,
        )
        with (
            patch("file_organizer.core.file_ops.collect_files", return_value=[doc]),
            patch(
                "file_organizer.core.organizer.dispatcher.process_text_files",
                return_value=[processed],
            ),
            patch.object(organizer, "_init_text_processor", side_effect=_fake_init),
            patch(
                "file_organizer.core.organizer.execute_plan",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError, match="disk full"),
        ):
            organizer.organize(doc.parent, tmp_path / "out")

    def test_organize_keeps_files_with_unreadable_hash(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """Files whose hash cannot be read are kept, not deduplicated away."""
        first = tmp_path / "input" / "a.txt"
        second = tmp_path / "input" / "b.txt"
        first.parent.mkdir()
        first.write_text("same")
        second.write_text("same")

        def _fake_init() -> None:
            tp = MagicMock()
            tp.text_model.is_initialized = True
            organizer.text_processor = tp

        processed = [
            ProcessedFile(
                file_path=path,
                description="Categorized into Docs",
                folder_name="Docs",
                filename=path.stem,
            )
            for path in (first, second)
        ]
        with (
            patch("file_organizer.core.file_ops.collect_files", return_value=[first, second]),
            patch(
                "file_organizer.core.organizer.dispatcher.process_text_files",
                return_value=processed,
            ),
            patch.object(organizer, "_init_text_processor", side_effect=_fake_init),
            patch.object(FileOrganizer, "_sha256_via_safedir", return_value=None),
        ):
            result = organizer.organize(first.parent, tmp_path / "out")

        assert result.deduplicated_files == 0
        assert result.processed_files == 2

    def test_organize_routes_cad_files_to_extension_fallback(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """CAD files fall back to extension routing when no text model is ready."""
        drawing = tmp_path / "input" / "part.dwg"
        drawing.parent.mkdir()
        drawing.write_bytes(b"fake dwg")

        with (
            patch("file_organizer.core.file_ops.collect_files", return_value=[drawing]),
            patch.object(organizer, "_init_text_processor", return_value=None),
        ):
            result = organizer.organize(drawing.parent, tmp_path / "out")

        assert result.total_files == 1
        assert result.organized_structure

    def test_organize_files_delegates_to_file_ops(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        with patch(
            "file_organizer.core.organizer.file_ops.organize_files", return_value={}
        ) as mock_organize:
            assert organizer._organize_files([], tmp_path / "out", True) == {}
        mock_organize.assert_called_once()

    def test_process_image_files_delegates_to_dispatcher(self, organizer: FileOrganizer) -> None:
        organizer.vision_processor = MagicMock()
        with patch(
            "file_organizer.core.organizer.dispatcher.process_image_files", return_value=[]
        ) as mock_process:
            assert organizer._process_image_files([]) == []
        mock_process.assert_called_once()

    def test_process_video_files_delegates_to_dispatcher(self, organizer: FileOrganizer) -> None:
        with patch(
            "file_organizer.core.organizer.dispatcher.process_video_files", return_value=[]
        ) as mock_process:
            assert organizer._process_video_files([]) == []
        mock_process.assert_called_once()

    def test_init_vision_processor_delegates_to_initializer(self, organizer: FileOrganizer) -> None:
        with patch(
            "file_organizer.core.organizer.initializer.init_vision_processor",
            return_value=None,
        ) as mock_init:
            organizer._init_vision_processor()
        assert organizer.vision_processor is None
        mock_init.assert_called_once()
