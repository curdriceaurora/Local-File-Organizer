"""Unit tests for OpenAIVisionModel and its image encoding helpers.

Patterns applied:
- pytestmark: unit + ci markers
- tmp_path for all file I/O (no /tmp/ paths)
- Assert mock call args exactly, not just return values
- Parametrize near-duplicate cases (task types, mime types)
- No tautological assertions
- EAFP error path tested: FileNotFoundError propagates from _image_to_data_url
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType, TokenExhaustionError
from file_organizer.models.openai_vision_model import (
    OpenAIVisionModel,
    _bytes_to_data_url,
    _image_to_data_url,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def openai_vision_config() -> ModelConfig:
    return ModelConfig(
        name="gpt-4o-mini",
        model_type=ModelType.VISION,
        provider="openai",
        api_key="sk-test",
        api_base_url=None,
    )


@pytest.fixture()
def mock_openai_client() -> MagicMock:
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = "A photo of a cat"
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


@pytest.fixture()
def sample_image(tmp_path: Path) -> Path:
    """Minimal valid-ish PNG stub (just needs to be readable bytes)."""
    img = tmp_path / "sample.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)  # PNG magic + padding
    return img


# ---------------------------------------------------------------------------
# Image encoding helpers
# ---------------------------------------------------------------------------


class TestImageToDataUrl:
    """_image_to_data_url encodes a file as a base64 data URL."""

    def test_encodes_png_with_correct_mime(self, tmp_path: Path) -> None:
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake png bytes")

        url = _image_to_data_url(img)

        assert url.startswith("data:image/png;base64,")
        payload = url.split(",", 1)[1]
        assert base64.b64decode(payload) == b"fake png bytes"

    def test_encodes_jpeg_with_correct_mime(self, tmp_path: Path) -> None:
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"fake jpeg bytes")

        url = _image_to_data_url(img)

        assert url.startswith("data:image/jpeg;base64,")

    def test_unknown_extension_falls_back_to_jpeg_mime(self, tmp_path: Path) -> None:
        img = tmp_path / "image.unknownext999"
        img.write_bytes(b"bytes")

        url = _image_to_data_url(img)

        assert url.startswith("data:image/jpeg;base64,")

    def test_raises_file_not_found_for_missing_path(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.png"

        with pytest.raises(FileNotFoundError):
            _image_to_data_url(missing)

    @pytest.mark.parametrize(
        "extension, expected_mime",
        [
            ("png", "image/png"),
            ("jpg", "image/jpeg"),
            ("jpeg", "image/jpeg"),
            ("gif", "image/gif"),
            ("webp", "image/webp"),
            ("bmp", "image/bmp"),
        ],
    )
    def test_mime_type_by_extension(
        self, tmp_path: Path, extension: str, expected_mime: str
    ) -> None:
        img = tmp_path / f"img.{extension}"
        img.write_bytes(b"x")

        url = _image_to_data_url(img)

        assert url.startswith(f"data:{expected_mime};base64,")


class TestBytesToDataUrl:
    """_bytes_to_data_url encodes raw bytes as a base64 data URL."""

    def test_encodes_bytes_with_default_mime(self) -> None:
        data = b"raw image bytes"

        url = _bytes_to_data_url(data)

        assert url.startswith("data:image/jpeg;base64,")
        payload = url.split(",", 1)[1]
        assert base64.b64decode(payload) == data

    def test_encodes_bytes_with_custom_mime(self) -> None:
        url = _bytes_to_data_url(b"data", mime_type="image/png")

        assert url.startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestOpenAIVisionModelInit:
    def test_init_sets_config(self, openai_vision_config: ModelConfig) -> None:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(openai_vision_config)
        assert model.config is openai_vision_config
        assert model.client is None
        assert not model.is_initialized

    def test_init_raises_import_error_when_openai_missing(
        self, openai_vision_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", False):
            with pytest.raises(ImportError, match="file-organizer\\[cloud\\]"):
                OpenAIVisionModel(openai_vision_config)

    def test_init_raises_value_error_for_wrong_model_type(self) -> None:
        bad_config = ModelConfig(
            name="gpt-4o",
            model_type=ModelType.TEXT,  # wrong for vision model
            provider="openai",
        )
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            with pytest.raises(ValueError, match="Expected VISION or VIDEO"):
                OpenAIVisionModel(bad_config)

    def test_init_accepts_video_model_type(self) -> None:
        cfg = ModelConfig(name="gpt-4o", model_type=ModelType.VIDEO, provider="openai")
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(cfg)
        assert model.config.model_type == ModelType.VIDEO


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


class TestOpenAIVisionModelInitialize:
    def test_initialize_creates_client_with_config_credentials(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(openai_vision_config)

        with (
            patch("file_organizer.models._openai_client.OPENAI_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._openai_client.OpenAI",
                create=True,
                return_value=mock_openai_client,
            ) as mock_cls,
        ):
            model.initialize()

        mock_cls.assert_called_once_with(
            api_key=openai_vision_config.api_key,
        )
        assert model.client is mock_openai_client
        assert model.is_initialized

    def test_initialize_is_idempotent(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(openai_vision_config)

        with (
            patch("file_organizer.models._openai_client.OPENAI_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._openai_client.OpenAI",
                create=True,
                return_value=mock_openai_client,
            ) as mock_cls,
        ):
            model.initialize()
            model.initialize()

        mock_cls.assert_called_once()


# ---------------------------------------------------------------------------
# generate() — image_path branch
# ---------------------------------------------------------------------------


class TestOpenAIVisionModelGenerateWithPath:
    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> OpenAIVisionModel:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_generate_with_image_path_calls_api(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)

        result = model.generate("Describe this image", image_path=sample_image)

        assert result == "A photo of a cat"
        mock_openai_client.chat.completions.create.assert_called_once()

    def test_generate_sends_image_as_data_url_in_messages(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)

        model.generate("Describe", image_path=sample_image)

        _, kwargs = mock_openai_client.chat.completions.create.call_args
        messages = kwargs["messages"]
        assert len(messages) == 1
        content = messages[0]["content"]
        # Content should have exactly one image_url block and one text block
        types = [block["type"] for block in content]
        assert sorted(types) == ["image_url", "text"]
        # Image url should be a base64 data URL
        image_block = next(b for b in content if b["type"] == "image_url")
        assert image_block["image_url"]["url"].startswith("data:")

    def test_generate_raises_file_not_found_for_missing_image(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)
        missing = tmp_path / "does_not_exist.png"

        with pytest.raises(FileNotFoundError):
            model.generate("prompt", image_path=missing)

    def test_generate_sends_correct_model_name(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)

        model.generate("prompt", image_path=sample_image)

        _, kwargs = mock_openai_client.chat.completions.create.call_args
        assert kwargs["model"] == openai_vision_config.name


# ---------------------------------------------------------------------------
# generate() — image_data branch
# ---------------------------------------------------------------------------


class TestOpenAIVisionModelGenerateWithBytes:
    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> OpenAIVisionModel:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_generate_with_image_data_calls_api(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)

        result = model.generate("Describe", image_data=b"fake bytes")

        assert result == "A photo of a cat"
        mock_openai_client.chat.completions.create.assert_called_once()

    def test_generate_encodes_bytes_as_data_url(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)
        raw = b"image bytes"

        model.generate("prompt", image_data=raw)

        _, kwargs = mock_openai_client.chat.completions.create.call_args
        image_block = next(b for b in kwargs["messages"][0]["content"] if b["type"] == "image_url")
        url = image_block["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        payload = url.split(",", 1)[1]
        assert base64.b64decode(payload) == raw


# ---------------------------------------------------------------------------
# generate() — guard conditions
# ---------------------------------------------------------------------------


class TestOpenAIVisionModelGenerateGuards:
    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> OpenAIVisionModel:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_raises_runtime_error_when_not_initialized(
        self, openai_vision_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(openai_vision_config)

        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("prompt", image_path=Path("/any"))

    def test_raises_value_error_when_neither_image_nor_data(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)

        with pytest.raises(ValueError, match="exactly one"):
            model.generate("prompt")

    def test_raises_value_error_when_both_provided(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)

        with pytest.raises(ValueError, match="exactly one"):
            model.generate("prompt", image_path=sample_image, image_data=b"bytes")


# ---------------------------------------------------------------------------
# analyze_image()
# ---------------------------------------------------------------------------


class TestOpenAIVisionModelAnalyzeImage:
    """analyze_image() delegates to generate() with the correct prompt."""

    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> OpenAIVisionModel:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(config)
        model.client = client
        model._initialized = True
        return model

    @pytest.mark.parametrize(
        ("task", "expected_prompt_fragment"),
        [
            ("describe", "detailed description"),
            ("categorize", "general category or theme"),
            ("ocr", "Extract all visible text"),
            ("filename", "descriptive filename"),
        ],
    )
    def test_analyze_image_calls_generate_for_each_task(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
        sample_image: Path,
        task: str,
        expected_prompt_fragment: str,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)

        result = model.analyze_image(sample_image, task=task)

        # Verify the API was called with the task-specific prompt
        mock_openai_client.chat.completions.create.assert_called_once()
        _, kwargs = mock_openai_client.chat.completions.create.call_args
        text_block = next(b for b in kwargs["messages"][0]["content"] if b["type"] == "text")
        assert expected_prompt_fragment in text_block["text"], (
            f"Expected prompt fragment {expected_prompt_fragment!r} not found for task={task!r}"
        )
        assert result == "A photo of a cat"  # from mock fixture

    def test_analyze_image_uses_custom_prompt(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(openai_vision_config, mock_openai_client)

        model.analyze_image(sample_image, task="describe", custom_prompt="My custom prompt")

        _, kwargs = mock_openai_client.chat.completions.create.call_args
        text_block = next(b for b in kwargs["messages"][0]["content"] if b["type"] == "text")
        assert text_block["text"] == "My custom prompt"


# ---------------------------------------------------------------------------
# cleanup()
# ---------------------------------------------------------------------------


class TestOpenAIVisionModelCleanup:
    def test_cleanup_resets_client_and_initialized_flag(
        self,
        openai_vision_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(openai_vision_config)
        model.client = mock_openai_client
        model._initialized = True

        model.cleanup()

        assert model.client is None
        assert not model.is_initialized


# ---------------------------------------------------------------------------
# get_default_config()
# ---------------------------------------------------------------------------


class TestOpenAIVisionModelDefaultConfig:
    def test_default_config_is_openai_provider(self) -> None:
        cfg = OpenAIVisionModel.get_default_config()
        assert cfg.provider == "openai"
        assert cfg.model_type == ModelType.VISION

    def test_default_config_model_name(self) -> None:
        cfg = OpenAIVisionModel.get_default_config()
        assert cfg.name == "gpt-4o-mini"

    def test_custom_model_name(self) -> None:
        cfg = OpenAIVisionModel.get_default_config("gpt-4o")
        assert cfg.name == "gpt-4o"


# ---------------------------------------------------------------------------
# Token exhaustion
# ---------------------------------------------------------------------------


class TestOpenAIVisionModelTokenExhaustion:
    """Token-exhaustion detection and retry in OpenAIVisionModel.generate()."""

    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> OpenAIVisionModel:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = OpenAIVisionModel(config)
        model.client = client
        model._initialized = True
        return model

    def _exhausted_response(self) -> MagicMock:
        choice = MagicMock()
        choice.finish_reason = "length"
        choice.message.content = ""
        return MagicMock(choices=[choice])

    def _success_response(self, text: str = "Good content") -> MagicMock:
        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = text
        return MagicMock(choices=[choice])

    def test_retries_on_token_exhaustion(
        self, openai_vision_config: ModelConfig, sample_image: Path
    ) -> None:
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            self._exhausted_response(),
            self._success_response(),
        ]
        model = self._make_initialized(openai_vision_config, client)

        result = model.generate("describe", image_path=sample_image)

        assert result == "Good content"
        assert client.chat.completions.create.call_count == 2
        retry_kwargs = client.chat.completions.create.call_args_list[1][1]
        assert retry_kwargs["max_tokens"] == openai_vision_config.max_tokens * 2

    def test_raises_on_double_exhaustion(
        self, openai_vision_config: ModelConfig, sample_image: Path
    ) -> None:
        client = MagicMock()
        client.chat.completions.create.return_value = self._exhausted_response()
        model = self._make_initialized(openai_vision_config, client)

        with pytest.raises(TokenExhaustionError, match="exhausted token budget"):
            model.generate("describe", image_path=sample_image)

        assert client.chat.completions.create.call_count == 2

    def test_no_retry_when_response_adequate(
        self, openai_vision_config: ModelConfig, sample_image: Path
    ) -> None:
        client = MagicMock()
        choice = MagicMock()
        choice.finish_reason = "length"
        choice.message.content = "This is a perfectly adequate response from the model"
        client.chat.completions.create.return_value = MagicMock(choices=[choice])
        model = self._make_initialized(openai_vision_config, client)

        result = model.generate("describe", image_path=sample_image)

        assert "perfectly adequate" in result
        assert client.chat.completions.create.call_count == 1
