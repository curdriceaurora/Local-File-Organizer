"""Unit tests for ClaudeTextModel.

Patterns applied:
- pytestmark: unit + ci markers on every class (project standard)
- Mock call verification: assert_called_once_with exact args, not just return values
- No tautological assertions: assert specific field values, not isinstance
- Parametrize near-duplicate cases (e.g. kwargs overrides)
- Capture client ref before cleanup() nulls it (pattern from PR #835)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType, TokenExhaustionError
from file_organizer.models.claude_text_model import ClaudeTextModel

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
        model_type=ModelType.TEXT,
        provider="claude",
        api_key=api_key,
    )


def _make_client(text: str = "Generated response") -> MagicMock:
    """Return a pre-configured mock Anthropic client."""
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
def claude_config() -> ModelConfig:
    return _make_config()


@pytest.fixture()
def mock_claude_client() -> MagicMock:
    return _make_client()


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestClaudeTextModelInit:
    """Constructor validation."""

    def test_init_sets_config(self, claude_config: ModelConfig) -> None:
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)
        assert model.config is claude_config
        assert model.client is None
        assert not model.is_initialized

    def test_init_raises_import_error_when_anthropic_missing(
        self, claude_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", False):
            with pytest.raises(ImportError, match="file-organizer\\[claude\\]"):
                ClaudeTextModel(claude_config)

    def test_init_raises_value_error_for_wrong_model_type(self) -> None:
        bad_config = ModelConfig(
            name="claude-3-5-sonnet-20241022",
            model_type=ModelType.VISION,  # wrong
            provider="claude",
        )
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            with pytest.raises(ValueError, match="Expected TEXT"):
                ClaudeTextModel(bad_config)


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


class TestClaudeTextModelInitialize:
    """initialize() creates an anthropic.Anthropic client via the shared factory."""

    def test_initialize_creates_client(
        self,
        claude_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)

        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._claude_client.Anthropic",
                create=True,
                return_value=mock_claude_client,
            ) as mock_cls,
        ):
            model.initialize()

        # api_key forwarded; no base_url for Claude
        mock_cls.assert_called_once_with(api_key=claude_config.api_key)
        assert model.client is mock_claude_client
        assert model.is_initialized

    def test_initialize_is_idempotent(
        self,
        claude_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)

        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._claude_client.Anthropic",
                create=True,
                return_value=mock_claude_client,
            ) as mock_cls,
        ):
            model.initialize()
            model.initialize()  # second call must be a no-op

        mock_cls.assert_called_once()  # NOT twice

    def test_initialize_without_api_key_omits_kwarg(
        self,
        mock_claude_client: MagicMock,
    ) -> None:
        """When api_key is None the SDK reads ANTHROPIC_API_KEY from env."""
        cfg = _make_config(api_key=None)
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(cfg)

        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._claude_client.Anthropic",
                create=True,
                return_value=mock_claude_client,
            ) as mock_cls,
        ):
            model.initialize()

        # Must be called with NO kwargs — SDK reads env var automatically
        mock_cls.assert_called_once_with()

    def test_initialize_warns_and_ignores_base_url(
        self,
        mock_claude_client: MagicMock,
    ) -> None:
        """api_base_url is silently ignored with a warning (Claude SDK has no base_url)."""
        cfg = ModelConfig(
            name="claude-3-5-sonnet-20241022",
            model_type=ModelType.TEXT,
            provider="claude",
            api_key="sk-ant-test",
            api_base_url="https://custom.endpoint.example.com",
        )
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(cfg)

        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._claude_client.Anthropic",
                create=True,
                return_value=mock_claude_client,
            ) as mock_cls,
        ):
            model.initialize()

        # base_url must NOT be passed to Anthropic()
        call_kwargs = mock_cls.call_args[1]
        assert "base_url" not in call_kwargs

    def test_initialize_propagates_exception(self, claude_config: ModelConfig) -> None:
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)

        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._claude_client.Anthropic",
                create=True,
                side_effect=RuntimeError("auth failure"),
            ),
        ):
            with pytest.raises(RuntimeError, match="auth failure"):
                model.initialize()

        assert not model.is_initialized
        assert model.client is None


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


class TestClaudeTextModelGenerate:
    """generate() calls messages.create with the correct payload."""

    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> ClaudeTextModel:
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_generate_returns_stripped_content(
        self,
        claude_config: ModelConfig,
    ) -> None:
        client = _make_client("  trimmed response  ")
        model = self._make_initialized(claude_config, client)

        result = model.generate("Hello")

        assert result == "trimmed response"

    def test_generate_calls_api_with_exact_payload(
        self,
        claude_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        model = self._make_initialized(claude_config, mock_claude_client)

        model.generate("Describe this file")

        mock_claude_client.messages.create.assert_called_once_with(
            model=claude_config.name,
            max_tokens=claude_config.max_tokens,
            messages=[{"role": "user", "content": "Describe this file"}],
            temperature=claude_config.temperature,
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
        claude_config: ModelConfig,
        mock_claude_client: MagicMock,
        kwarg_name: str,
        kwarg_value: float,
    ) -> None:
        model = self._make_initialized(claude_config, mock_claude_client)

        model.generate("prompt", **{kwarg_name: kwarg_value})

        _, call_kwargs = mock_claude_client.messages.create.call_args
        assert call_kwargs[kwarg_name] == kwarg_value

    def test_generate_raises_runtime_error_when_not_initialized(
        self, claude_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)

        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("prompt")

    def test_generate_propagates_api_exception(
        self,
        claude_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        mock_claude_client.messages.create.side_effect = RuntimeError("API error")
        model = self._make_initialized(claude_config, mock_claude_client)

        with pytest.raises(RuntimeError, match="API error"):
            model.generate("prompt")

    def test_generate_handles_empty_content(
        self,
        claude_config: ModelConfig,
    ) -> None:
        """Empty content list returns empty string."""
        client = MagicMock()
        client.messages.create.return_value = MagicMock(content=[], stop_reason="end_turn")
        model = self._make_initialized(claude_config, client)

        result = model.generate("prompt")

        assert result == ""


# ---------------------------------------------------------------------------
# cleanup()
# ---------------------------------------------------------------------------


class TestClaudeTextModelCleanup:
    """cleanup() calls client.close() and resets initialisation state."""

    def test_cleanup_calls_close_on_client(self, claude_config: ModelConfig) -> None:
        """cleanup() must call client.close() to release the httpx connection pool."""
        mock_client = MagicMock()
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)
        model.client = mock_client
        model._initialized = True

        client_ref = model.client  # capture before cleanup() nulls it
        model.cleanup()

        client_ref.close.assert_called_once()

    def test_cleanup_resets_state(self, claude_config: ModelConfig) -> None:
        mock_client = MagicMock()
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)
        model.client = mock_client
        model._initialized = True

        model.cleanup()

        assert model.client is None
        assert not model.is_initialized

    def test_cleanup_is_safe_when_not_initialized(self, claude_config: ModelConfig) -> None:
        """cleanup() on an uninitialised model must not raise."""
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)

        model.cleanup()  # should not raise

        assert model.client is None
        assert not model.is_initialized

    def test_cleanup_suppresses_close_exception(self, claude_config: ModelConfig) -> None:
        """Exceptions from client.close() are swallowed — not re-raised."""
        mock_client = MagicMock()
        mock_client.close.side_effect = RuntimeError("close failed")
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)
        model.client = mock_client
        model._initialized = True

        model.cleanup()  # must not raise

        assert model.client is None
        assert not model.is_initialized


# ---------------------------------------------------------------------------
# get_default_config()
# ---------------------------------------------------------------------------


class TestClaudeTextModelDefaultConfig:
    """get_default_config() returns a correctly typed ModelConfig."""

    def test_default_config_provider_is_claude(self) -> None:
        cfg = ClaudeTextModel.get_default_config()
        assert cfg.provider == "claude"
        assert cfg.model_type == ModelType.TEXT

    def test_default_config_default_model_name(self) -> None:
        cfg = ClaudeTextModel.get_default_config()
        assert cfg.name == "claude-3-5-sonnet-20241022"

    def test_default_config_custom_model_name(self) -> None:
        cfg = ClaudeTextModel.get_default_config("claude-3-opus-20240229")
        assert cfg.name == "claude-3-opus-20240229"

    def test_framework_field_synced_to_claude(self) -> None:
        """ModelConfig.__post_init__ must sync framework = 'claude' for provider='claude'."""
        cfg = ClaudeTextModel.get_default_config()
        assert cfg.framework == "claude"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestClaudeTextModelContextManager:
    def test_context_manager_initializes_and_cleans_up(
        self,
        claude_config: ModelConfig,
        mock_claude_client: MagicMock,
    ) -> None:
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(claude_config)

        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch(
                "file_organizer.models._claude_client.Anthropic",
                create=True,
                return_value=mock_claude_client,
            ),
        ):
            with model:
                assert model.is_initialized

        assert not model.is_initialized
        assert model.client is None


# ---------------------------------------------------------------------------
# Token exhaustion
# ---------------------------------------------------------------------------


class TestClaudeTextModelTokenExhaustion:
    """stop_reason == 'max_tokens' triggers retry with doubled max_tokens."""

    def _make_initialized(self, config: ModelConfig, client: MagicMock) -> ClaudeTextModel:
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(config)
        model.client = client
        model._initialized = True
        return model

    def test_retries_on_token_exhaustion(self, claude_config: ModelConfig) -> None:
        client = MagicMock()
        client.messages.create.side_effect = [
            _exhausted_response(),
            _success_response(),
        ]
        model = self._make_initialized(claude_config, client)

        result = model.generate("test")

        assert result == "Good content"
        assert client.messages.create.call_count == 2
        retry_kwargs = client.messages.create.call_args_list[1][1]
        assert retry_kwargs["max_tokens"] == claude_config.max_tokens * 2

    def test_raises_on_double_exhaustion(self, claude_config: ModelConfig) -> None:
        client = MagicMock()
        client.messages.create.return_value = _exhausted_response()
        model = self._make_initialized(claude_config, client)

        with pytest.raises(TokenExhaustionError, match="exhausted token budget"):
            model.generate("test")

        assert client.messages.create.call_count == 2

    def test_no_retry_when_stop_reason_end_turn(self, claude_config: ModelConfig) -> None:
        client = MagicMock()
        client.messages.create.return_value = _success_response("")
        model = self._make_initialized(claude_config, client)

        result = model.generate("test")

        assert result == ""
        assert client.messages.create.call_count == 1

    def test_no_retry_when_response_adequate(self, claude_config: ModelConfig) -> None:
        """max_tokens but adequate content — no retry (content is long enough)."""
        client = MagicMock()
        text_block = MagicMock()
        text_block.text = "This is a perfectly adequate response from the Claude model"
        client.messages.create.return_value = MagicMock(
            content=[text_block], stop_reason="max_tokens"
        )
        model = self._make_initialized(claude_config, client)

        result = model.generate("test")

        assert "perfectly adequate" in result
        assert client.messages.create.call_count == 1
