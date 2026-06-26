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


# ===========================================================================
# 6. file_organizer/web/csrf.py Tests
# ===========================================================================


class TestWebCSRFGaps:
    def test_csrf_receive_and_decode_error(self) -> None:
        from fastapi.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import Response
        from starlette.routing import Route

        from file_organizer.web.csrf import CSRFMiddleware

        async def test_body_route(request: Request) -> Response:
            # downstream reads the body to trigger the _receive coroutine
            body = await request.body()
            return Response(content=body)

        async def get_route(request: Request) -> Response:
            return Response(content="ok")

        app = Starlette(
            routes=[
                Route("/test-body", test_body_route, methods=["POST"]),
                Route("/get-cookie", get_route, methods=["GET"]),
            ]
        )
        app.add_middleware(CSRFMiddleware)

        client = TestClient(app)

        # GET request to set cookie
        client.get("/get-cookie")
        token = client.cookies.get("_csrf_token")

        # 1. Trigger _receive on the replayed body
        res = client.post("/test-body", headers={"x-csrf-token": token}, data={"foo": "bar"})
        assert res.status_code == 200
        assert b"foo=bar" in res.content

        # 2. Trigger UnicodeDecodeError in form parsing
        # We send invalid UTF-8 bytes like b"csrf_token=\xff" and check that it's rejected (403)
        # because the decoding fails and submitted token becomes None.
        res_decode = client.post(
            "/test-body",
            content=b"csrf_token=\xff",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert res_decode.status_code == 403


# ===========================================================================
# 7. file_organizer/services/audio/metadata_extractor.py Tests
# ===========================================================================


class TestAudioMetadataExtractorGaps:
    def test_audio_metadata_extractor_static_methods(self) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        # Test format_duration
        assert AudioMetadataExtractor.format_duration(3665) == "01:01:05"
        assert AudioMetadataExtractor.format_duration(65) == "01:05"
        # Test format_bitrate
        assert AudioMetadataExtractor.format_bitrate(1200000) == "1.2 Mbps"
        assert AudioMetadataExtractor.format_bitrate(320000) == "320 kbps"
        assert AudioMetadataExtractor.format_bitrate(500) == "500 bps"

    @patch("file_organizer.services.audio.metadata_extractor.Path.exists", return_value=True)
    @patch("file_organizer.services.audio.metadata_extractor.Path.stat")
    def test_audio_metadata_extractor_mutagen_mp3(
        self, mock_stat: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_stat.return_value.st_size = 5000
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        mock_mutagen_file = MagicMock()
        mock_audio = MagicMock()
        mock_audio.info.length = 180.0
        mock_audio.info.bitrate = 320000
        mock_audio.info.sample_rate = 44100
        mock_audio.info.channels = 2
        mock_audio.info.codec = "mp3"

        # MP3 ID3 tags
        mock_audio.tags = {
            "TIT2": ["Song Title"],
            "TPE1": ["Artist Name"],
            "TALB": ["Album Name"],
            "TPE2": ["Album Artist"],
            "TCON": ["Pop"],
            "TDRC": ["2024-10-12"],
            "TRCK": ["3/12"],
            "TPOS": ["1/2"],
            "COMM": ["Nice song"],
            "TENC": ["Lame"],
            "APIC:cover": "artwork_data",
        }
        mock_mutagen_file.return_value = mock_audio

        with (
            patch.dict("sys.modules", {"mutagen": MagicMock(File=mock_mutagen_file)}),
            patch(
                "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor._check_artwork_mutagen",
                return_value=(True, 1),
            ),
        ):
            extractor = AudioMetadataExtractor(use_fallback=True)
            meta = extractor.extract("dummy.mp3")
            assert meta.title == "Song Title"
            assert meta.artist == "Artist Name"
            assert meta.album == "Album Name"
            assert meta.album_artist == "Album Artist"
            assert meta.genre == "Pop"
            assert meta.year == 2024
            assert meta.track_number == 3
            assert meta.disc_number == 1
            assert meta.comment == "Nice song"
            assert meta.encoder == "Lame"
            assert meta.has_artwork is True
            assert meta.artwork_count == 1

    @patch("file_organizer.services.audio.metadata_extractor.Path.exists", return_value=True)
    @patch("file_organizer.services.audio.metadata_extractor.Path.stat")
    def test_audio_metadata_extractor_mutagen_vorbis_and_mp4(
        self, mock_stat: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_stat.return_value.st_size = 6000
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        # Test Vorbis comment list extraction
        mock_audio_vorbis = MagicMock()
        mock_audio_vorbis.info.length = 200.0
        mock_audio_vorbis.tags = {
            "title": ["Vorbis Title"],
            "artist": ["Vorbis Artist"],
            "album": ["Vorbis Album"],
            "date": ["2025"],
            "tracknumber": ["5"],
            "discnumber": ["2"],
            "unmapped_tag": ["unmapped_value"],
        }

        # Test MP4 tuple track numbers and covr artwork
        mock_audio_mp4 = MagicMock()
        mock_audio_mp4.info.length = 150.0
        mock_audio_mp4.tags = {
            "©nam": ["MP4 Title"],
            "trkn": [(4, 10)],
            "disk": [(1, 2)],
            "covr": ["cover_data"],
        }

        mock_mutagen_file = MagicMock(side_effect=[mock_audio_vorbis, mock_audio_mp4])

        with patch.dict("sys.modules", {"mutagen": MagicMock(File=mock_mutagen_file)}):
            extractor = AudioMetadataExtractor(use_fallback=True)

            # 1. Vorbis
            meta_vorbis = extractor.extract("dummy.flac")
            assert meta_vorbis.title == "Vorbis Title"
            assert meta_vorbis.year == 2025
            assert meta_vorbis.track_number == 5
            assert meta_vorbis.disc_number == 2
            assert meta_vorbis.extra_tags["unmapped_tag"] == "['unmapped_value']"

            # 2. MP4
            meta_mp4 = extractor.extract("dummy.m4a")
            assert meta_mp4.title == "MP4 Title"
            assert meta_mp4.track_number == 4
            assert meta_mp4.disc_number == 1

    @patch("file_organizer.services.audio.metadata_extractor.Path.exists", return_value=True)
    @patch("file_organizer.services.audio.metadata_extractor.Path.stat")
    def test_audio_metadata_extractor_fallback_tinytag(
        self, mock_stat: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_stat.return_value.st_size = 7000
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        # Mutagen fails, fall back to tinytag
        mock_tinytag = MagicMock()
        mock_tag = MagicMock()
        mock_tag.duration = 120.0
        mock_tag.bitrate = 192000
        mock_tag.samplerate = 44100
        mock_tag.channels = 2
        mock_tag.title = "Tiny Title"
        mock_tag.artist = "Tiny Artist"
        mock_tag.album = "Tiny Album"
        mock_tag.albumartist = "Tiny Album Artist"
        mock_tag.genre = "Rock"
        mock_tag.year = "2023-05-06"
        mock_tag.track = "12/20"
        mock_tag.disc = "1/2"
        mock_tag.comment = "Tiny comment"
        mock_tinytag.TinyTag.get.return_value = mock_tag

        with (
            patch.dict("sys.modules", {"mutagen": None, "tinytag": mock_tinytag}),
            patch("file_organizer.services.audio.metadata_extractor.logger.warning"),
        ):
            extractor = AudioMetadataExtractor(use_fallback=True)
            meta = extractor.extract("dummy.mp3")
            assert meta.title == "Tiny Title"
            assert meta.artist == "Tiny Artist"
            assert meta.year == 2023
            assert meta.track_number == 12
            assert meta.disc_number == 1

            # Test tinytag not installed raising ImportError
            with patch.dict("sys.modules", {"tinytag": None}):
                with pytest.raises(ImportError) as exc_info:
                    extractor.extract("dummy.mp3")
                assert "tinytag is required" in str(exc_info.value)

            # Test no fallback raises mutagen error
            extractor_no_fallback = AudioMetadataExtractor(use_fallback=False)
            with pytest.raises(ImportError) as exc_info:
                extractor_no_fallback.extract("dummy.mp3")
            assert "mutagen is required" in str(exc_info.value)

    def test_audio_metadata_extractor_file_not_found(self) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        extractor = AudioMetadataExtractor()
        with pytest.raises(FileNotFoundError):
            extractor.extract("non_existent_audio_file_xyz_123.mp3")

    @patch("file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor.extract")
    def test_audio_metadata_extractor_batch(self, mock_extract: MagicMock) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        extractor = AudioMetadataExtractor()

        mock_extract.side_effect = [MagicMock(), RuntimeError("fail"), MagicMock()]
        res = extractor.extract_batch(["a.mp3", "b.mp3", "c.mp3"])
        assert len(res) == 2


# ===========================================================================
# 8. file_organizer/services/video/metadata_extractor.py Tests
# ===========================================================================


class TestVideoMetadataExtractorGaps:
    def test_video_metadata_extractor_resolution_label(self) -> None:
        from file_organizer.services.video.metadata_extractor import resolution_label

        assert resolution_label(None, 100) == "unknown"
        assert resolution_label(3840, 2160) == "4k"
        assert resolution_label(1920, 1080) == "1080p"
        assert resolution_label(1280, 720) == "720p"
        assert resolution_label(854, 480) == "480p"
        assert resolution_label(640, 360) == "sd"

    @patch("file_organizer.services.video.metadata_extractor.Path.exists", return_value=True)
    @patch("file_organizer.services.video.metadata_extractor.Path.stat")
    @patch("file_organizer.services.video.metadata_extractor.subprocess.run")
    def test_video_metadata_extractor_ffprobe_success(
        self, mock_run: MagicMock, mock_stat: MagicMock, mock_exists: MagicMock
    ) -> None:
        import json

        mock_stat.return_value.st_size = 12000
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        probe_data = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30000/1001",
                    "duration": "12.34",
                }
            ],
            "format": {"bit_rate": "5000000", "tags": {"creation_time": "2024-01-15T14:30:45Z"}},
        }
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(probe_data))

        extractor = VideoMetadataExtractor()
        meta = extractor.extract(Path("dummy.mp4"))
        assert meta.width == 1920
        assert meta.height == 1080
        assert meta.codec == "h264"
        assert meta.fps == 29.97
        assert meta.duration == 12.34
        assert meta.bitrate == 5000000
        assert meta.creation_date is not None

    @patch("file_organizer.services.video.metadata_extractor.Path.exists", return_value=True)
    @patch("file_organizer.services.video.metadata_extractor.Path.stat")
    @patch("file_organizer.services.video.metadata_extractor.subprocess.run")
    def test_video_metadata_extractor_ffprobe_date_parsing_variations(
        self, mock_run: MagicMock, mock_stat: MagicMock, mock_exists: MagicMock
    ) -> None:
        import json

        mock_stat.return_value.st_size = 12000
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        # 1. Date only
        probe_data_1 = {"format": {"tags": {"date": "2025-06-15"}}}
        # 2. Year only
        probe_data_2 = {"format": {"tags": {"date": "2026"}}}
        # 3. YYYY-MM-DD HH:MM:SS
        probe_data_3 = {"format": {"tags": {"date": "2024-02-20 18:00:00"}}}

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(probe_data_1)),
            MagicMock(returncode=0, stdout=json.dumps(probe_data_2)),
            MagicMock(returncode=0, stdout=json.dumps(probe_data_3)),
        ]

        extractor = VideoMetadataExtractor()

        meta1 = extractor.extract(Path("dummy.mp4"))
        assert meta1.creation_date.year == 2025
        assert meta1.creation_date.month == 6

        meta2 = extractor.extract(Path("dummy.mp4"))
        assert meta2.creation_date.year == 2026

        meta3 = extractor.extract(Path("dummy.mp4"))
        assert meta3.creation_date.year == 2024
        assert meta3.creation_date.hour == 18

    @patch("file_organizer.services.video.metadata_extractor.Path.exists", return_value=True)
    @patch("file_organizer.services.video.metadata_extractor.Path.stat")
    @patch("file_organizer.services.video.metadata_extractor.subprocess.run")
    def test_video_metadata_extractor_opencv_fallback(
        self, mock_run: MagicMock, mock_stat: MagicMock, mock_exists: MagicMock
    ) -> None:
        import subprocess

        mock_stat.return_value.st_size = 8000
        # ffprobe fails
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["ffprobe"], timeout=10)
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            mock_cv2.CAP_PROP_FRAME_WIDTH: 1280.0,
            mock_cv2.CAP_PROP_FRAME_HEIGHT: 720.0,
            mock_cv2.CAP_PROP_FPS: 24.0,
            mock_cv2.CAP_PROP_FRAME_COUNT: 240.0,
        }.get(prop, 0.0)
        mock_cv2.VideoCapture.return_value = mock_cap

        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            extractor = VideoMetadataExtractor()
            meta = extractor.extract(Path("dummy.mp4"))
            assert meta.width == 1280
            assert meta.height == 720
            assert meta.fps == 24.0
            assert meta.duration == 10.0
            mock_cap.release.assert_called_once()

            # Test OpenCV failure in VideoCapture
            mock_cap_fail = MagicMock()
            mock_cap_fail.isOpened.return_value = False
            mock_cv2.VideoCapture.return_value = mock_cap_fail
            meta_fail = extractor.extract(Path("dummy.mp4"))
            assert meta_fail.width is None

    def test_video_metadata_extractor_file_not_found(self) -> None:
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        extractor = VideoMetadataExtractor()
        with pytest.raises(FileNotFoundError):
            extractor.extract(Path("non_existent_video_file_xyz_123.mp4"))


# ===========================================================================
# 9. file_organizer/utils/epub_enhanced.py Tests
# ===========================================================================


class TestEpubEnhancedGaps:
    def test_epub_enhanced_import_errors(self) -> None:
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", False),
            pytest.raises(ImportError),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            EnhancedEPUBReader()

        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", False),
            pytest.raises(ImportError),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            EnhancedEPUBReader()

    def test_epub_enhanced_word_to_number_and_clean_isbn(self) -> None:
        from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
        ):
            reader = EnhancedEPUBReader()
            assert reader._word_to_number("second") == 2
            assert reader._word_to_number("invalid") is None
            assert reader._clean_isbn("978-3-16-148410-0") == "9783161484100"

    @patch("file_organizer.utils.epub_enhanced.Path.exists", return_value=True)
    def test_epub_enhanced_reader_workflow(self, mock_exists: MagicMock) -> None:
        from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

        mock_book = MagicMock()
        mock_book.version = "3.0"

        # Metadata stub
        def get_metadata_stub(namespace, name):
            if name == "title":
                return [("The Great Book: Book Two", {})]
            if name == "creator":
                return [("Jane Doe", {})]
            if name == "identifier":
                return [("urn:uuid:12345", {}), ("isbn:9781234567890", {"scheme": "ISBN"})]
            return []

        mock_book.get_metadata.side_effect = get_metadata_stub

        mock_item = MagicMock()
        mock_item.get_type.return_value = 9
        mock_item.get_content.return_value = b"<html><head><title>Chapter 1</title></head><body><h1>Chapter One</h1><p>This is the first chapter paragraph.</p></body></html>"
        mock_item.file_name = "chapter_1.xhtml"
        mock_book.get_items.return_value = [mock_item]

        mock_ebooklib = MagicMock()
        mock_ebooklib.ITEM_DOCUMENT = 9

        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.ebooklib", mock_ebooklib, create=True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced._read_epub_safedir", return_value=mock_book),
        ):
            reader = EnhancedEPUBReader()
            content = reader.read_epub("dummy.epub", extract_cover=False)
            assert content.metadata.title == "The Great Book: Book Two"
            assert content.metadata.authors == ["Jane Doe"]
            assert content.metadata.series == "The Great Book"
            assert content.metadata.series_index == 2.0
            assert content.metadata.isbn == "9781234567890"
            assert content.total_chapters == 1
            assert "This is the first chapter paragraph." in content.raw_text

    @patch("file_organizer.utils.epub_enhanced.Path.exists", return_value=True)
    def test_epub_enhanced_cover_extraction_pillow_unavailable(
        self, mock_exists: MagicMock
    ) -> None:
        from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

        mock_book = MagicMock()
        mock_book.get_metadata.return_value = [("cover_id", {})]
        mock_cover_item = MagicMock()
        mock_cover_item.get_type.return_value = 12
        mock_cover_item.get_content.return_value = b"cover_image_bytes"
        mock_book.get_item_with_id.return_value = mock_cover_item

        mock_ebooklib = MagicMock()
        mock_ebooklib.ITEM_COVER = 12

        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.ebooklib", mock_ebooklib, create=True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.PILLOW_AVAILABLE", False),
            patch("file_organizer.utils.epub_enhanced._read_epub_safedir", return_value=mock_book),
            patch("file_organizer.utils.epub_enhanced.logger.warning") as mock_warn,
        ):
            reader = EnhancedEPUBReader()
            content = reader.read_epub("dummy.epub", extract_cover=True)
            assert content.metadata.cover_path is None
            mock_warn.assert_called_with("Pillow not available, cannot extract cover image")

    @patch("file_organizer.utils.epub_enhanced.sys.platform", "win32")
    @patch("file_organizer.utils.epub_enhanced.Path.is_symlink", return_value=True)
    def test_read_epub_legacy_checked_symlink_raises(self, mock_is_symlink: MagicMock) -> None:
        from file_organizer.utils.epub_enhanced import _read_epub_legacy_checked
        from file_organizer.utils.safedir import SymlinkRejected

        with pytest.raises(SymlinkRejected):
            _read_epub_legacy_checked(Path("dummy.epub"))


# ===========================================================================
# 10. file_organizer/utils/readers/ebook.py Tests
# ===========================================================================


class TestEbookReaderGaps:
    def test_read_ebook_file_arg_validation(self) -> None:
        from file_organizer.utils.readers.ebook import read_ebook_file

        with pytest.raises(ValueError) as exc_info:
            read_ebook_file(None, None)
        assert "requires file_path or fileobj" in str(exc_info.value)

    def test_read_ebook_file_import_error(self) -> None:
        from file_organizer.utils.readers.ebook import read_ebook_file

        with (
            patch("file_organizer.utils.readers.ebook.EBOOKLIB_AVAILABLE", False),
            pytest.raises(ImportError) as exc_info,
        ):
            read_ebook_file("dummy.epub")
        assert "ebooklib is not installed" in str(exc_info.value)

    @patch("file_organizer.utils.readers.ebook.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.ebook._check_file_size")
    def test_read_ebook_file_unsupported_format(
        self, mock_size: MagicMock, mock_exists: MagicMock
    ) -> None:
        from file_organizer.utils.readers.ebook import read_ebook_file

        with (
            patch("file_organizer.utils.readers.ebook.EBOOKLIB_AVAILABLE", True),
            pytest.raises(FileReadError) as exc_info,
        ):
            read_ebook_file("dummy.pdf")
        assert "Unsupported ebook format" in str(exc_info.value)

    @patch("file_organizer.utils.readers.ebook.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.ebook._check_file_size")
    def test_read_ebook_file_parse(self, mock_size: MagicMock, mock_exists: MagicMock) -> None:
        from file_organizer.utils.readers.ebook import read_ebook_file

        mock_book = MagicMock()
        mock_item = MagicMock()
        mock_item.get_type.return_value = 9
        mock_item.get_content.return_value = b"<html><body><p>Ebook Paragraph</p></body></html>"
        mock_book.get_items.return_value = [mock_item]

        mock_ebooklib = MagicMock()
        mock_ebooklib.ITEM_DOCUMENT = 9
        mock_epub = MagicMock()
        mock_epub.read_epub.return_value = mock_book

        with (
            patch("file_organizer.utils.readers.ebook.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.readers.ebook.ebooklib", mock_ebooklib, create=True),
            patch("file_organizer.utils.readers.ebook.epub", mock_epub, create=True),
        ):
            # Test path-based parse
            text = read_ebook_file("dummy.epub", max_chars=100)
            assert text == "Ebook Paragraph"

            # Test fileobj-based parse
            mock_fileobj = MagicMock()
            text_fileobj = read_ebook_file("dummy.epub", fileobj=mock_fileobj)
            assert text_fileobj == "Ebook Paragraph"


# ===========================================================================
# 11. file_organizer/utils/readers/documents.py Tests
# ===========================================================================


class TestDocumentReadersGaps:
    def test_read_text_file_arg_validation(self) -> None:
        from file_organizer.utils.readers.documents import read_text_file

        with pytest.raises(ValueError) as exc_info:
            read_text_file(None)
        assert "requires file_path or fileobj" in str(exc_info.value)

    @patch("file_organizer.utils.readers.documents.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.documents._check_file_size")
    @patch("file_organizer.utils.readers.documents.Path.open")
    def test_read_docx_file_workflow(
        self, mock_open: MagicMock, mock_size: MagicMock, mock_exists: MagicMock
    ) -> None:
        import io

        from file_organizer.utils.readers.documents import read_docx_file

        # Test DOCX import error
        with (
            patch("file_organizer.utils.readers.documents.DOCX_AVAILABLE", False),
            pytest.raises(ImportError),
        ):
            read_docx_file("dummy.docx")

        # Test DOCX success
        mock_doc = MagicMock()
        mock_para = MagicMock()
        mock_para.text = "Docx text line"
        mock_doc.paragraphs = [mock_para]

        mock_open.return_value.__enter__.return_value = io.BytesIO(b"docx content")

        with (
            patch("file_organizer.utils.readers.documents.DOCX_AVAILABLE", True),
            patch("file_organizer.utils.readers.documents.docx.Document", return_value=mock_doc),
        ):
            text = read_docx_file("dummy.docx")
            assert text == "Docx text line"

    @patch("file_organizer.utils.readers.documents.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.documents._check_file_size")
    def test_read_pdf_file_workflow(self, mock_size: MagicMock, mock_exists: MagicMock) -> None:
        from file_organizer.utils.readers.documents import read_pdf_file

        # Test PDF import error
        with (
            patch("file_organizer.utils.readers.documents.PYMUPDF_AVAILABLE", False),
            pytest.raises(ImportError),
        ):
            read_pdf_file("dummy.pdf")

        # Test PDF success
        mock_doc = MagicMock()
        mock_doc.__enter__.return_value = mock_doc
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_page.get_text.return_value = "PDF text content"
        mock_doc.load_page.return_value = mock_page

        with (
            patch("file_organizer.utils.readers.documents.PYMUPDF_AVAILABLE", True),
            patch("file_organizer.utils.readers.documents.fitz.open", return_value=mock_doc),
        ):
            text = read_pdf_file("dummy.pdf")
            assert text == "PDF text content"

    @patch("file_organizer.utils.readers.documents.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.documents._check_file_size")
    @patch("file_organizer.utils.readers.documents.Path.open")
    def test_read_spreadsheet_file_workflow(
        self, mock_open: MagicMock, mock_size: MagicMock, mock_exists: MagicMock
    ) -> None:
        import io

        from file_organizer.utils.readers.documents import read_spreadsheet_file

        # Test spreadsheet arg validation
        with pytest.raises(ValueError):
            read_spreadsheet_file(None)

        # Test unsupported format
        with pytest.raises(FileReadError) as exc_info:
            read_spreadsheet_file("dummy.xls", fileobj=io.BytesIO(b""))
        assert "Unsupported spreadsheet format" in str(exc_info.value)

        # Test Excel import error
        with (
            patch("file_organizer.utils.readers.documents.OPENPYXL_AVAILABLE", False),
            pytest.raises(ImportError),
        ):
            read_spreadsheet_file("dummy.xlsx")

        # Test Excel success
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [("col1", "col2"), ("val1", "val2")]
        mock_wb.active = mock_ws

        mock_open.return_value.__enter__.return_value = io.BytesIO(b"spreadsheet content")

        with (
            patch("file_organizer.utils.readers.documents.OPENPYXL_AVAILABLE", True),
            patch(
                "file_organizer.utils.readers.documents.openpyxl.load_workbook",
                return_value=mock_wb,
            ),
        ):
            text = read_spreadsheet_file("dummy.xlsx")
            assert "col1,col2" in text
            assert "val1,val2" in text

    @patch("file_organizer.utils.readers.documents.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.documents._check_file_size")
    @patch("file_organizer.utils.readers.documents.Path.open")
    def test_read_presentation_file_workflow(
        self, mock_open: MagicMock, mock_size: MagicMock, mock_exists: MagicMock
    ) -> None:
        import io

        from file_organizer.utils.readers.documents import read_presentation_file

        # Test PPTX import error
        with (
            patch("file_organizer.utils.readers.documents.PPTX_AVAILABLE", False),
            pytest.raises(ImportError),
        ):
            read_presentation_file("dummy.pptx")

        # Test PPTX success
        mock_prs = MagicMock()
        mock_slide = MagicMock()
        mock_shape = MagicMock()
        mock_shape.text = "Slide text content"
        mock_slide.shapes = [mock_shape]
        mock_prs.slides = [mock_slide]

        mock_open.return_value.__enter__.return_value = io.BytesIO(b"pptx content")

        with (
            patch("file_organizer.utils.readers.documents.PPTX_AVAILABLE", True),
            patch("file_organizer.utils.readers.documents.Presentation", return_value=mock_prs),
        ):
            text = read_presentation_file("dummy.pptx")
            assert "Slide 1: Slide text content" in text


# ===========================================================================
# 12. file_organizer/optimization/buffer_pool.py Tests
# ===========================================================================


class TestBufferPoolGaps:
    def test_buffer_pool_init_validation(self) -> None:
        from file_organizer.optimization.buffer_pool import BufferPool

        with pytest.raises(ValueError, match="buffer_size must be > 0"):
            BufferPool(buffer_size=0)
        with pytest.raises(ValueError, match="initial_buffers must be > 0"):
            BufferPool(initial_buffers=0)
        with pytest.raises(ValueError, match="max_buffers .* must be >= initial_buffers"):
            BufferPool(initial_buffers=5, max_buffers=3)

    def test_buffer_pool_utilization_zero(self) -> None:
        from file_organizer.optimization.buffer_pool import BufferPool

        pool = BufferPool(initial_buffers=1)
        # Force total_buffers to 0 to trigger line 97
        pool._total_buffers = 0
        assert pool.utilization == 0.0

    def test_buffer_pool_acquire_validation_and_oversize(self) -> None:
        from file_organizer.optimization.buffer_pool import BufferPool

        pool = BufferPool(buffer_size=10, initial_buffers=2)
        with pytest.raises(ValueError, match="size must be > 0"):
            pool.acquire(size=0)

        # Oversize buffer (lines 114-116)
        buf = pool.acquire(size=20)
        assert len(buf) == 20
        assert pool.in_use_count == 1
        pool.release(buf)
        assert pool.in_use_count == 0

    def test_buffer_pool_grow_and_timeout(self) -> None:
        from file_organizer.optimization.buffer_pool import BufferPool

        # Pool with initial=1, max=2
        pool = BufferPool(buffer_size=10, initial_buffers=1, max_buffers=2)

        # Acquire the only available buffer
        buf1 = pool.acquire()
        assert len(buf1) == 10
        assert pool.total_buffers == 1

        # Acquire second buffer: grows the pool (lines 123-128)
        buf2 = pool.acquire()
        assert len(buf2) == 10
        assert pool.total_buffers == 2

        # Try to acquire third buffer: must wait or timeout
        with pytest.raises(ValueError, match="timeout must be >= 0"):
            pool.acquire(timeout=-1)

        with pytest.raises(TimeoutError, match="Timed out waiting"):
            pool.acquire(timeout=0.01)

    def test_buffer_pool_release_validation_and_resize(self) -> None:
        from file_organizer.optimization.buffer_pool import BufferPool

        pool = BufferPool(buffer_size=10, initial_buffers=2)

        # Release invalid buffer
        with pytest.raises(ValueError, match="Attempted to release a buffer not owned"):
            pool.release(bytearray(10))

        # Release a pooled buffer whose length is NOT buffer_size (lines 166-170)
        buf = pool.acquire()
        buf.append(1)  # change length
        pool.release(buf)
        assert pool.total_buffers == 1

        # Resize validation
        with pytest.raises(ValueError, match="target_total_buffers must be > 0"):
            pool.resize(0)


# ===========================================================================
# 13. file_organizer/utils/readers/cad.py Tests
# ===========================================================================


class TestCADReaderGaps:
    @patch("file_organizer.utils.readers.cad.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.cad._check_file_size")
    @patch("file_organizer.utils.readers.cad.Path.stat")
    @patch("file_organizer.utils.readers.cad.Path.open")
    def test_read_cad_file_dispatch_and_unsupported(
        self,
        mock_open: MagicMock,
        mock_stat: MagicMock,
        mock_size: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        import io

        from file_organizer.utils.readers.cad import read_cad_file

        # Test unsupported format
        with pytest.raises(FileReadError, match="Unsupported CAD file format"):
            read_cad_file("dummy.xyz")

        # Test STEP path branch dispatch
        mock_stat.return_value.st_size = 1024
        mock_open.return_value.__enter__.return_value = io.StringIO(
            "HEADER;FILE_DESCRIPTION('STEP file');ENDSEC;DATA;\n#1\n#2"
        )
        res = read_cad_file("dummy.step")
        assert "STEP File Information" in res
        assert "Approximate entity count: 2" in res

    @patch("file_organizer.utils.readers.cad.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.cad._check_file_size")
    @patch("file_organizer.utils.readers.cad.Path.open")
    def test_read_dxf_file_edge_cases(
        self, mock_open: MagicMock, mock_size: MagicMock, mock_exists: MagicMock
    ) -> None:

        mock_doc = MagicMock()
        mock_doc.dxfversion = "AC1015"
        mock_doc.layers = [MagicMock() for _ in range(5)]
        for i, layer in enumerate(mock_doc.layers):
            layer.dxf.name = f"layer_{i}"
            layer.dxf.color = i

        # 1. Test empty author fallback and max_layers limit
        def mock_header_get(var, default=""):
            if var == "$TITLE":
                return "My DXF"
            if var == "$AUTHOR":
                return ""
            if var == "$LASTSAVEDBY":
                return "SavedByAuthor"
            return default

        mock_doc.header.get.side_effect = mock_header_get

        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf.readfile", return_value=mock_doc),
        ):
            res = read_dxf_file("dummy.dxf", max_layers=2)
            assert "Author: SavedByAuthor" in res
            assert "... and 3 more layers" in res

        # 2. Test exceptions in header reads
        mock_doc.header.get.side_effect = Exception("Header read error")
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf.readfile", return_value=mock_doc),
        ):
            res = read_dxf_file("dummy.dxf")
            assert "DXF Version: AC1015" in res

        # 3. Test ezdxf Import error
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", False),
            pytest.raises(ImportError, match="ezdxf is not installed"),
        ):
            read_dxf_file("dummy.dxf")

    @patch("file_organizer.utils.readers.cad.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.cad._check_file_size")
    @patch("file_organizer.utils.readers.cad.Path.stat")
    def test_read_dwg_file_path_branch_and_fallback(
        self, mock_stat: MagicMock, mock_size: MagicMock, mock_exists: MagicMock
    ) -> None:
        from file_organizer.utils.readers.cad import read_dwg_file

        mock_stat.return_value.st_size = 2048

        # Test ezdxf fails on DWG, falls back to basic file info
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch(
                "file_organizer.utils.readers.cad.ezdxf.readfile",
                side_effect=Exception("DWG read error"),
            ),
        ):
            res = read_dwg_file("dummy.dwg")
            assert "=== DWG File Information ===" in res
            assert "Size: 2.00 KB" in res

    @patch("file_organizer.utils.readers.cad.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.cad._check_file_size")
    @patch("file_organizer.utils.readers.cad.Path.stat")
    @patch("file_organizer.utils.readers.cad.Path.open")
    def test_read_step_file_path_branch_and_exception(
        self,
        mock_open: MagicMock,
        mock_stat: MagicMock,
        mock_size: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        import io

        from file_organizer.utils.readers.cad import read_step_file

        # 1. Test step path branch success
        mock_stat.return_value.st_size = 1024
        mock_open.return_value.__enter__.return_value = io.StringIO(
            "HEADER;FILE_NAME('my_step');ENDSEC;DATA;\n#1"
        )
        res = read_step_file("dummy.step")
        assert "FILE_NAME('my_step')" in res

        # 2. Test exception handling
        mock_open.side_effect = OSError("Read failed")
        with pytest.raises(FileReadError, match="Failed to read STEP file"):
            read_step_file("dummy.step")

    @patch("file_organizer.utils.readers.cad.Path.exists", return_value=True)
    @patch("file_organizer.utils.readers.cad._check_file_size")
    @patch("file_organizer.utils.readers.cad.Path.stat")
    @patch("file_organizer.utils.readers.cad.Path.open")
    def test_read_iges_file_path_branch_and_exception(
        self,
        mock_open: MagicMock,
        mock_stat: MagicMock,
        mock_size: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        import io

        from file_organizer.utils.readers.cad import read_iges_file

        # 1. Test iges path branch success
        mock_stat.return_value.st_size = 1024
        iges_content = (
            "Start section text"
            + " " * 54
            + "S      1\nGlobal parameters"
            + " " * 55
            + "G      1\n"
        )
        mock_open.return_value.__enter__.return_value = io.StringIO(iges_content)
        res = read_iges_file("dummy.iges")
        assert "=== Start Section ===" in res
        assert "=== Global Parameters ===" in res

        # 2. Test exception handling
        mock_open.side_effect = OSError("Read failed")
        with pytest.raises(FileReadError, match="Failed to read IGES file"):
            read_iges_file("dummy.iges")
