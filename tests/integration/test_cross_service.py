"""Integration tests for Gap P2: Cross-Service.

Verifies that services compose correctly — TextProcessor reads real files,
VisionProcessor processes images, and FileOrganizer chains them to produce
organized output on disk.

All tests use real service instances; only the Ollama/OpenAI HTTP clients
are stubbed at the ``model._do_generate()`` level.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.services.text_processor import TextProcessor
from file_organizer.services.vision_processor import VisionProcessor

from .conftest import make_text_config, make_vision_config, minimal_png_bytes

pytestmark = [pytest.mark.integration]


class TestTextProcessorEndToEnd:
    """TextProcessor reads real files and returns structured metadata."""

    def test_process_txt_file(
        self,
        stub_text_model_init: None,
        stub_text_model_generate: MagicMock,
        stub_nltk: None,
        integration_source_dir: Path,
    ) -> None:
        """TextProcessor reads a real .txt file and returns metadata."""
        text_cfg = make_text_config()
        processor = TextProcessor(config=text_cfg)
        processor.initialize()

        result = processor.process_file(integration_source_dir / "report.txt")

        assert result.error is None
        assert result.description != ""
        assert result.folder_name != ""
        assert result.filename != ""
        assert result.original_content is not None
        assert "Revenue" in result.original_content

    def test_process_csv_file(
        self,
        stub_text_model_init: None,
        stub_text_model_generate: MagicMock,
        stub_nltk: None,
        integration_source_dir: Path,
    ) -> None:
        """TextProcessor reads a real .csv file and returns metadata."""
        text_cfg = make_text_config()
        processor = TextProcessor(config=text_cfg)
        processor.initialize()

        result = processor.process_file(integration_source_dir / "data.csv")

        assert result.error is None
        assert result.description != ""
        assert result.folder_name != ""
        assert result.filename != ""

    def test_process_md_file(
        self,
        stub_text_model_init: None,
        stub_text_model_generate: MagicMock,
        stub_nltk: None,
        integration_source_dir: Path,
    ) -> None:
        """TextProcessor reads a real .md file and returns metadata."""
        text_cfg = make_text_config()
        processor = TextProcessor(config=text_cfg)
        processor.initialize()

        result = processor.process_file(integration_source_dir / "notes.md")

        assert result.error is None
        assert result.description != ""
        assert result.folder_name != ""


class TestVisionProcessorEndToEnd:
    """VisionProcessor processes image files with stubbed model."""

    def test_process_image_file(
        self,
        stub_vision_model_init: None,
        stub_vision_model_generate: MagicMock,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """VisionProcessor processes a real image file and returns metadata."""
        img_path = tmp_path / "photo.png"
        img_path.write_bytes(minimal_png_bytes())

        vision_cfg = make_vision_config()
        processor = VisionProcessor(config=vision_cfg)
        processor.initialize()

        result = processor.process_file(img_path)

        assert result.error is None
        assert result.description != ""
        assert result.folder_name != ""
        assert result.filename != ""

    def test_nonexistent_image_returns_error(
        self,
        stub_vision_model_init: None,
        stub_vision_model_generate: MagicMock,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """VisionProcessor returns error for missing file, does not raise."""
        vision_cfg = make_vision_config()
        processor = VisionProcessor(config=vision_cfg)
        processor.initialize()

        result = processor.process_file(tmp_path / "nonexistent.png")

        assert result.error is not None


class TestOrganizerChainsProcessors:
    """FileOrganizer chains processors to produce organized output."""

    def test_organizer_chains_text_to_output(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """Organizer with dry_run=False creates files in output dir."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=False,
        )

        result = org.organize(
            input_path=str(integration_source_dir),
            output_path=str(integration_output_dir),
        )

        assert result.processed_files == 3
        assert result.failed_files == 0

        # Files should actually exist in output dir
        output_files = [f for f in integration_output_dir.rglob("*") if f.is_file()]
        assert len(output_files) == 3


class TestFallbackChain:
    """Model init failure falls back to extension-based organization."""

    def test_ollama_unavailable_falls_back_to_extension(
        self,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """When model init raises OSError, organizer falls back gracefully."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        # Patch initialize to simulate Ollama being down
        with patch(
            "file_organizer.services.text_processor.TextProcessor.initialize",
            side_effect=ConnectionRefusedError("Connection refused"),
        ):
            result = org.organize(
                input_path=str(integration_source_dir),
                output_path=str(integration_output_dir),
            )

        # Should still process files via extension fallback
        assert result.total_files == 3
        assert result.failed_files == 0
        assert "Documents" in result.organized_structure
        assert "Spreadsheets" in result.organized_structure
