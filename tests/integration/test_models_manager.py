"""Integration tests for ModelManager.

Covers: check_installed() (JSON parse, dict form, list form, non-zero
returncode falls back to text parse, FileNotFoundError returns empty set),
list_models() (all / text / vision / audio / custom type_filter),
display_models() (prints Rich table without error), pull_model() (success,
FileNotFoundError, timeout), swap_model() (no factory, with factory, factory
raises → rollback, concurrent lock returns False), get_active_model() /
get_active_model_id(), cache_info() (import fallback path).
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.model_manager import ModelManager

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_response(names: list[str]) -> str:
    """Serialize a list of model names to the Ollama JSON format (dict form)."""
    return json.dumps({"models": [{"name": n} for n in names]})


def _json_list_response(names: list[str]) -> str:
    """Serialize a list of model names to the Ollama JSON format (list form)."""
    return json.dumps([{"name": n} for n in names])


def _completed_proc(stdout: str = "", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# check_installed()
# ---------------------------------------------------------------------------


class TestCheckInstalled:
    def test_returns_names_from_json_dict_form(self) -> None:
        with patch("subprocess.run", return_value=_completed_proc(_json_response(["llama3:8b"]))):
            mgr = ModelManager()
            result = mgr.check_installed()
        assert "llama3:8b" in result

    def test_returns_names_from_json_list_form(self) -> None:
        with patch(
            "subprocess.run",
            return_value=_completed_proc(_json_list_response(["qwen2.5:3b"])),
        ):
            mgr = ModelManager()
            result = mgr.check_installed()
        assert "qwen2.5:3b" in result

    def test_returns_empty_set_on_empty_json(self) -> None:
        with patch("subprocess.run", return_value=_completed_proc("{}")):
            mgr = ModelManager()
            result = mgr.check_installed()
        assert isinstance(result, set)
        assert len(result) == 0

    def test_fallback_to_text_parse_on_nonzero_returncode(self) -> None:
        text_output = "NAME              ID            SIZE   MODIFIED\nllama3:8b         abc123  4.7 GB  2 hours ago\n"
        with patch(
            "subprocess.run",
            side_effect=[
                _completed_proc("", returncode=1),
                _completed_proc(text_output, returncode=0),
            ],
        ):
            mgr = ModelManager()
            result = mgr.check_installed()
        assert "llama3:8b" in result

    def test_returns_empty_set_when_ollama_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError("ollama not found")):
            mgr = ModelManager()
            result = mgr.check_installed()
        assert result == set()

    def test_returns_multiple_installed_models(self) -> None:
        names = ["llama3:8b", "qwen2.5:3b", "llava:7b"]
        with patch("subprocess.run", return_value=_completed_proc(_json_response(names))):
            mgr = ModelManager()
            result = mgr.check_installed()
        assert result == set(names)


# ---------------------------------------------------------------------------
# list_models()
# ---------------------------------------------------------------------------


class TestListModels:
    def _patch_installed(self, mgr: ModelManager, names: set[str]) -> None:
        mgr.check_installed = lambda: names  # type: ignore[method-assign]

    def test_list_models_all_returns_list(self) -> None:
        mgr = ModelManager()
        self._patch_installed(mgr, set())
        models = mgr.list_models()
        assert isinstance(models, list)
        assert len(models) >= 1

    def test_list_models_text_filter(self) -> None:
        mgr = ModelManager()
        self._patch_installed(mgr, set())
        models = mgr.list_models(type_filter="text")
        assert len(models) >= 1
        assert all(m.model_type == "text" for m in models)

    def test_list_models_vision_filter(self) -> None:
        mgr = ModelManager()
        self._patch_installed(mgr, set())
        models = mgr.list_models(type_filter="vision")
        assert len(models) >= 1
        assert all(m.model_type == "vision" for m in models)

    def test_list_models_audio_filter(self) -> None:
        mgr = ModelManager()
        self._patch_installed(mgr, set())
        models = mgr.list_models(type_filter="audio")
        assert len(models) >= 1
        assert all(m.model_type == "audio" for m in models)

    def test_list_models_unknown_filter_returns_empty(self) -> None:
        mgr = ModelManager()
        self._patch_installed(mgr, set())
        models = mgr.list_models(type_filter="nonexistent_type_xyz")
        assert isinstance(models, list)
        assert len(models) == 0

    def test_installed_flag_set_for_known_model(self) -> None:
        from file_organizer.models.registry import get_text_models

        all_text = get_text_models()
        if not all_text:
            pytest.skip("No text models in registry")
        first_model_name = all_text[0].name

        mgr = ModelManager()
        self._patch_installed(mgr, {first_model_name})
        models = mgr.list_models(type_filter="text")
        matching = [m for m in models if m.name == first_model_name]
        assert matching[0].installed is True

    def test_not_installed_flag_for_absent_model(self) -> None:
        mgr = ModelManager()
        self._patch_installed(mgr, set())
        models = mgr.list_models(type_filter="text")
        assert all(m.installed is False for m in models)


# ---------------------------------------------------------------------------
# display_models()
# ---------------------------------------------------------------------------


class TestDisplayModels:
    def test_display_models_does_not_raise(self) -> None:
        mock_console = MagicMock()
        mgr = ModelManager(console=mock_console)
        mgr.check_installed = lambda: set()  # type: ignore[method-assign]
        mgr.display_models()
        mock_console.print.assert_called_once()

    def test_display_models_text_filter_does_not_raise(self) -> None:
        mock_console = MagicMock()
        mgr = ModelManager(console=mock_console)
        mgr.check_installed = lambda: set()  # type: ignore[method-assign]
        mgr.display_models(type_filter="text")
        mock_console.print.assert_called_once()


# ---------------------------------------------------------------------------
# pull_model()
# ---------------------------------------------------------------------------


class TestPullModel:
    def test_pull_model_returns_true_on_success(self) -> None:
        proc = _completed_proc(returncode=0)
        with patch("subprocess.run", return_value=proc):
            mgr = ModelManager()
            assert mgr.pull_model("llama3:8b") is True

    def test_pull_model_returns_false_on_nonzero_exit(self) -> None:
        proc = _completed_proc(returncode=1)
        with patch("subprocess.run", return_value=proc):
            mgr = ModelManager()
            assert mgr.pull_model("bad-model") is False

    def test_pull_model_returns_false_when_ollama_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            mgr = ModelManager()
            assert mgr.pull_model("any-model") is False

    def test_pull_model_returns_false_on_timeout(self) -> None:
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ollama", timeout=600)
        ):
            mgr = ModelManager()
            assert mgr.pull_model("slow-model") is False


# ---------------------------------------------------------------------------
# swap_model()
# ---------------------------------------------------------------------------


class TestSwapModel:
    def test_swap_model_without_factory_records_id(self) -> None:
        mgr = ModelManager()
        result = mgr.swap_model("text", "llama3:8b")
        assert result is True
        assert mgr.get_active_model_id("text") == "llama3:8b"
        assert mgr.get_active_model("text") is None

    def test_swap_model_with_factory_loads_model(self) -> None:
        mgr = ModelManager()
        mock_model = MagicMock()
        factory = lambda: mock_model  # noqa: E731
        result = mgr.swap_model("text", "llama3:8b", model_factory=factory)
        assert result is True
        assert mgr.get_active_model("text") is mock_model
        mock_model.initialize.assert_called_once()

    def test_swap_model_factory_failure_returns_false(self) -> None:
        mgr = ModelManager()

        def bad_factory():
            raise RuntimeError("Factory failed")

        result = mgr.swap_model("text", "llama3:8b", model_factory=bad_factory)
        assert result is False
        assert mgr.get_active_model("text") is None

    def test_swap_model_factory_failure_preserves_old_model(self) -> None:
        mgr = ModelManager()
        old_model = MagicMock()
        mgr._active_models["text"] = old_model
        mgr._active_model_ids["text"] = "old-model"

        def bad_factory():
            raise RuntimeError("Factory failed")

        mgr.swap_model("text", "new-model", model_factory=bad_factory)
        assert mgr.get_active_model("text") is old_model

    def test_swap_model_drains_old_model(self) -> None:
        mgr = ModelManager()
        old_model = MagicMock()
        mgr._active_models["text"] = old_model

        new_model = MagicMock()
        mgr.swap_model("text", "new-model", model_factory=lambda: new_model)
        old_model.safe_cleanup.assert_called_once()

    def test_swap_model_concurrent_lock_returns_false(self) -> None:
        mgr = ModelManager()
        results: list[bool] = []

        def hold_lock() -> None:
            mgr._swap_lock.acquire()

        hold_lock()
        result = mgr.swap_model("text", "any-model")
        results.append(result)
        mgr._swap_lock.release()
        assert results == [False]

    def test_swap_model_updates_active_model_id(self) -> None:
        mgr = ModelManager()
        mgr.swap_model("vision", "llava:7b")
        assert mgr.get_active_model_id("vision") == "llava:7b"

    def test_swap_model_multiple_types_independent(self) -> None:
        mgr = ModelManager()
        mgr.swap_model("text", "llama3:8b")
        mgr.swap_model("vision", "llava:7b")
        assert mgr.get_active_model_id("text") == "llama3:8b"
        assert mgr.get_active_model_id("vision") == "llava:7b"


# ---------------------------------------------------------------------------
# get_active_model() / get_active_model_id()
# ---------------------------------------------------------------------------


class TestGetActiveModel:
    def test_get_active_model_returns_none_if_not_loaded(self) -> None:
        mgr = ModelManager()
        assert mgr.get_active_model("text") is None

    def test_get_active_model_id_returns_none_if_never_swapped(self) -> None:
        mgr = ModelManager()
        assert mgr.get_active_model_id("audio") is None


# ---------------------------------------------------------------------------
# cache_info()
# ---------------------------------------------------------------------------


class TestCacheInfo:
    def test_cache_info_returns_dict(self) -> None:
        mgr = ModelManager()
        result = mgr.cache_info()
        assert isinstance(result, dict)
        assert all(isinstance(k, str) for k in result.keys())

    def test_cache_info_returns_empty_dict_on_import_failure(self) -> None:
        with patch.dict("sys.modules", {"file_organizer.optimization.model_cache": None}):
            mgr = ModelManager()
            result = mgr.cache_info()
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_cache_info_returns_expected_keys_when_available(self) -> None:
        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 10
        mock_stats.misses = 5
        mock_stats.evictions = 2
        mock_stats.current_size = 3
        mock_stats.max_size = 100
        mock_stats.memory_usage_bytes = 1024
        mock_cache.stats.return_value = mock_stats

        mock_module = MagicMock()
        mock_module.ModelCache.return_value = mock_cache

        with patch.dict("sys.modules", {"file_organizer.optimization.model_cache": mock_module}):
            mgr = ModelManager()
            result = mgr.cache_info()

        assert result.get("hits") == 10
        assert result.get("misses") == 5
        assert result.get("evictions") == 2
        assert result.get("current_size") == 3
        assert result.get("max_size") == 100
        assert result.get("memory_usage_bytes") == 1024
