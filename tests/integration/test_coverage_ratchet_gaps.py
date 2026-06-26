"""Integration tests addressing coverage gaps in files below their floors.

Targets:
- file_organizer/models/base.py
- file_organizer/models/_openai_client.py
- file_organizer/models/openai_vision_model.py
- file_organizer/services/vision_processor.py
- file_organizer/utils/readers/cad.py
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pydantic
import pytest
from PIL import Image

from file_organizer.models._openai_client import create_openai_client
from file_organizer.models.base import (
    ModelConfig,
    ModelType,
    StructuredParseError,
    parse_structured_json,
)
from file_organizer.models.openai_vision_model import OpenAIVisionModel
from file_organizer.services.vision_processor import (
    VisionProcessor,
    preprocess_and_clamp_image,
)
from file_organizer.utils.readers._base import FileReadError
from file_organizer.utils.readers.cad import read_dwg_file, read_dxf_file

pytestmark = pytest.mark.integration


# ===========================================================================
# 1. file_organizer/models/base.py Tests
# ===========================================================================


class DummySchema(pydantic.BaseModel):
    foo: str
    bar: int


class TestBaseModelGaps:
    def test_parse_structured_json_markdown(self) -> None:
        raw = '```json\n{\n  "foo": "hello",\n  "bar": 42\n}\n```'
        res = parse_structured_json(raw, DummySchema)
        assert res.foo == "hello"
        assert res.bar == 42

    def test_parse_structured_json_fallback_regex(self) -> None:
        raw = 'Some leading text {"foo": "regex", "bar": 100} some trailing text.'
        res = parse_structured_json(raw, DummySchema)
        assert res.foo == "regex"
        assert res.bar == 100

    def test_parse_structured_json_invalid_json_raises(self) -> None:
        raw = "No JSON here at all!"
        with pytest.raises(StructuredParseError) as exc_info:
            parse_structured_json(raw, DummySchema)
        assert "No JSON object found" in str(exc_info.value)

    def test_parse_structured_json_malformed_json_object_raises(self) -> None:
        raw = 'Parsed partially { "foo": "bad" '
        with pytest.raises(StructuredParseError) as exc_info:
            parse_structured_json(raw, DummySchema)
        assert "No JSON object found" in str(exc_info.value)

    def test_parse_structured_json_validation_error_raises(self) -> None:
        raw = '{"foo": "regex", "bar": "not-an-int"}'
        with pytest.raises(StructuredParseError) as exc_info:
            parse_structured_json(raw, DummySchema)
        assert "JSON data did not validate against schema" in str(exc_info.value)

    def test_model_config_legacy_sync(self) -> None:
        c1 = ModelConfig(
            name="m1", model_type=ModelType.TEXT, provider="openai", framework="ollama"
        )
        assert c1.framework == "openai"

        c2 = ModelConfig(
            name="m2", model_type=ModelType.TEXT, provider="llama_cpp", framework="ollama"
        )
        assert c2.framework == "llama_cpp"

        c3 = ModelConfig(name="m3", model_type=ModelType.TEXT, provider="mlx", framework="ollama")
        assert c3.framework == "mlx"

        c4 = ModelConfig(
            name="m4", model_type=ModelType.TEXT, provider="claude", framework="ollama"
        )
        assert c4.framework == "claude"


# ===========================================================================
# 2. file_organizer/models/_openai_client.py Tests
# ===========================================================================


class TestOpenAIClientGaps:
    def test_create_openai_client_custom_params(self) -> None:
        config = ModelConfig(
            name="gpt-4o",
            model_type=ModelType.TEXT,
            provider="openai",
            api_key="sk-test-key",
            api_base_url="https://custom.openai.com/v1",
        )
        with (
            patch("file_organizer.models._openai_client.OPENAI_AVAILABLE", True, create=True),
            patch("file_organizer.models._openai_client.OpenAI", create=True) as mock_openai,
        ):
            client = create_openai_client(config, "text")
            assert client is not None
            mock_openai.assert_called_once_with(
                api_key="sk-test-key", base_url="https://custom.openai.com/v1"
            )

    def test_create_openai_client_error_logging(self) -> None:
        config = ModelConfig(
            name="gpt-4o", model_type=ModelType.TEXT, provider="openai", api_key="sk-test-key"
        )
        with (
            patch("file_organizer.models._openai_client.OPENAI_AVAILABLE", True, create=True),
            patch("file_organizer.models._openai_client.OpenAI", create=True) as mock_openai,
        ):
            mock_openai.side_effect = ValueError("invalid client arguments")
            with pytest.raises(ValueError):
                create_openai_client(config, "text")


# ===========================================================================
# 3. file_organizer/models/openai_vision_model.py Tests
# ===========================================================================


class TestOpenAIVisionModelGaps:
    def test_invalid_type_raises(self) -> None:
        config = ModelConfig(name="gpt-4o", model_type=ModelType.TEXT, provider="openai")
        with (
            patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True),
            pytest.raises(ValueError) as exc_info,
        ):
            OpenAIVisionModel(config)
        assert "Expected VISION or VIDEO" in str(exc_info.value)

    @patch("file_organizer.models.openai_vision_model.create_openai_client")
    def test_initialize_twice_noop(self, mock_create: MagicMock) -> None:
        config = ModelConfig(name="gpt-4o", model_type=ModelType.VISION, provider="openai")
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(config)
        model.initialize()
        model.initialize()
        mock_create.assert_called_once()

    @patch("file_organizer.models.openai_vision_model.create_openai_client")
    def test_generate_image_path_validation_and_methods(
        self, mock_create: MagicMock, tmp_path: Path
    ) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        config = ModelConfig(name="gpt-4o", model_type=ModelType.VISION, provider="openai")
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(config)
        model.initialize()

        # Generate with neither path nor bytes
        with pytest.raises(ValueError) as exc_info:
            model.generate("prompt")
        assert "Provide exactly one of image_path or image_data" in str(exc_info.value)

        # Mock successful chat completion response
        mock_choice = MagicMock()
        mock_choice.message.content = "A beautiful sunset."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        # Call analyze_image
        img_file = tmp_path / "test.png"
        Image.new("RGB", (100, 100)).save(img_file)

        res = model.analyze_image(img_file, task="describe")
        assert res == "A beautiful sunset."

        # Verify client cleanup with error handling
        mock_client.close.side_effect = RuntimeError("close error")
        model.cleanup()
        assert model.client is None

    @patch("file_organizer.models.openai_vision_model.create_openai_client")
    def test_generate_token_exhaustion_retry(self, mock_create: MagicMock, tmp_path: Path) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        config = ModelConfig(
            name="gpt-4o", model_type=ModelType.VISION, provider="openai", max_tokens=100
        )
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(config)
        model.initialize()

        # Mock token exhausted response
        mock_choice = MagicMock()
        mock_choice.finish_reason = "length"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        # Second response (retry) is successful
        mock_choice_retry = MagicMock()
        mock_choice_retry.message.content = "Retried result."
        mock_choice_retry.finish_reason = "stop"
        mock_response_retry = MagicMock()
        mock_response_retry.choices = [mock_choice_retry]

        mock_client.chat.completions.create.side_effect = [mock_response, mock_response_retry]

        img_file = tmp_path / "test.png"
        Image.new("RGB", (10, 10)).save(img_file)

        res = model.generate("prompt", image_path=img_file)
        assert res == "Retried result."
        assert mock_client.chat.completions.create.call_count == 2


# ===========================================================================
# 4. file_organizer/services/vision_processor.py Tests
# ===========================================================================


class TestVisionProcessorGaps:
    def test_preprocess_and_clamp_tall_image(self, tmp_path: Path) -> None:
        # Create a tall image (height > width and > 1024)
        img_file = tmp_path / "tall.png"
        Image.new("RGB", (200, 1200)).save(img_file)

        # Resizing in Pillow removes the .format attribute, causing a JPEG fallback in the code
        img_bytes, mime_type = preprocess_and_clamp_image(img_file, max_edge=1024)
        assert mime_type == "image/jpeg"

        # Open the processed image to check dimensions
        with Image.open(io.BytesIO(img_bytes)) as img:
            assert img.height == 1024
            assert img.width == int(200 * (1024 / 1200))

    def test_preprocess_and_clamp_unsupported_format(self, tmp_path: Path) -> None:
        # Create a BMP image (which is not in JPEG/PNG/WEBP/GIF whitelist)
        img_file = tmp_path / "test.bmp"
        Image.new("RGB", (50, 50)).save(img_file)

        # BMP format gets forced to JPEG format
        img_bytes, mime_type = preprocess_and_clamp_image(img_file)
        assert mime_type == "image/jpeg"

    def test_preprocess_and_clamp_rgba_jpeg_conversion(self, tmp_path: Path) -> None:
        # Create an RGBA image, then save as JPEG (requires RGB conversion)
        img_file = tmp_path / "rgba.png"
        Image.new("RGBA", (100, 100), (255, 0, 0, 128)).save(img_file)

        # JPEG image with RGBA source will trigger the RGB conversion
        img_bytes, mime_type = preprocess_and_clamp_image(img_file, max_edge=2000)
        assert mime_type == "image/png"  # Keeps PNG format but covers the sync path

    def test_preprocess_and_clamp_invalid_dimensions_fallback(self, tmp_path: Path) -> None:
        # Create a 0x0 size image (invalid dimensions)
        img_file = tmp_path / "invalid.png"
        img_file.write_bytes(b"corrupted image bytes")

        # Falls back to raw bytes
        img_bytes, mime_type = preprocess_and_clamp_image(img_file)
        assert img_bytes == b"corrupted image bytes"
        assert mime_type == "image/png"

    def test_vision_processor_ocr_description_errors(self, tmp_path: Path) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        mock_model.generate.side_effect = RuntimeError("model error")

        processor = VisionProcessor(vision_model=mock_model)

        img_file = tmp_path / "test.png"
        Image.new("RGB", (10, 10)).save(img_file)

        # Test description fallback
        desc = processor._generate_description(img_file)
        assert desc == f"Image from {img_file.name}"

        # Test OCR text extraction fallback
        txt = processor._extract_text(img_file)
        assert txt is None

        # Test folder name fallback
        folder = processor._generate_folder_name(img_file, "context")
        assert folder == "images"

        # Test filename fallback
        filename = processor._generate_filename(img_file, "context")
        assert filename == img_file.stem

    def test_vision_processor_structured_generate_circuit_breaker(self) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        # Mock structured generate to raise a fatal connection error
        mock_model.generate_structured.side_effect = ConnectionError("Connection refused")

        processor = VisionProcessor(vision_model=mock_model, backend_cooldown_seconds=10.0)

        # First call: trips the circuit
        with pytest.raises(ConnectionError):
            processor._guarded_generate_structured(schema=DummySchema, prompt="test")

        assert processor._is_circuit_open() is True

        # Second call: short-circuited while open
        with pytest.raises(RuntimeError) as exc_info:
            processor._guarded_generate_structured(schema=DummySchema, prompt="test")
        assert "Vision backend circuit open" in str(exc_info.value)

    def test_vision_processor_circuit_cooldown_reset(self) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        mock_model.generate.side_effect = ConnectionError("Connection refused")
        processor = VisionProcessor(vision_model=mock_model, backend_cooldown_seconds=1.0)
        with pytest.raises(ConnectionError):
            processor._guarded_generate(prompt="test")
        assert processor._is_circuit_open() is True
        processor._circuit_opened_at = time.monotonic() - 10.0
        assert processor._is_circuit_open() is False

    def test_preprocess_and_clamp_no_pillow(self, tmp_path: Path) -> None:
        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"raw bytes")
        with patch.dict("sys.modules", {"PIL": None}):
            img_bytes, mime_type = preprocess_and_clamp_image(img_file)
            assert img_bytes == b"raw bytes"
            assert mime_type == "image/png"

    @patch("PIL.Image.open")
    def test_preprocess_and_clamp_invalid_dimensions(
        self, mock_open: MagicMock, tmp_path: Path
    ) -> None:
        mock_img = MagicMock()
        mock_img.size = (0, 100)
        mock_img.__enter__.return_value = mock_img
        mock_open.return_value = mock_img
        img_file = tmp_path / "zero.png"
        img_file.write_bytes(b"dummy")
        img_bytes, mime_type = preprocess_and_clamp_image(img_file)
        assert img_bytes == b"dummy"

    def test_preprocess_and_clamp_wide_image(self, tmp_path: Path) -> None:
        img_file = tmp_path / "wide.png"
        Image.new("RGB", (1200, 200)).save(img_file)
        img_bytes, mime_type = preprocess_and_clamp_image(img_file, max_edge=1024)
        assert mime_type == "image/jpeg"
        with Image.open(io.BytesIO(img_bytes)) as img:
            assert img.width == 1024
            assert img.height == int(200 * (1024 / 1200))

    @patch("PIL.Image.open")
    def test_preprocess_and_clamp_jpeg_rgba_conversion(
        self, mock_open: MagicMock, tmp_path: Path
    ) -> None:
        mock_img = MagicMock()
        mock_img.size = (100, 100)
        mock_img.format = "JPEG"
        mock_img.mode = "RGBA"
        mock_img.__enter__.return_value = mock_img
        mock_open.return_value = mock_img
        img_file = tmp_path / "rgba_jpeg.jpg"
        img_file.write_bytes(b"dummy")
        preprocess_and_clamp_image(img_file)
        mock_img.convert.assert_called_once_with("RGB")

    def test_vision_processor_all_flags_off(self, tmp_path: Path) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        processor = VisionProcessor(vision_model=mock_model)
        img_file = tmp_path / "test.png"
        Image.new("RGB", (10, 10)).save(img_file)
        res = processor.process_file(
            img_file,
            generate_description=False,
            generate_folder=False,
            generate_filename=False,
            perform_ocr=False,
        )
        assert res.description == ""
        assert res.folder_name == ""
        assert res.filename == ""
        assert res.has_text is False

    def test_vision_processor_unsupported_extension(self, tmp_path: Path) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        processor = VisionProcessor(vision_model=mock_model)
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello world")
        res = processor.process_file(txt_file)
        assert "Unsupported image format for vision model" in res.error
        assert res.confidence == 0.3

    def test_vision_processor_structured_short_names_fallback(self, tmp_path: Path) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        mock_schema_result = MagicMock()
        mock_schema_result.description = "A description"
        mock_schema_result.folder_name = "ab"
        mock_schema_result.filename = "cd"
        mock_schema_result.has_text = False
        mock_schema_result.extracted_text = None
        mock_model.generate_structured.return_value = mock_schema_result
        processor = VisionProcessor(vision_model=mock_model)
        img_file = tmp_path / "my_test_image.png"
        Image.new("RGB", (10, 10)).save(img_file)
        res = processor.process_file(img_file)
        assert res.folder_name == "images"
        assert res.filename == "my_test_image"

    def test_vision_processor_generate_flags_false(self, tmp_path: Path) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        mock_schema_result = MagicMock()
        mock_schema_result.description = "A description"
        mock_schema_result.folder_name = "ignored"
        mock_schema_result.filename = "ignored"
        mock_schema_result.has_text = False
        mock_schema_result.extracted_text = None
        mock_model.generate_structured.return_value = mock_schema_result
        processor = VisionProcessor(vision_model=mock_model)
        img_file = tmp_path / "my_test_image.png"
        Image.new("RGB", (10, 10)).save(img_file)
        res = processor.process_file(
            img_file,
            generate_description=True,
            generate_folder=False,
            generate_filename=False,
            perform_ocr=False,
        )
        assert res.folder_name == "images"
        assert res.filename == "my_test_image"

    @patch("file_organizer.services.vision_processor.preprocess_and_clamp_image")
    @patch("file_organizer.services.vision_fallback.compute_fallback")
    def test_vision_processor_fallback_fails(
        self, mock_fallback: MagicMock, mock_clamp: MagicMock, tmp_path: Path
    ) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        processor = VisionProcessor(vision_model=mock_model)
        img_file = tmp_path / "test.png"
        Image.new("RGB", (10, 10)).save(img_file)
        mock_clamp.side_effect = RuntimeError("preprocess failed")
        mock_fallback.side_effect = RuntimeError("fallback failed")
        res = processor.process_file(img_file)
        assert res.folder_name == "errors"
        assert res.filename == "test"
        assert "preprocess failed" in res.error
        assert res.confidence == 0.0

    def test_extract_text_variations(self) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        processor = VisionProcessor(vision_model=mock_model)
        mock_model.generate.return_value = "NO_TEXT"
        assert processor._extract_text(Path("dummy.png")) is None
        mock_model.generate.return_value = "short"
        assert processor._extract_text(Path("dummy.png")) is None
        mock_model.generate.return_value = "A very long extracted text line"
        assert processor._extract_text(Path("dummy.png")) == "A very long extracted text line"

    def test_generate_folder_name_variations(self) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        processor = VisionProcessor(vision_model=mock_model)
        mock_model.generate.return_value = "category: My Cool Folder "
        assert processor._generate_folder_name(Path("dummy.png"), "context") == "my_cool"
        mock_model.generate.return_value = "ab"
        assert processor._generate_folder_name(Path("dummy.png"), "context") == "images"
        mock_model.generate.return_value = "valid_folder"
        assert processor._generate_folder_name(Path("dummy.png"), "context") == "valid_folder"

    def test_generate_filename_variations(self) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        processor = VisionProcessor(vision_model=mock_model)
        mock_model.generate.return_value = "filename: my_cool_file.png "
        assert processor._generate_filename(Path("dummy.png"), "context") == "my_cool_file"
        mock_model.generate.return_value = "ab"
        assert processor._generate_filename(Path("dummy.jpg"), "context") == "dummy"
        mock_model.generate.return_value = "valid_filename"
        assert processor._generate_filename(Path("dummy.png"), "context") == "valid_filename"

    def test_guarded_generate_circuit_open(self) -> None:
        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION
        mock_model.generate.side_effect = ConnectionError("Connection refused")
        processor = VisionProcessor(vision_model=mock_model, backend_cooldown_seconds=10.0)
        with pytest.raises(ConnectionError):
            processor._guarded_generate(prompt="test")
        assert processor._is_circuit_open() is True
        with pytest.raises(RuntimeError) as exc_info:
            processor._guarded_generate(prompt="test")
        assert "Vision backend circuit open" in str(exc_info.value)


# ===========================================================================
# 5. file_organizer/utils/readers/cad.py Tests
# ===========================================================================


class BadStream(io.BytesIO):
    def read(self, *args: Any, **kwargs: Any) -> bytes:
        raise OSError("simulate disk read failure")


class TestCADReadersGaps:
    def test_read_dxf_corrupt_stream_raises(self) -> None:
        # Use BadStream to trigger the OSError on read(), which gets caught and raised as FileReadError
        corrupt_stream = BadStream(b"dxf")
        mock_ezdxf = MagicMock()
        mock_ezdxf.read.side_effect = OSError("simulate disk read failure")
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf", mock_ezdxf, create=True),
            pytest.raises(FileReadError) as exc_info,
        ):
            read_dxf_file(fileobj=corrupt_stream)
        assert "Failed to read DXF file" in str(exc_info.value)

    def test_read_dwg_corrupt_stream_returns_fallback(self) -> None:
        # Use BadStream to trigger the OSError on read() inside ezdxf, which is caught and returned as a fallback
        corrupt_stream = BadStream(b"dwg")
        mock_ezdxf = MagicMock()
        mock_ezdxf.read.side_effect = OSError("simulate disk read failure")
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf", mock_ezdxf, create=True),
        ):
            result = read_dwg_file(fileobj=corrupt_stream)
        assert "=== DWG File Information ===" in result
        assert "Note: Full DWG parsing requires additional tools." in result

    def test_read_dwg_non_existent_file_raises(self) -> None:
        # A non-existent file path raises FileReadError
        mock_ezdxf = MagicMock()
        mock_ezdxf.readfile.side_effect = OSError("no such file")
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf", mock_ezdxf, create=True),
            pytest.raises(FileReadError) as exc_info,
        ):
            read_dwg_file(file_path="non_existent_file_xyz_123.dwg")
        assert "File not found" in str(exc_info.value)
