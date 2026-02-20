"""Tests for file_organizer.models.model_manager module.

Covers ModelManager lifecycle, list_models, pull_model, check_installed,
and cache_info — all with mocked subprocess/ollama calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.model_manager import ModelManager


# ---------------------------------------------------------------------------
# check_installed
# ---------------------------------------------------------------------------


class TestCheckInstalled:
    """Tests for ModelManager.check_installed."""

    def test_parses_json_output(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {"models": [{"name": "qwen2.5:3b"}, {"name": "llama3:8b"}]}
        )

        with patch("subprocess.run", return_value=mock_result):
            mgr = ModelManager()
            installed = mgr.check_installed()
            assert "qwen2.5:3b" in installed
            assert "llama3:8b" in installed

    def test_parses_json_list_format(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([{"name": "model-a"}, {"name": "model-b"}])

        with patch("subprocess.run", return_value=mock_result):
            mgr = ModelManager()
            installed = mgr.check_installed()
            assert "model-a" in installed

    def test_fallback_on_json_failure(self) -> None:
        mock_json_result = MagicMock()
        mock_json_result.returncode = 1

        mock_text_result = MagicMock()
        mock_text_result.stdout = "NAME\tSIZE\nqwen2.5:3b\t1.9GB\n"
        mock_text_result.returncode = 0

        with patch(
            "subprocess.run", side_effect=[mock_json_result, mock_text_result]
        ):
            mgr = ModelManager()
            installed = mgr.check_installed()
            assert "qwen2.5:3b" in installed

    def test_ollama_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            mgr = ModelManager()
            installed = mgr.check_installed()
            assert installed == set()

    def test_generic_exception_falls_back(self) -> None:
        mock_text_result = MagicMock()
        mock_text_result.stdout = "NAME\tSIZE\ntest:latest\t2GB\n"
        mock_text_result.returncode = 0

        with patch(
            "subprocess.run", side_effect=[RuntimeError("fail"), mock_text_result]
        ):
            mgr = ModelManager()
            installed = mgr.check_installed()
            assert "test:latest" in installed


# ---------------------------------------------------------------------------
# _is_installed
# ---------------------------------------------------------------------------


class TestIsInstalled:
    """Tests for ModelManager._is_installed static method."""

    def test_exact_match(self) -> None:
        assert ModelManager._is_installed("qwen2.5:3b", {"qwen2.5:3b", "llama3:8b"})

    def test_prefix_match(self) -> None:
        assert ModelManager._is_installed(
            "qwen2.5:3b", {"qwen2.5:3b-instruct-q4_K_M"}
        )

    def test_no_match(self) -> None:
        assert not ModelManager._is_installed("missing:model", {"other:model"})

    def test_empty_installed(self) -> None:
        assert not ModelManager._is_installed("any:model", set())


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


class TestListModels:
    """Tests for ModelManager.list_models."""

    def test_returns_model_list(self) -> None:
        with patch.object(ModelManager, "check_installed", return_value=set()):
            mgr = ModelManager()
            models = mgr.list_models()
            assert isinstance(models, list)
            assert len(models) > 0

    def test_type_filter(self) -> None:
        with patch.object(ModelManager, "check_installed", return_value=set()):
            mgr = ModelManager()
            text_models = mgr.list_models(type_filter="text")
            for m in text_models:
                assert m.model_type == "text"


# ---------------------------------------------------------------------------
# pull_model
# ---------------------------------------------------------------------------


class TestPullModel:
    """Tests for ModelManager.pull_model."""

    def test_successful_pull(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            mgr = ModelManager(console=MagicMock())
            assert mgr.pull_model("test:model") is True

    def test_failed_pull(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            mgr = ModelManager(console=MagicMock())
            assert mgr.pull_model("test:model") is False

    def test_ollama_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            mgr = ModelManager(console=MagicMock())
            assert mgr.pull_model("test:model") is False

    def test_pull_timeout(self) -> None:
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 600)):
            mgr = ModelManager(console=MagicMock())
            assert mgr.pull_model("test:model") is False


# ---------------------------------------------------------------------------
# cache_info
# ---------------------------------------------------------------------------


class TestCacheInfo:
    """Tests for ModelManager.cache_info."""

    def test_returns_dict(self) -> None:
        mgr = ModelManager()
        result = mgr.cache_info()
        assert isinstance(result, dict)

    def test_returns_empty_on_import_error(self) -> None:
        with patch(
            "file_organizer.optimization.model_cache.ModelCache",
            side_effect=Exception("simulated cache failure"),
        ):
            mgr = ModelManager()
            result = mgr.cache_info()
            assert result == {}
