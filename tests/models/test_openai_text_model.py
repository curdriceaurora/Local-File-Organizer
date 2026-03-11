"""Unit tests for OpenAITextModel.

Patterns applied:
- pytestmark: unit + ci markers on every class (project standard)
- Mock call verification: assert_called_once_with exact args, not just return values
- No tautological assertions: assert specific field values, not isinstance
- Parametrize near-duplicate cases (e.g. kwargs overrides)
- AsyncMock: N/A — all model methods are synchronous
- tmp_path: N/A — no file I/O in text model tests
- Exit code / CLI: N/A — pure unit test
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType, TokenExhaustionError
from file_organizer.models.openai_text_model import OpenAITextModel

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def openai_config() -> ModelConfig:
    """Minimal OpenAI text model config."""
    return ModelConfig(
        name="gpt-4o-mini",
        model_type=ModelType.TEXT,
        provider="openai",
        api_key="sk-test",
        api_base_url=None,
    )


@pytest.fixture()
def mock_openai_client() -> MagicMock:
    """Pre-configured mock for the openai.OpenAI client."""
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = "Generated response"
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestOpenAITextModelInit:
    """Constructor validation."""

    def test_init_sets_config(self, openai_config: ModelConfig) -> None:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(openai_config)
        assert model.config is openai_config
        assert model.client is None
        assert not model.is_initialized

    def test_init_raises_import_error_when_openai_missing(self, openai_config: ModelConfig) -> None:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", False):
            with pytest.raises(ImportError, match="file-organizer\\[cloud\\]"):
                OpenAITextModel(openai_config)

    def test_init_raises_value_error_for_wrong_model_type(self) -> None:
        bad_config = ModelConfig(
            name="gpt-4o-mini",
            model_type=ModelType.VISION,  # wrong
            provider="openai",
        )
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            with pytest.raises(ValueError, match="Expected TEXT"):
                OpenAITextModel(bad_config)


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


class TestOpenAITextModelInitialize:
    """initialize() creates an openai.OpenAI client via the shared factory."""

    def test_initialize_creates_client(
        self,
        openai_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(openai_config)

        with (
            patch("file_organizer.models._openai_client.OPENAI_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._openai_client.OpenAI",
                create=True,
                return_value=mock_openai_client,
            ) as mock_cls,
        ):
            model.initialize()

        # Verify client was created with only the non-None credentials
        mock_cls.assert_called_once_with(
            api_key=openai_config.api_key,
        )
        assert model.client is mock_openai_client
        assert model.is_initialized

    def test_initialize_is_idempotent(
        self,
        openai_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(openai_config)

        with (
            patch("file_organizer.models._openai_client.OPENAI_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._openai_client.OpenAI",
                create=True,
                return_value=mock_openai_client,
            ) as mock_cls,
        ):
            model.initialize()
            model.initialize()  # second call should be a no-op

        mock_cls.assert_called_once()  # NOT twice

    def test_initialize_with_base_url_and_no_api_key(
        self,
        mock_openai_client: MagicMock,
    ) -> None:
        """Local LM Studio / vLLM flow: base_url set, no api_key."""
        local_config = ModelConfig(
            name="local-model",
            model_type=ModelType.TEXT,
            provider="openai",
            api_key=None,
            api_base_url="http://localhost:1234/v1",
        )
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(local_config)

        with (
            patch("file_organizer.models._openai_client.OPENAI_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._openai_client.OpenAI",
                create=True,
                return_value=mock_openai_client,
            ) as mock_cls,
        ):
            model.initialize()

        # Client must be constructed with base_url only — no api_key kwarg
        mock_cls.assert_called_once_with(base_url="http://localhost:1234/v1")
        assert model.client is mock_openai_client
        assert model.is_initialized

    def test_initialize_propagates_exception(self, openai_config: ModelConfig) -> None:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(openai_config)

        with (
            patch("file_organizer.models._openai_client.OPENAI_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._openai_client.OpenAI",
                create=True,
                side_effect=RuntimeError("connection refused"),
            ),
        ):
            with pytest.raises(RuntimeError, match="connection refused"):
                model.initialize()

        # Model must NOT be marked initialised after failure
        assert not model.is_initialized
        assert model.client is None


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


class TestOpenAITextModelGenerate:
    """generate() calls chat.completions.create with the correct payload."""

    def _make_initialized(
        self,
        config: ModelConfig,
        client: MagicMock,
    ) -> OpenAITextModel:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_generate_returns_stripped_content(
        self,
        openai_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        choice = MagicMock()
        choice.message.content = "  trimmed response  "
        mock_openai_client.chat.completions.create.return_value = MagicMock(choices=[choice])
        model = self._make_initialized(openai_config, mock_openai_client)

        result = model.generate("Hello")

        assert result == "trimmed response"

    def test_generate_calls_api_with_exact_payload(
        self,
        openai_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        model = self._make_initialized(openai_config, mock_openai_client)

        model.generate("Describe this file")

        mock_openai_client.chat.completions.create.assert_called_once_with(
            model=openai_config.name,
            messages=[{"role": "user", "content": "Describe this file"}],
            temperature=openai_config.temperature,
            max_tokens=openai_config.max_tokens,
        )

    @pytest.mark.parametrize(
        "kwarg_name, kwarg_value",
        [
            ("temperature", 0.1),
            ("max_tokens", 500),
        ],
    )
    def test_generate_kwargs_override_config(
        self,
        openai_config: ModelConfig,
        mock_openai_client: MagicMock,
        kwarg_name: str,
        kwarg_value: float,
    ) -> None:
        model = self._make_initialized(openai_config, mock_openai_client)

        model.generate("prompt", **{kwarg_name: kwarg_value})

        _, call_kwargs = mock_openai_client.chat.completions.create.call_args
        assert call_kwargs[kwarg_name] == kwarg_value

    def test_generate_raises_runtime_error_when_not_initialized(
        self, openai_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(openai_config)

        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("prompt")

    def test_generate_propagates_api_exception(
        self,
        openai_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        mock_openai_client.chat.completions.create.side_effect = RuntimeError("API error")
        model = self._make_initialized(openai_config, mock_openai_client)

        with pytest.raises(RuntimeError, match="API error"):
            model.generate("prompt")

    def test_generate_handles_none_content(
        self,
        openai_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        """None message content (refusal / content filter) should return empty string."""
        choice = MagicMock()
        choice.message.content = None
        mock_openai_client.chat.completions.create.return_value = MagicMock(choices=[choice])
        model = self._make_initialized(openai_config, mock_openai_client)

        result = model.generate("prompt")

        assert result == ""


# ---------------------------------------------------------------------------
# cleanup()
# ---------------------------------------------------------------------------


class TestOpenAITextModelCleanup:
    """cleanup() releases the client and resets initialisation state."""

    def test_cleanup_resets_state(
        self,
        openai_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(openai_config)
        model.client = mock_openai_client
        model._initialized = True

        model.cleanup()

        assert model.client is None
        assert not model.is_initialized


# ---------------------------------------------------------------------------
# get_default_config()
# ---------------------------------------------------------------------------


class TestOpenAITextModelDefaultConfig:
    """get_default_config() returns a correctly typed ModelConfig."""

    def test_default_config_provider_is_openai(self) -> None:
        cfg = OpenAITextModel.get_default_config()
        assert cfg.provider == "openai"
        assert cfg.model_type == ModelType.TEXT

    def test_default_config_custom_model_name(self) -> None:
        cfg = OpenAITextModel.get_default_config("gpt-4o")
        assert cfg.name == "gpt-4o"

    def test_default_config_default_model_name(self) -> None:
        cfg = OpenAITextModel.get_default_config()
        assert cfg.name == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestOpenAITextModelContextManager:
    """Using the model as a context manager initialises and cleans up correctly."""

    def test_context_manager_initializes_and_cleans_up(
        self,
        openai_config: ModelConfig,
        mock_openai_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(openai_config)

        with (
            patch("file_organizer.models._openai_client.OPENAI_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._openai_client.OpenAI",
                create=True,
                return_value=mock_openai_client,
            ),
        ):
            with model:
                assert model.is_initialized

        assert not model.is_initialized
        assert model.client is None


# ---------------------------------------------------------------------------
# Token exhaustion
# ---------------------------------------------------------------------------


class TestOpenAITextModelTokenExhaustion:
    """Token-exhaustion detection and retry in OpenAITextModel.generate()."""

    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> OpenAITextModel:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(config)
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

    def test_retries_on_token_exhaustion(self, openai_config: ModelConfig) -> None:
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            self._exhausted_response(),
            self._success_response(),
        ]
        model = self._make_initialized(openai_config, client)

        result = model.generate("test")

        assert result == "Good content"
        assert client.chat.completions.create.call_count == 2
        # Retry uses doubled max_tokens
        retry_kwargs = client.chat.completions.create.call_args_list[1][1]
        assert retry_kwargs["max_tokens"] == openai_config.max_tokens * 2

    def test_raises_on_double_exhaustion(self, openai_config: ModelConfig) -> None:
        client = MagicMock()
        client.chat.completions.create.return_value = self._exhausted_response()
        model = self._make_initialized(openai_config, client)

        with pytest.raises(TokenExhaustionError, match="exhausted token budget"):
            model.generate("test")

        assert client.chat.completions.create.call_count == 2

    def test_no_retry_when_finish_reason_stop(self, openai_config: ModelConfig) -> None:
        client = MagicMock()
        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = ""
        client.chat.completions.create.return_value = MagicMock(choices=[choice])
        model = self._make_initialized(openai_config, client)

        result = model.generate("test")

        assert result == ""
        assert client.chat.completions.create.call_count == 1

    def test_no_retry_when_response_adequate(self, openai_config: ModelConfig) -> None:
        client = MagicMock()
        choice = MagicMock()
        choice.finish_reason = "length"
        choice.message.content = "This is a perfectly adequate response from the model"
        client.chat.completions.create.return_value = MagicMock(choices=[choice])
        model = self._make_initialized(openai_config, client)

        result = model.generate("test")

        assert "perfectly adequate" in result
        assert client.chat.completions.create.call_count == 1
