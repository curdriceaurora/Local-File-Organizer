"""Tests for prompt enrichment and tags in VisionProcessor (#66, #64).

Marked ci so branch coverage counts toward the diff-coverage gate.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.models.base import ModelType
from file_organizer.models.vision_schema import VisionSchema
from file_organizer.services.vision_processor import ProcessedImage, VisionProcessor

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@pytest.fixture
def mock_vision_model() -> MagicMock:
    model = MagicMock()
    model.is_initialized = True
    model.config.model_type = ModelType.VISION
    model.generate.return_value = "Mocked AI Response"
    return model


@pytest.fixture
def vision_processor(mock_vision_model: MagicMock) -> VisionProcessor:
    return VisionProcessor(vision_model=mock_vision_model)


class TestVisionPromptEnrichment:
    """Test path hints and tags instructions in vision prompts."""

    def test_build_structured_prompt_includes_file_and_parent_hint(
        self, vision_processor: VisionProcessor
    ) -> None:
        file_path = Path("/") / "workspace" / "assets" / "screenshots" / "dashboard_v1.png"
        prompt = vision_processor._build_structured_prompt(
            file_path=file_path,
            generate_folder=True,
            generate_filename=True,
            perform_ocr=True,
        )

        assert "dashboard_v1.png" in prompt
        assert "screenshots" in prompt
        assert "tags" in prompt.lower()

    def test_vision_schema_carries_tags(self) -> None:
        schema = VisionSchema(
            description="A cloud architecture diagram",
            folder_name="diagrams",
            filename="cloud_architecture",
            has_text=True,
            extracted_text="AWS Architecture",
            tags=["cloud", "architecture", "aws"],
        )
        assert schema.tags == ["cloud", "architecture", "aws"]

    def test_processed_image_defaults_tags_to_empty_list(self) -> None:
        img = ProcessedImage(
            file_path=Path("img.png"),
            description="desc",
            folder_name="folder",
            filename="name",
        )
        assert img.tags == []

    def test_process_file_extracts_tags_from_structured_schema(
        self, vision_processor: VisionProcessor, mock_vision_model: MagicMock, tmp_path: Path
    ) -> None:
        img_path = tmp_path / "diagram.png"
        img_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        mock_schema = VisionSchema(
            description="System architecture flowchart",
            folder_name="diagrams",
            filename="system_architecture",
            has_text=False,
            extracted_text=None,
            tags=["architecture", "flowchart", "system"],
        )
        mock_vision_model.generate_structured.return_value = mock_schema

        result = vision_processor.process_file(img_path)

        assert isinstance(result, ProcessedImage)
        assert result.folder_name == "diagrams"
        assert result.filename == "system_architecture"
        assert result.tags == ["architecture", "flowchart", "system"]
