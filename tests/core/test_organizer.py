"""Tests for Core Organizer logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.core.organizer import FileOrganizer, OrganizationResult
from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.services.text_processor import ProcessedFile
from file_organizer.services.vision_processor import ProcessedImage


@pytest.fixture
def text_config():
    return ModelConfig(name="test-text", model_type=ModelType.TEXT)


@pytest.fixture
def vision_config():
    return ModelConfig(name="test-vision", model_type=ModelType.VISION)


@pytest.fixture
def organizer(text_config, vision_config):
    """FileOrganizer instance configured for testing."""
    return FileOrganizer(
        text_model_config=text_config,
        vision_model_config=vision_config,
        dry_run=True,
        use_hardlinks=False,
    )


@pytest.mark.unit
class TestFileOrganizer:
    """Tests for FileOrganizer class."""

    def test_init(self, text_config, vision_config):
        """Test default and custom initialization."""
        # Default
        org = FileOrganizer()
        assert org.text_model_config.name == "qwen2.5:3b-instruct-q4_K_M"
        assert org.dry_run is True

        # Custom
        org = FileOrganizer(
            text_model_config=text_config,
            vision_model_config=vision_config,
            dry_run=False,
            use_hardlinks=True,
            parallel_workers=2,
        )
        assert org.text_model_config == text_config
        assert org.dry_run is False
        assert org.use_hardlinks is True
        assert org.parallel_config.max_workers == 2

    def test_collect_files(self, organizer, tmp_path):
        """Test scanning files in a directory hierarchy."""
        # Create some files
        (tmp_path / "file1.txt").touch()
        (tmp_path / ".hidden.txt").touch()  # Should be skipped
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file2.jpg").touch()

        files = organizer._collect_files(tmp_path)

        # Should find file1 and file2, but not .hidden
        assert len(files) == 2
        names = {f.name for f in files}
        assert "file1.txt" in names
        assert "file2.jpg" in names
        assert ".hidden.txt" not in names

    def test_organize_input_missing(self, organizer, tmp_path):
        """Test organizing fails when input path does not exist."""
        with pytest.raises(ValueError, match="Input path does not exist"):
            organizer.organize(tmp_path / "missing", tmp_path / "out")

    @patch("file_organizer.core.organizer.TextProcessor")
    @patch("file_organizer.core.organizer.VisionProcessor")
    @patch("file_organizer.core.organizer.FileOrganizer._collect_files")
    def test_organize_empty_directory(self, mock_collect, mock_vision, mock_text, organizer, tmp_path):
        """Test organizing an empty directory returns early."""
        mock_collect.return_value = []

        result = organizer.organize(tmp_path, tmp_path / "out")

        assert result.total_files == 0
        mock_text.assert_not_called()
        mock_vision.assert_not_called()

    @patch.object(FileOrganizer, "_process_text_files")
    @patch.object(FileOrganizer, "_process_image_files")
    @patch.object(FileOrganizer, "_simulate_organization")
    @patch.object(FileOrganizer, "_collect_files")
    @patch("file_organizer.core.organizer.TextProcessor")
    @patch("file_organizer.core.organizer.VisionProcessor")
    def test_organize_dry_run_flow(
        self, mock_vision_cls, mock_text_cls, mock_collect, mock_simulate, mock_imgs, mock_txts, organizer, tmp_path
    ):
        """Test full orchestrator flow in dry-run mode."""
        # Setup files
        txt_path = tmp_path / "test.txt"
        img_path = tmp_path / "test.jpg"
        mock_collect.return_value = [txt_path, img_path]

        # Setup mock processors and results
        mock_txt_proc = ProcessedFile(txt_path, "desc", "docs", "test_file")
        mock_img_proc = ProcessedImage(img_path, "desc", "images", "test_img")

        mock_txts.return_value = [mock_txt_proc]
        mock_imgs.return_value = [mock_img_proc]

        mock_simulate.return_value = {"docs": ["test_file.txt"], "images": ["test_img.jpg"]}

        result = organizer.organize(tmp_path, tmp_path / "out")

        # Verify pipeline sequence
        mock_collect.assert_called_once_with(tmp_path)
        mock_txts.assert_called_once_with([txt_path])
        mock_imgs.assert_called_once_with([img_path])
        mock_simulate.assert_called_once_with([mock_txt_proc, mock_img_proc], tmp_path / "out")

        # Verify result parsing
        assert result.total_files == 2
        assert result.processed_files == 2
        assert result.organized_structure == {"docs": ["test_file.txt"], "images": ["test_img.jpg"]}

    @patch.object(FileOrganizer, "_organize_files")
    @patch.object(FileOrganizer, "_process_text_files")
    @patch.object(FileOrganizer, "_collect_files")
    @patch("file_organizer.core.organizer.TextProcessor")
    def test_organize_live_run_flow(
        self, mock_text_cls, mock_collect, mock_txts, mock_org, organizer, tmp_path
    ):
        """Test full orchestrator flow in live mode (moves files)."""
        organizer.dry_run = False

        # Setup test data
        txt_path = tmp_path / "test.txt"
        mock_collect.return_value = [txt_path]
        mock_txt_proc = ProcessedFile(txt_path, "desc", "docs", "test_file")
        mock_txts.return_value = [mock_txt_proc]
        mock_org.return_value = {"docs": ["test_file.txt"]}

        result = organizer.organize(tmp_path, tmp_path / "out")

        mock_org.assert_called_once_with([mock_txt_proc], tmp_path / "out", True)
        assert result.organized_structure == {"docs": ["test_file.txt"]}

    def test_simulate_organization(self, organizer, tmp_path):
        """Test simulation builds output structure dict without creating files."""
        p1 = ProcessedFile(tmp_path / "f1.txt", "", "docs", "file_1")
        p2 = ProcessedFile(tmp_path / "f2.txt", "", "docs", "file_2")
        p3 = ProcessedImage(tmp_path / "i1.jpg", "", "images", "img_1")
        err = ProcessedFile(tmp_path / "e.txt", "", "errs", "e", error="fail")

        out_path = tmp_path / "out"
        structure = organizer._simulate_organization([p1, p2, p3, err], out_path)

        assert structure == {
            "docs": ["file_1.txt", "file_2.txt"],
            "images": ["img_1.jpg"]
        }
        # Verify it didn't create anything
        assert not out_path.exists()

    @patch("file_organizer.core.organizer.shutil.copy2")
    def test_organize_files_copy(self, mock_copy, organizer, tmp_path):
        """Test physical file copy organization."""
        organizer.dry_run = False
        organizer.use_hardlinks = False # Force copy

        out_path = tmp_path / "out"
        f1 = tmp_path / "f1.txt"

        proc = ProcessedFile(f1, "", "docs", "file_1")

        structure = organizer._organize_files([proc], out_path, True)

        assert structure == {"docs": ["file_1.txt"]}
        mock_copy.assert_called_once_with(f1, out_path / "docs" / "file_1.txt")
        assert (out_path / "docs").is_dir()

    @patch("file_organizer.core.organizer.os.link")
    def test_organize_files_hardlink(self, mock_link, organizer, tmp_path):
        """Test physical file hardlink organization."""
        organizer.dry_run = False
        organizer.use_hardlinks = True

        out_path = tmp_path / "out"
        f1 = tmp_path / "f1.txt"

        proc = ProcessedFile(f1, "", "docs", "file_1")

        structure = organizer._organize_files([proc], out_path, True)

        assert structure == {"docs": ["file_1.txt"]}
        mock_link.assert_called_once_with(f1, out_path / "docs" / "file_1.txt")

    @patch("file_organizer.core.organizer.shutil.copy2")
    def test_organize_files_collision(self, mock_copy, organizer, tmp_path):
        """Test handling of identical filenames during copy."""
        organizer.dry_run = False
        organizer.use_hardlinks = False

        out_path = tmp_path / "out"
        docs_dir = out_path / "docs"
        docs_dir.mkdir(parents=True)
        # Create a file that already exists to force collision numbering
        (docs_dir / "file_1.txt").touch()

        f1 = tmp_path / "f1.txt"
        proc = ProcessedFile(f1, "", "docs", "file_1")

        # When skip_existing is False, it should use _1 suffix
        structure = organizer._organize_files([proc], out_path, skip_existing=False)

        assert structure == {"docs": ["file_1_1.txt"]}
        mock_copy.assert_called_once_with(f1, out_path / "docs" / "file_1_1.txt")

    def test_show_methods_do_not_crash(self, organizer, tmp_path):
        """Ensure UI display methods run without error."""
        organizer._show_file_breakdown([tmp_path], [tmp_path], [tmp_path], [tmp_path], [tmp_path], [tmp_path])
        organizer._show_skipped_files([tmp_path], [tmp_path], [tmp_path])

        res = OrganizationResult(total_files=5, processing_time=1.0)
        organizer._show_summary(res, tmp_path)
