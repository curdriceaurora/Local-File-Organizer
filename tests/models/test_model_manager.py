"""Tests for ModelManager class."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelType
from file_organizer.models.model_manager import ModelManager
from file_organizer.models.registry import AVAILABLE_MODELS, ModelInfo


@pytest.fixture
def model_manager():
    """Return a ModelManager instance with a mocked console."""
    console = MagicMock()
    return ModelManager(console=console)


@pytest.mark.unit
class TestModelManager:
    """Tests for ModelManager class."""

    @patch("file_organizer.models.model_manager.subprocess.run")
    def test_check_installed_success(self, mock_run, model_manager):
        """Test check_installed parses JSON output correctly."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"models": [{"name": "qwen2.5:3b"}, {"name": "llama3:8b"}]})
        mock_run.return_value = mock_result

        installed = model_manager.check_installed()

        assert installed == {"qwen2.5:3b", "llama3:8b"}
        mock_run.assert_called_once_with(
            ["ollama", "list", "--json"], capture_output=True, text=True, timeout=15
        )

    @patch("file_organizer.models.model_manager.subprocess.run")
    def test_check_installed_fallback_on_error_code(self, mock_run, model_manager):
        """Test check_installed falls back to text parsing if JSON fails."""
        # First call fails (JSON), second call succeeds (text)
        mock_result_fail = MagicMock()
        mock_result_fail.returncode = 1

        mock_result_success = MagicMock()
        mock_result_success.stdout = "NAME             SIZE\nphi3:mini        2.3GB\n"

        mock_run.side_effect = [mock_result_fail, mock_result_success]

        with patch.object(
            model_manager, "_parse_ollama_list_text", return_value={"phi3:mini"}
        ) as mock_fallback:
            installed = model_manager.check_installed()
            assert installed == {"phi3:mini"}
            mock_fallback.assert_called_once()

    @patch("file_organizer.models.model_manager.subprocess.run")
    def test_check_installed_file_not_found(self, mock_run, model_manager):
        """Test check_installed handles missing ollama CLI."""
        mock_run.side_effect = FileNotFoundError()
        installed = model_manager.check_installed()
        assert installed == set()

    @patch("file_organizer.models.model_manager.subprocess.run")
    def test_parse_ollama_list_text(self, mock_run, model_manager):
        """Test fallback parsing of plain text ollama list."""
        mock_result = MagicMock()
        mock_result.stdout = "NAME             ID           SIZE   MODIFIED\nlol:latest       abc          1GB    today\ntest:tag         def          2GB    yesterday\n"
        mock_run.return_value = mock_result

        names = model_manager._parse_ollama_list_text()
        assert names == {"lol:latest", "test:tag"}

    @patch("file_organizer.models.model_manager.ModelManager.check_installed")
    def test_list_models(self, mock_check, model_manager):
        """Test list_models populates installed status."""
        # Using built-in AVAILABLE_MODELS registry
        mock_check.return_value = {"qwen2.5:3b-instruct-q4_K_M"}

        models = model_manager.list_models()
        assert len(models) > 0

        for m in models:
            if m.name == "qwen2.5:3b-instruct-q4_K_M":
                assert m.installed is True
            elif m.name == "llava:7b-v1.6-q4_K_M":
                assert m.installed is False

    @patch("file_organizer.models.model_manager.ModelManager.check_installed")
    def test_list_models_with_filter(self, mock_check, model_manager):
        """Test list_models with type filter."""
        mock_check.return_value = set()

        text_models = model_manager.list_models(type_filter=ModelType.TEXT.value)
        assert len(text_models) > 0
        for m in text_models:
            assert m.model_type == ModelType.TEXT.value

    @patch("file_organizer.models.model_manager.subprocess.run")
    def test_pull_model_success(self, mock_run, model_manager):
        """Test pull_model success path."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = model_manager.pull_model("test-model")
        assert result is True
        mock_run.assert_called_once_with(["ollama", "pull", "test-model"], timeout=600)
        model_manager._console.print.assert_any_call(
            "[green]Model 'test-model' pulled successfully.[/green]"
        )

    @patch("file_organizer.models.model_manager.subprocess.run")
    def test_pull_model_failure(self, mock_run, model_manager):
        """Test pull_model failure path."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        result = model_manager.pull_model("test-model")
        assert result is False
        model_manager._console.print.assert_any_call("[red]Pull failed (exit code 1).[/red]")

    @patch("file_organizer.models.model_manager.subprocess.run")
    def test_pull_model_not_found(self, mock_run, model_manager):
        """Test pull_model when ollama is not installed."""
        mock_run.side_effect = FileNotFoundError()
        result = model_manager.pull_model("test-model")
        assert result is False
        model_manager._console.print.assert_any_call(
            "[red]Ollama CLI not found. Install from https://ollama.ai[/red]"
        )

    @patch("file_organizer.models.model_manager.subprocess.run")
    def test_pull_model_timeout(self, mock_run, model_manager):
        """Test pull_model timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["ollama"], timeout=600)
        result = model_manager.pull_model("test-model")
        assert result is False
        model_manager._console.print.assert_any_call("[red]Pull timed out.[/red]")

    def test_is_installed_exact_match(self):
        """Test installed check with exact match."""
        assert ModelManager._is_installed("qwen2.5:3b", {"qwen2.5:3b", "other"}) is True

    def test_is_installed_prefix_match(self):
        """Test installed check with prefix tagging match."""
        # e.g model_name is qwen2.5:3b-instruct-q4_K_M but ollama stores as qwen2.5:3b
        assert ModelManager._is_installed("qwen2.5:3b-instruct-q4_K_M", {"qwen2.5:3b"}) is True

    def test_is_installed_not_found(self):
        """Test installed check for missing models."""
        assert ModelManager._is_installed("llama3", {"qwen2.5:3b"}) is False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelRegistry:
    """Tests for the static AVAILABLE_MODELS catalogue."""

    def test_registry_not_empty(self) -> None:
        assert len(AVAILABLE_MODELS) > 0

    def test_all_entries_are_model_info(self) -> None:
        for m in AVAILABLE_MODELS:
            assert isinstance(m, ModelInfo)

    def test_default_text_model_present(self) -> None:
        names = [m.name for m in AVAILABLE_MODELS]
        assert "qwen2.5:3b-instruct-q4_K_M" in names

    def test_default_vision_model_present(self) -> None:
        names = [m.name for m in AVAILABLE_MODELS]
        assert "qwen2.5vl:7b-q4_K_M" in names

    def test_model_types_are_valid(self) -> None:
        valid_types = {t.value for t in ModelType}
        for m in AVAILABLE_MODELS:
            assert m.model_type in valid_types, f"{m.name} has invalid type {m.model_type}"


# ---------------------------------------------------------------------------
# ModelManager — display
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelManagerDisplay:
    """Tests for ModelManager.display_models()."""

    def test_display_does_not_raise(self) -> None:
        mock_console = MagicMock()
        mgr = ModelManager(console=mock_console)
        with patch.object(mgr, "check_installed", return_value=set()):
            mgr.display_models()
        mock_console.print.assert_called()

    def test_display_with_filter(self) -> None:
        mock_console = MagicMock()
        mgr = ModelManager(console=mock_console)
        with patch.object(mgr, "check_installed", return_value=set()):
            mgr.display_models(type_filter="audio")
        mock_console.print.assert_called()


# ---------------------------------------------------------------------------
# ModelManager — cache_info
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCacheInfo:
    """Tests for cache_info()."""

    def test_cache_info_returns_dict(self) -> None:
        mgr = ModelManager(console=MagicMock())
        result = mgr.cache_info()
        assert isinstance(result, dict)
