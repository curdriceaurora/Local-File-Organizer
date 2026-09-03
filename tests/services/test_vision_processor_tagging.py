"""Tests for vision processor LLM tag generation (#1760)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from file_organizer.models.base import ModelType
from file_organizer.models.vision_schema import TaggedVisionSchema, VisionSchema
from file_organizer.services.vision_processor import ProcessedImage, VisionProcessor

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    img_path = tmp_path / "sample.jpg"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(img_path, format="JPEG")
    return img_path


@pytest.fixture
def mock_vision_model() -> MagicMock:
    model = MagicMock()
    model.config.model_type = ModelType.VISION
    model.is_initialized = True
    return model


@pytest.fixture
def processor(mock_vision_model: MagicMock) -> VisionProcessor:
    proc = VisionProcessor(vision_model=mock_vision_model)
    proc.vision_model = mock_vision_model
    return proc


def test_vision_tagging_disabled_selects_vision_schema(
    processor: VisionProcessor, sample_image: Path
) -> None:
    schema_res = VisionSchema(
        description="A blue image",
        folder_name="graphics",
        filename="blue_graphic",
        has_text=False,
    )
    processor._guarded_generate_structured = MagicMock(return_value=schema_res)  # type: ignore[method-assign]

    result = processor.process_file(sample_image, generate_tags=False)

    assert isinstance(result, ProcessedImage)
    assert result.tags == []
    processor._guarded_generate_structured.assert_called_once()
    called_schema = processor._guarded_generate_structured.call_args[1]["schema"]
    called_prompt = processor._guarded_generate_structured.call_args[1]["prompt"]
    assert called_schema is VisionSchema
    assert "- tags:" not in called_prompt


def test_vision_tagging_enabled_selects_tagged_vision_schema(
    processor: VisionProcessor, sample_image: Path
) -> None:
    schema_res = TaggedVisionSchema(
        description="A blue image",
        folder_name="graphics",
        filename="blue_graphic",
        has_text=False,
        tags=["Blue", "GRAPHIC", "square-shape"],
    )
    processor._guarded_generate_structured = MagicMock(return_value=schema_res)  # type: ignore[method-assign]

    result = processor.process_file(
        sample_image,
        generate_tags=True,
        tag_style="descriptive",
        tag_prompt="focus on colors",
    )

    assert isinstance(result, ProcessedImage)
    assert "blue" in result.tags
    assert "graphic" in result.tags
    assert "square-shape" in result.tags
    processor._guarded_generate_structured.assert_called_once()
    called_schema = processor._guarded_generate_structured.call_args[1]["schema"]
    called_prompt = processor._guarded_generate_structured.call_args[1]["prompt"]
    assert called_schema is TaggedVisionSchema
    assert "- tags:" in called_prompt
    assert "descriptive" in called_prompt
    assert "focus on colors" in called_prompt


def test_vision_fast_path_only_generate_tags_invokes_model(
    processor: VisionProcessor, sample_image: Path
) -> None:
    schema_res = TaggedVisionSchema(
        description="Ignored",
        folder_name="Ignored",
        filename="Ignored",
        has_text=False,
        tags=["screenshot", "blue"],
    )
    processor._guarded_generate_structured = MagicMock(return_value=schema_res)  # type: ignore[method-assign]

    result = processor.process_file(
        sample_image,
        generate_description=False,
        generate_folder=False,
        generate_filename=False,
        perform_ocr=False,
        generate_tags=True,
    )

    processor._guarded_generate_structured.assert_called_once()
    assert result.tags == ["screenshot", "blue"]
    assert result.description == ""


def test_vision_fast_path_all_flags_off_bypasses_model(
    processor: VisionProcessor, sample_image: Path
) -> None:
    processor._guarded_generate_structured = MagicMock()  # type: ignore[method-assign]

    result = processor.process_file(
        sample_image,
        generate_description=False,
        generate_folder=False,
        generate_filename=False,
        perform_ocr=False,
        generate_tags=False,
    )

    processor._guarded_generate_structured.assert_not_called()
    assert result.tags == []
    assert result.description == ""


def test_vision_tagging_comma_separated_tags(
    processor: VisionProcessor, sample_image: Path
) -> None:
    schema_res = MagicMock()
    schema_res.description = "A blue shape"
    schema_res.folder_name = "graphics"
    schema_res.filename = "blue_graphic"
    schema_res.has_text = False
    schema_res.extracted_text = None
    schema_res.tags = "blue, geometric, abstract"
    processor._guarded_generate_structured = MagicMock(return_value=schema_res)  # type: ignore[method-assign]

    result = processor.process_file(sample_image, generate_tags=True)

    assert result.tags == ["blue", "geometric", "abstract"]


def test_vision_tagging_error_produces_empty_tags(
    processor: VisionProcessor, sample_image: Path
) -> None:
    processor._guarded_generate_structured = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("Vision inference failed")
    )

    result = processor.process_file(sample_image, generate_tags=True)

    assert result.tags == []
    assert result.error is not None
