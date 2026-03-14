"""Tests for Core Organizer logic.

After the God Object decomposition, tests are organized by module:
- FileOrganizer facade (public API)
- file_ops (collect, organize, simulate, fallback, cleanup)
- display (Rich UI helpers)
- initializer (processor startup)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.types import OrganizationResult
from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.services.text_processor import ProcessedFile
from file_organizer.services.vision_processor import ProcessedImage


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

    @patch("file_organizer.core.file_ops.shutil.copy2")
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
        mock_copy.assert_called_once_with(f1, out_path / "docs" / "file_1.txt")
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

    @patch("file_organizer.core.file_ops.shutil.copy2")
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
        mock_copy.assert_called_once_with(f1, out_path / "docs" / "file_1_1.txt")

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
