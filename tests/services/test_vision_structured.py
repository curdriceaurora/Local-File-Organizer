"""Tests for structured vision processing, shape validation, and OOM circuit breaking."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from file_organizer.models.base import (
    BaseModel,
    ModelConfig,
    ModelType,
    StructuredParseError,
    parse_structured_json,
)
from file_organizer.models.vision_schema import VisionSchema
from file_organizer.services.vision_processor import (
    ProcessedImage,
    VisionProcessor,
    _mime_type_for_image_format,
    preprocess_and_clamp_image,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestStructuredJsonParser:
    """Verify parse_structured_json robustness."""

    def test_clean_json(self) -> None:
        text = '{"description": "desc", "folder_name": "folders", "filename": "file", "has_text": false}'
        res = parse_structured_json(text, VisionSchema)
        assert isinstance(res, VisionSchema)
        assert res.description == "desc"
        assert res.has_text is False

    def test_markdown_code_block(self) -> None:
        text = '```json\n{"description": "desc", "folder_name": "folders", "filename": "file", "has_text": false}\n```'
        res = parse_structured_json(text, VisionSchema)
        assert isinstance(res, VisionSchema)
        assert res.description == "desc"

    def test_malformed_markdown_code_block_reports_parse_error(self) -> None:
        text = "```json\n{not-json}\n```"
        with pytest.raises(StructuredParseError, match="Failed to parse JSON"):
            parse_structured_json(text, VisionSchema)

    def test_conversational_wrapping(self) -> None:
        text = 'Sure, here is the result: {"description": "desc", "folder_name": "folders", "filename": "file", "has_text": false} hope that helps!'
        res = parse_structured_json(text, VisionSchema)
        assert isinstance(res, VisionSchema)
        assert res.description == "desc"

    def test_no_json_found(self) -> None:
        with pytest.raises(StructuredParseError, match="No JSON object found"):
            parse_structured_json("hello world", VisionSchema)

    def test_invalid_schema(self) -> None:
        with pytest.raises(StructuredParseError, match="validation"):
            parse_structured_json('{"description": "desc"}', VisionSchema)

    def test_object_shaped_extracted_text_is_normalized(self) -> None:
        text = (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": true, '
            '"extracted_text": {"text": "Payment process"}}'
        )

        res = parse_structured_json(text, VisionSchema)

        assert isinstance(res, VisionSchema)
        assert res.extracted_text == "Payment process"

    def test_string_extracted_text_is_preserved(self) -> None:
        text = (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": true, '
            '"extracted_text": "Payment process"}'
        )

        res = parse_structured_json(text, VisionSchema)

        assert isinstance(res, VisionSchema)
        assert res.extracted_text == "Payment process"

    def test_none_extracted_text_is_preserved(self) -> None:
        text = (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": false, '
            '"extracted_text": null}'
        )

        res = parse_structured_json(text, VisionSchema)

        assert isinstance(res, VisionSchema)
        assert res.extracted_text is None

    def test_object_text_list_shaped_extracted_text_is_joined(self) -> None:
        text = (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": true, '
            '"extracted_text": {"text": ["Payment", "process"]}}'
        )

        res = parse_structured_json(text, VisionSchema)

        assert isinstance(res, VisionSchema)
        assert res.extracted_text == "Payment\nprocess"

    def test_unknown_object_shaped_extracted_text_becomes_none(self) -> None:
        text = (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": true, '
            '"extracted_text": {"confidence": 0.7}}'
        )

        res = parse_structured_json(text, VisionSchema)

        assert isinstance(res, VisionSchema)
        assert res.extracted_text is None

    def test_list_shaped_extracted_text_is_joined(self) -> None:
        text = (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": true, '
            '"extracted_text": ["Payment", "process"]}'
        )

        res = parse_structured_json(text, VisionSchema)

        assert isinstance(res, VisionSchema)
        assert res.extracted_text == "Payment\nprocess"

    def test_object_lines_shaped_extracted_text_is_joined(self) -> None:
        text = (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": true, '
            '"extracted_text": {"lines": ["Payment", "process"]}}'
        )

        res = parse_structured_json(text, VisionSchema)

        assert isinstance(res, VisionSchema)
        assert res.extracted_text == "Payment\nprocess"

    def test_generate_structured_adds_schema_instruction(self) -> None:
        class DummyModel(BaseModel):
            def __init__(self) -> None:
                super().__init__(ModelConfig(name="dummy", model_type=ModelType.TEXT))
                self.last_prompt = ""
                self.last_kwargs: dict[str, object] = {}

            def initialize(self) -> None:
                super().initialize()

            def generate(self, prompt: str, **kwargs: object) -> str:
                self.last_prompt = prompt
                self.last_kwargs = kwargs
                return (
                    '{"description":"desc","folder_name":"folders",'
                    '"filename":"file","has_text":false}'
                )

            def cleanup(self) -> None:
                pass

        model = DummyModel()
        result = model.generate_structured("Describe", VisionSchema, temperature=0.2)

        assert isinstance(result, VisionSchema)
        assert result.description == "desc"
        assert "JSON Schema" in model.last_prompt
        assert model.last_kwargs == {"temperature": 0.2}


class TestImagePreprocessingAndClamping:
    """Verify preprocess_and_clamp_image shape validation and downsampling."""

    def test_no_clamping_needed(self, tmp_path: Path) -> None:
        img_path = tmp_path / "test.jpg"
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(img_path, "JPEG")

        res_bytes, mime_type = preprocess_and_clamp_image(img_path, max_edge=200)
        assert len(res_bytes) > 0
        assert mime_type == "image/jpeg"

        with Image.open(io.BytesIO(res_bytes)) as processed:
            assert processed.size == (100, 100)

    def test_unknown_pillow_format_defaults_to_jpeg_mime(self) -> None:
        assert _mime_type_for_image_format("TIFF") == "image/jpeg"

    def test_clamping_applied(self, tmp_path: Path) -> None:
        img_path = tmp_path / "large.jpg"
        img = Image.new("RGB", (2000, 1000), color="red")
        img.save(img_path, "JPEG")

        res_bytes, mime_type = preprocess_and_clamp_image(img_path, max_edge=1000)
        assert mime_type == "image/jpeg"
        with Image.open(io.BytesIO(res_bytes)) as processed:
            assert processed.size == (1000, 500)  # Aspect ratio preserved!

    def test_portrait_clamping_applied(self, tmp_path: Path) -> None:
        img_path = tmp_path / "portrait.jpg"
        img = Image.new("RGB", (1000, 2000), color="red")
        img.save(img_path, "JPEG")

        res_bytes, mime_type = preprocess_and_clamp_image(img_path, max_edge=1000)
        assert mime_type == "image/jpeg"
        with Image.open(io.BytesIO(res_bytes)) as processed:
            assert processed.size == (500, 1000)

    def test_png_mime_type_preserved(self, tmp_path: Path) -> None:
        img_path = tmp_path / "diagram.png"
        img = Image.new("RGB", (10, 10), color="yellow")
        img.save(img_path, "PNG")

        res_bytes, mime_type = preprocess_and_clamp_image(img_path, max_edge=10)
        assert res_bytes == img_path.read_bytes()
        assert mime_type == "image/png"

    def test_rgba_to_rgb_conversion(self, tmp_path: Path) -> None:
        img_path = tmp_path / "rgba.tiff"
        img = Image.new("RGBA", (10, 10), color=(255, 0, 0, 128))
        img.save(img_path, "TIFF")

        res_bytes, mime_type = preprocess_and_clamp_image(img_path, max_edge=10)
        assert mime_type == "image/jpeg"
        with Image.open(io.BytesIO(res_bytes)) as processed:
            assert processed.mode == "RGB"

    def test_webp_mime_type_preserved(self, tmp_path: Path) -> None:
        img_path = tmp_path / "modern.webp"
        img = Image.new("RGB", (10, 10), color="green")
        img.save(img_path, "WEBP")

        res_bytes, mime_type = preprocess_and_clamp_image(img_path, max_edge=10)
        assert res_bytes == img_path.read_bytes()
        assert mime_type == "image/webp"

    def test_invalid_dimensions(self, tmp_path: Path) -> None:
        img_path = tmp_path / "empty.jpg"
        img_path.write_bytes(b"")  # corrupt empty file
        res_bytes, mime_type = preprocess_and_clamp_image(img_path)
        assert len(res_bytes) == 0
        assert mime_type == "image/jpeg"

    def test_missing_pillow_falls_back_to_guessed_mime(self, tmp_path: Path) -> None:
        img_path = tmp_path / "raw.webp"
        img_path.write_bytes(b"raw")

        with patch.dict("sys.modules", {"PIL": None}):
            res_bytes, mime_type = preprocess_and_clamp_image(img_path)

        assert res_bytes == b"raw"
        assert mime_type == "image/webp"

    def test_zero_dimensions_falls_back_to_raw_bytes(self, tmp_path: Path) -> None:
        img_path = tmp_path / "zero.jpg"
        img_path.write_bytes(b"raw")
        fake_img = MagicMock()
        fake_img.__enter__.return_value = fake_img
        fake_img.__exit__.return_value = None
        fake_img.size = (0, 10)

        with patch("PIL.Image.open", return_value=fake_img):
            res_bytes, mime_type = preprocess_and_clamp_image(img_path)

        assert res_bytes == b"raw"
        assert mime_type == "image/jpeg"


class TestVisionProcessorStructured:
    """Verify VisionProcessor structured output execution and fallbacks."""

    @pytest.fixture
    def mock_model(self) -> MagicMock:
        model = MagicMock()
        model.is_initialized = True
        model.config.model_type = ModelType.VISION
        return model

    def test_process_file_structured_success(self, mock_model: MagicMock, tmp_path: Path) -> None:
        img_path = tmp_path / "test.jpg"
        img = Image.new("RGB", (10, 10))
        img.save(img_path, "JPEG")

        processor = VisionProcessor(vision_model=mock_model)

        mock_model.generate_structured.return_value = VisionSchema(
            description="A scenic view",
            folder_name="landscapes",
            filename="mountain_view",
            has_text=False,
        )

        result = processor.process_file(img_path)
        assert isinstance(result, ProcessedImage)
        assert result.description == "A scenic view"
        assert result.folder_name == "landscapes"
        assert result.filename == "mountain_view"
        assert result.source == "vision"
        assert result.confidence == 1.0
        assert result.error is None
        assert mock_model.generate_structured.call_args.kwargs["mime_type"] == "image/jpeg"

    def test_unsupported_format_uses_metadata_fallback(
        self, mock_model: MagicMock, tmp_path: Path
    ) -> None:
        img_path = tmp_path / "vector.svg"
        img_path.write_text("<svg></svg>", encoding="utf-8")

        processor = VisionProcessor(vision_model=mock_model)

        result = processor.process_file(img_path)

        mock_model.generate_structured.assert_not_called()
        assert result.error == "Unsupported image format for vision model: .svg"
        assert result.source == "fallback_filename"
        assert result.filename == "vector"

    def test_process_file_missing_file_does_not_invoke_model(self, mock_model: MagicMock) -> None:
        result = VisionProcessor(vision_model=mock_model).process_file("missing.jpg")

        mock_model.generate_structured.assert_not_called()
        assert result.error == "File not found"
        assert result.folder_name == "errors"
        assert result.confidence == 0.0

    def test_process_file_disabled_folder_and_filename_uses_defaults(
        self, mock_model: MagicMock, tmp_path: Path
    ) -> None:
        img_path = tmp_path / "test.jpg"
        Image.new("RGB", (10, 10)).save(img_path, "JPEG")
        mock_model.generate_structured.return_value = VisionSchema(
            description="A scenic view",
            folder_name="ignored",
            filename="ignored",
            has_text=False,
        )

        result = VisionProcessor(vision_model=mock_model).process_file(
            img_path,
            generate_folder=False,
            generate_filename=False,
        )

        prompt = mock_model.generate_structured.call_args.kwargs["prompt"]
        assert "- folder_name: Return the string 'images'." in prompt
        assert f"- filename: Return the string '{img_path.stem}'." in prompt
        assert result.folder_name == "images"
        assert result.filename == img_path.stem

    def test_process_file_short_names_fall_back_to_defaults(
        self, mock_model: MagicMock, tmp_path: Path
    ) -> None:
        img_path = tmp_path / "test.jpg"
        Image.new("RGB", (10, 10)).save(img_path, "JPEG")
        mock_model.generate_structured.return_value = VisionSchema(
            description="A scenic view",
            folder_name="a",
            filename="a",
            has_text=False,
        )

        result = VisionProcessor(vision_model=mock_model).process_file(img_path)

        assert result.folder_name == "images"
        assert result.filename == img_path.stem

    def test_fallback_failure_uses_error_result(
        self, mock_model: MagicMock, tmp_path: Path
    ) -> None:
        img_path = tmp_path / "test.jpg"
        Image.new("RGB", (10, 10)).save(img_path, "JPEG")
        mock_model.generate_structured.side_effect = RuntimeError("model failed")

        with patch(
            "file_organizer.services.vision_fallback.compute_fallback",
            side_effect=RuntimeError("fallback failed"),
        ):
            result = VisionProcessor(vision_model=mock_model).process_file(img_path)

        assert result.description == ""
        assert result.folder_name == "errors"
        assert result.error == "model failed"
        assert result.confidence == 0.0

    def test_guarded_generate_trips_circuit_on_fatal_error(self, mock_model: MagicMock) -> None:
        mock_model.generate.side_effect = RuntimeError("failed to allocate memory")
        processor = VisionProcessor(vision_model=mock_model)

        with pytest.raises(RuntimeError, match="failed to allocate"):
            processor._guarded_generate(prompt="x", image_path="x.jpg")

        assert processor._is_circuit_open() is True

    def test_guarded_generate_structured_raises_when_circuit_open(
        self, mock_model: MagicMock
    ) -> None:
        processor = VisionProcessor(vision_model=mock_model)
        processor._trip_backend_circuit(RuntimeError("backend unavailable"))

        with pytest.raises(RuntimeError, match="Vision backend circuit open"):
            processor._guarded_generate_structured(prompt="x", schema=VisionSchema)

    def test_oom_fatal_error_trips_circuit(self, mock_model: MagicMock, tmp_path: Path) -> None:
        img_path = tmp_path / "test.jpg"
        img = Image.new("RGB", (10, 10))
        img.save(img_path, "JPEG")

        processor = VisionProcessor(vision_model=mock_model, backend_cooldown_seconds=1.0)

        # Mock raises OOM exception
        mock_model.generate_structured.side_effect = RuntimeError("Ollama OOM: out of memory")

        # First call fails and should fall back to metadata
        result = processor.process_file(img_path)
        assert result.confidence < 1.0  # fallback confidence
        assert result.error is not None
        assert "out of memory" in result.error
        assert processor._is_circuit_open() is True

        # Second call is short-circuited and goes straight to fallback
        mock_model.generate_structured.reset_mock()
        result2 = processor.process_file(img_path)
        mock_model.generate_structured.assert_not_called()
        assert result2.error is not None
        assert "backend unavailable" in result2.error
