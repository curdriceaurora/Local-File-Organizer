"""Unit tests for ClaudeVisionModel and image block encoding.

Patterns applied:
- pytestmark: unit + ci markers
- tmp_path for all file I/O
- Assert mock call args exactly
- Parametrize near-duplicate cases
- Verify Claude-specific image block format: source.base64, not image_url
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType, TokenExhaustionError
from file_organizer.models.claude_vision_model import ClaudeVisionModel, _build_image_block

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    name: str = "claude-3-5-sonnet-20241022",
    api_key: str | None = "sk-ant-test",
) -> ModelConfig:
    return ModelConfig(
        name=name,
        model_type=ModelType.VISION,
        provider="claude",
        api_key=api_key,
    )


def _make_client(text: str = "A photo of a cat") -> MagicMock:
    client = MagicMock()
    text_block = MagicMock()
    text_block.text = text
    client.messages.create.return_value = MagicMock(content=[text_block], stop_reason="end_turn")
    return client


def _exhausted_response(text: str = "") -> MagicMock:
    text_block = MagicMock()
    text_block.text = text
    return MagicMock(content=[text_block], stop_reason="max_tokens")


def _success_response(text: str = "Good content") -> MagicMock:
    text_block = MagicMock()
    text_block.text = text
    return MagicMock(content=[text_block], stop_reason="end_turn")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def claude_vision_config() -> ModelConfig:
    return _make_config()


@pytest.fixture()
def mock_claude_client() -> MagicMock:
    return _make_client()


@pytest.fixture()
def sample_image(tmp_path: Path) -> Path:
    """Minimal PNG stub — just needs to be readable bytes."""
    img = tmp_path / "sample.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    return img


# ---------------------------------------------------------------------------
# _build_image_block()
# ---------------------------------------------------------------------------


class TestBuildImageBlock:
    """_build_image_block converts a data URL to a Claude image content block."""

    def test_produces_base64_source_type(self) -> None:
        data_url = "data:image/png;base64," + base64.b64encode(b"fake").decode()
        block = _build_image_block(data_url)
        assert block["type"] == "image"
        assert block["source"]["type"] == "base64"

    def test_extracts_correct_mime_type(self) -> None:
        data_url = "data:image/webp;base64," + base64.b64encode(b"x").decode()
        block = _build_image_block(data_url)
        assert block["source"]["media_type"] == "image/webp"

    def test_extracts_correct_base64_data(self) -> None:
        raw = b"image content"
        b64 = base64.b64encode(raw).decode()
        data_url = f"data:image/jpeg;base64,{b64}"
        block = _build_image_block(data_url)
        assert block["source"]["data"] == b64

    @pytest.mark.parametrize(
        "mime",
        ["image/jpeg", "image/png", "image/gif", "image/webp"],
    )
    def test_handles_various_mime_types(self, mime: str) -> None:
        data_url = f"data:{mime};base64," + base64.b64encode(b"x").decode()
        block = _build_image_block(data_url)
        assert block["source"]["media_type"] == mime

    def test_raises_on_invalid_data_url(self) -> None:
        with pytest.raises(ValueError, match="valid base64 data URL"):
            _build_image_block("not-a-data-url")


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestClaudeVisionModelInit:
    def test_init_sets_config(self, claude_vision_config: ModelConfig) -> None:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(claude_vision_config)
        assert model.config is claude_vision_config
        assert model.client is None
        assert not model.is_initialized

    def test_init_raises_import_error_when_anthropic_missing(
        self, claude_vision_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", False):
            with pytest.raises(ImportError, match="file-organizer\\[claude\\]"):
                ClaudeVisionModel(claude_vision_config)

    def test_init_raises_value_error_for_wrong_model_type(self) -> None:
        bad_config = ModelConfig(
            name="claude-3-5-sonnet-20241022",
            model_type=ModelType.TEXT,  # wrong
            provider="claude",
        )
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            with pytest.raises(ValueError, match="Expected VISION or VIDEO"):
                ClaudeVisionModel(bad_config)

    def test_init_accepts_video_model_type(self) -> None:
        cfg = ModelConfig(
            name="claude-3-5-sonnet-20241022", model_type=ModelType.VIDEO, provider="claude"
        )
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(cfg)
        assert model.config.model_type == ModelType.VIDEO


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


class TestClaudeVisionModelInitialize:
    def test_initialize_creates_client(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(claude_vision_config)

        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._claude_client.Anthropic",
                create=True,
                return_value=mock_claude_client,
            ) as mock_cls,
        ):
            model.initialize()

        mock_cls.assert_called_once_with(api_key=claude_vision_config.api_key)
        assert model.client is mock_claude_client
        assert model.is_initialized

    def test_initialize_is_idempotent(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(claude_vision_config)

        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._claude_client.Anthropic",
                create=True,
                return_value=mock_claude_client,
            ) as mock_cls,
        ):
            model.initialize()
            model.initialize()

        mock_cls.assert_called_once()


# ---------------------------------------------------------------------------
# generate() — image_path branch
# ---------------------------------------------------------------------------


class TestClaudeVisionModelGenerateWithPath:
    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> ClaudeVisionModel:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_generate_with_image_path_calls_api(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)

        result = model.generate("Describe this image", image_path=sample_image)

        assert result == "A photo of a cat"
        mock_claude_client.messages.create.assert_called_once()

    def test_generate_passes_base64_image_block(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
        sample_image: Path,
    ) -> None:
        """Image must be passed as Claude's base64 source block, NOT OpenAI's image_url."""
        model = self._make_initialized(claude_vision_config, mock_claude_client)

        model.generate("Describe", image_path=sample_image)

        _, call_kwargs = mock_claude_client.messages.create.call_args
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        content = messages[0]["content"]

        image_block = content[0]
        assert image_block["type"] == "image"
        assert image_block["source"]["type"] == "base64"
        assert image_block["source"]["media_type"] in (
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
        )
        # Verify no image_url key — that would be the wrong (OpenAI) format
        assert "image_url" not in image_block

    def test_generate_passes_text_prompt_in_content(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)

        model.generate("My custom prompt", image_path=sample_image)

        _, call_kwargs = mock_claude_client.messages.create.call_args
        content = call_kwargs["messages"][0]["content"]
        text_block = content[1]
        assert text_block["type"] == "text"
        assert text_block["text"] == "My custom prompt"

    def test_generate_sends_correct_model_name(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)

        model.generate("prompt", image_path=sample_image)

        _, kwargs = mock_claude_client.messages.create.call_args
        assert kwargs["model"] == claude_vision_config.name

    def test_generate_raises_file_not_found_for_missing_image(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)
        missing = tmp_path / "does_not_exist.png"

        with pytest.raises(FileNotFoundError):
            model.generate("prompt", image_path=missing)


# ---------------------------------------------------------------------------
# generate() — image_data branch
# ---------------------------------------------------------------------------


class TestClaudeVisionModelGenerateWithBytes:
    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> ClaudeVisionModel:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_generate_with_image_data_calls_api(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)

        result = model.generate("Describe", image_data=b"fake bytes")

        assert result == "A photo of a cat"
        mock_claude_client.messages.create.assert_called_once()

    def test_generate_with_bytes_produces_base64_block(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)
        raw = b"image content"

        model.generate("prompt", image_data=raw)

        _, kwargs = mock_claude_client.messages.create.call_args
        image_block = kwargs["messages"][0]["content"][0]
        assert image_block["type"] == "image"
        assert image_block["source"]["type"] == "base64"
        assert base64.b64decode(image_block["source"]["data"]) == raw


# ---------------------------------------------------------------------------
# generate() — guard conditions
# ---------------------------------------------------------------------------


class TestClaudeVisionModelGenerateGuards:
    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> ClaudeVisionModel:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_raises_runtime_error_when_not_initialized(
        self, claude_vision_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(claude_vision_config)

        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("prompt", image_path=Path("/any"))

    def test_raises_value_error_when_neither_image_nor_data(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)

        with pytest.raises(ValueError, match="exactly one"):
            model.generate("prompt")

    def test_raises_value_error_when_both_provided(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)

        with pytest.raises(ValueError, match="exactly one"):
            model.generate("prompt", image_path=sample_image, image_data=b"bytes")


# ---------------------------------------------------------------------------
# analyze_image()
# ---------------------------------------------------------------------------


class TestClaudeVisionModelAnalyzeImage:
    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> ClaudeVisionModel:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(config)
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
    def test_analyze_image_uses_task_prompt(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
        sample_image: Path,
        task: str,
        expected_prompt_fragment: str,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)

        result = model.analyze_image(sample_image, task=task)

        mock_claude_client.messages.create.assert_called_once()
        _, kwargs = mock_claude_client.messages.create.call_args
        text_block = kwargs["messages"][0]["content"][1]
        assert expected_prompt_fragment in text_block["text"], (
            f"Expected {expected_prompt_fragment!r} not found for task={task!r}"
        )
        assert result == "A photo of a cat"

    def test_analyze_image_uses_custom_prompt(
        self,
        claude_vision_config: ModelConfig,
        mock_claude_client: MagicMock,
        sample_image: Path,
    ) -> None:
        model = self._make_initialized(claude_vision_config, mock_claude_client)

        model.analyze_image(sample_image, task="describe", custom_prompt="My custom prompt")

        _, kwargs = mock_claude_client.messages.create.call_args
        text_block = kwargs["messages"][0]["content"][1]
        assert text_block["text"] == "My custom prompt"


# ---------------------------------------------------------------------------
# cleanup()
# ---------------------------------------------------------------------------


class TestClaudeVisionModelCleanup:
    def test_cleanup_calls_close_on_client(self, claude_vision_config: ModelConfig) -> None:
        """cleanup() must call client.close() to release the httpx connection pool."""
        mock_client = MagicMock()
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(claude_vision_config)
        model.client = mock_client
        model._initialized = True

        client_ref = model.client  # capture before cleanup() nulls it
        model.cleanup()

        client_ref.close.assert_called_once()

    def test_cleanup_resets_client_and_initialized_flag(
        self, claude_vision_config: ModelConfig
    ) -> None:
        mock_client = MagicMock()
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(claude_vision_config)
        model.client = mock_client
        model._initialized = True

        model.cleanup()

        assert model.client is None
        assert not model.is_initialized

    def test_cleanup_suppresses_close_exception(self, claude_vision_config: ModelConfig) -> None:
        mock_client = MagicMock()
        mock_client.close.side_effect = RuntimeError("close failed")
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(claude_vision_config)
        model.client = mock_client
        model._initialized = True

        model.cleanup()  # must not raise

        assert model.client is None


# ---------------------------------------------------------------------------
# get_default_config()
# ---------------------------------------------------------------------------


class TestClaudeVisionModelDefaultConfig:
    def test_default_config_is_claude_provider(self) -> None:
        cfg = ClaudeVisionModel.get_default_config()
        assert cfg.provider == "claude"
        assert cfg.model_type == ModelType.VISION

    def test_default_config_model_name(self) -> None:
        cfg = ClaudeVisionModel.get_default_config()
        assert cfg.name == "claude-3-5-sonnet-20241022"

    def test_custom_model_name(self) -> None:
        cfg = ClaudeVisionModel.get_default_config("claude-3-opus-20240229")
        assert cfg.name == "claude-3-opus-20240229"

    def test_framework_field_synced_to_claude(self) -> None:
        cfg = ClaudeVisionModel.get_default_config()
        assert cfg.framework == "claude"


# ---------------------------------------------------------------------------
# Token exhaustion
# ---------------------------------------------------------------------------


class TestClaudeVisionModelTokenExhaustion:
    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> ClaudeVisionModel:
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_retries_on_token_exhaustion(
        self, claude_vision_config: ModelConfig, sample_image: Path
    ) -> None:
        client = MagicMock()
        client.messages.create.side_effect = [
            _exhausted_response(),
            _success_response(),
        ]
        model = self._make_initialized(claude_vision_config, client)

        result = model.generate("describe", image_path=sample_image)

        assert result == "Good content"
        assert client.messages.create.call_count == 2
        retry_kwargs = client.messages.create.call_args_list[1][1]
        assert retry_kwargs["max_tokens"] == claude_vision_config.max_tokens * 2

    def test_raises_on_double_exhaustion(
        self, claude_vision_config: ModelConfig, sample_image: Path
    ) -> None:
        client = MagicMock()
        client.messages.create.return_value = _exhausted_response()
        model = self._make_initialized(claude_vision_config, client)

        with pytest.raises(TokenExhaustionError, match="exhausted token budget"):
            model.generate("describe", image_path=sample_image)

        assert client.messages.create.call_count == 2

    def test_no_retry_when_response_adequate(
        self, claude_vision_config: ModelConfig, sample_image: Path
    ) -> None:
        client = MagicMock()
        text_block = MagicMock()
        text_block.text = "This is a perfectly adequate response from the Claude model"
        client.messages.create.return_value = MagicMock(
            content=[text_block], stop_reason="max_tokens"
        )
        model = self._make_initialized(claude_vision_config, client)

        result = model.generate("describe", image_path=sample_image)

        assert "perfectly adequate" in result
        assert client.messages.create.call_count == 1
