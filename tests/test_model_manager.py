"""Tests for ModelManager and model registry."""

from __future__ import annotations
import pytest

from unittest.mock import MagicMock, patch

from file_organizer.models.model_manager import ModelManager
from file_organizer.models.registry import AVAILABLE_MODELS, ModelInfo

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
        valid_types = {"text", "vision", "audio"}
        for m in AVAILABLE_MODELS:
            assert m.model_type in valid_types, f"{m.name} has invalid type {m.model_type}"


# ---------------------------------------------------------------------------
# ModelManager — list
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelManagerList:
    """Tests for ModelManager.list_models()."""

    def test_list_all_models(self) -> None:
        mgr = ModelManager()
        with patch.object(mgr, "check_installed", return_value=set()):
            models = mgr.list_models()
        assert len(models) == len(AVAILABLE_MODELS)

    def test_filter_by_text_type(self) -> None:
        mgr = ModelManager()
        with patch.object(mgr, "check_installed", return_value=set()):
            models = mgr.list_models(type_filter="text")
        assert all(m.model_type == "text" for m in models)
        assert len(models) > 0

    def test_filter_by_vision_type(self) -> None:
        mgr = ModelManager()
        with patch.object(mgr, "check_installed", return_value=set()):
            models = mgr.list_models(type_filter="vision")
        assert all(m.model_type == "vision" for m in models)

    def test_installed_flag_set_when_found(self) -> None:
        mgr = ModelManager()
        installed = {"qwen2.5:3b-instruct-q4_K_M"}
        with patch.object(mgr, "check_installed", return_value=installed):
            models = mgr.list_models()
        by_name = {m.name: m for m in models}
        assert by_name["qwen2.5:3b-instruct-q4_K_M"].installed is True

    def test_installed_flag_false_when_not_found(self) -> None:
        mgr = ModelManager()
        with patch.object(mgr, "check_installed", return_value=set()):
            models = mgr.list_models()
        assert all(not m.installed for m in models)


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
# ModelManager — check_installed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckInstalled:
    """Tests for Ollama integration."""

    def test_ollama_not_found(self) -> None:
        mgr = ModelManager()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = mgr.check_installed()
        assert result == set()

    def test_ollama_json_output(self) -> None:
        mgr = ModelManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"models": [{"name": "qwen2.5:3b-instruct-q4_K_M"}]}'
        with patch("subprocess.run", return_value=mock_result):
            result = mgr.check_installed()
        assert "qwen2.5:3b-instruct-q4_K_M" in result

    def test_ollama_text_fallback(self) -> None:
        mgr = ModelManager()
        # First call (--json) fails, second call (plain) succeeds
        failed = MagicMock()
        failed.returncode = 1
        success = MagicMock()
        success.returncode = 0
        success.stdout = "NAME           ID\ntest:latest    abc123\n"
        with patch("subprocess.run", side_effect=[failed, success]):
            result = mgr.check_installed()
        assert "test:latest" in result


# ---------------------------------------------------------------------------
# ModelManager — pull
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelPull:
    """Tests for pull_model()."""

    def test_pull_success(self) -> None:
        mock_console = MagicMock()
        mgr = ModelManager(console=mock_console)
        proc = MagicMock()
        proc.returncode = 0
        with patch("subprocess.run", return_value=proc):
            result = mgr.pull_model("test:latest")
        assert result is True

    def test_pull_failure(self) -> None:
        mock_console = MagicMock()
        mgr = ModelManager(console=mock_console)
        proc = MagicMock()
        proc.returncode = 1
        with patch("subprocess.run", return_value=proc):
            result = mgr.pull_model("nonexistent:latest")
        assert result is False

    def test_pull_ollama_missing(self) -> None:
        mock_console = MagicMock()
        mgr = ModelManager(console=mock_console)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = mgr.pull_model("test:latest")
        assert result is False


# ---------------------------------------------------------------------------
# ModelManager — cache_info
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCacheInfo:
    """Tests for cache_info()."""

    def test_cache_info_returns_dict(self) -> None:
        mgr = ModelManager()
        result = mgr.cache_info()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsInstalled:
    """Tests for _is_installed prefix matching."""

    def test_exact_match(self) -> None:
        assert ModelManager._is_installed("foo:bar", {"foo:bar"}) is True

    def test_prefix_match(self) -> None:
        assert ModelManager._is_installed("foo:bar-baz", {"foo:other"}) is True

    def test_no_match(self) -> None:
        assert ModelManager._is_installed("foo:bar", {"baz:qux"}) is False

    def test_empty_installed(self) -> None:
        assert ModelManager._is_installed("foo:bar", set()) is False
