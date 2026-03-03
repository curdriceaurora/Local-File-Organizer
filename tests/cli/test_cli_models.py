"""Tests for file_organizer.cli.models_cli module.

Tests the AI model management CLI commands:
- model list: List available AI models
- model pull: Download a model via Ollama
- model cache: Show model cache statistics
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.models_cli import model_app

runner = CliRunner()

pytestmark = [pytest.mark.unit]


class TestModelList:
    """Tests for model list command."""

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_list_all_models(self, mock_mgr_cls):
        """Test listing all available models."""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(model_app, ["list"])

        assert result.exit_code == 0
        mock_mgr.display_models.assert_called_once_with(type_filter=None)

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_list_text_models(self, mock_mgr_cls):
        """Test listing only text models."""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(model_app, ["list", "--type", "text"])

        assert result.exit_code == 0
        mock_mgr.display_models.assert_called_once_with(type_filter="text")

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_list_vision_models(self, mock_mgr_cls):
        """Test listing only vision models."""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(model_app, ["list", "--type", "vision"])

        assert result.exit_code == 0
        mock_mgr.display_models.assert_called_once_with(type_filter="vision")

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_list_audio_models(self, mock_mgr_cls):
        """Test listing only audio models."""
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(model_app, ["list", "--type", "audio"])

        assert result.exit_code == 0
        mock_mgr.display_models.assert_called_once_with(type_filter="audio")


class TestModelPull:
    """Tests for model pull command."""

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_pull_model_success(self, mock_mgr_cls):
        """Test successfully pulling a model."""
        mock_mgr = MagicMock()
        mock_mgr.pull_model.return_value = True
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(
            model_app, ["pull", "qwen2.5:3b-instruct-q4_K_M"]
        )

        assert result.exit_code == 0
        mock_mgr.pull_model.assert_called_once_with("qwen2.5:3b-instruct-q4_K_M")

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_pull_model_failure(self, mock_mgr_cls):
        """Test handling model pull failure."""
        mock_mgr = MagicMock()
        mock_mgr.pull_model.return_value = False
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(
            model_app, ["pull", "nonexistent:model"]
        )

        assert result.exit_code == 1

    def test_pull_missing_model_name(self):
        """Test pull without model name argument."""
        result = runner.invoke(model_app, ["pull"])

        assert result.exit_code != 0

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_pull_various_models(self, mock_mgr_cls):
        """Test pulling various model formats."""
        mock_mgr = MagicMock()
        mock_mgr.pull_model.return_value = True
        mock_mgr_cls.return_value = mock_mgr

        models = [
            "qwen2.5:3b",
            "mistral:latest",
            "llama2:13b-chat",
        ]

        for model in models:
            result = runner.invoke(model_app, ["pull", model])
            assert result.exit_code == 0


class TestModelCache:
    """Tests for model cache command."""

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_cache_with_data(self, mock_mgr_cls):
        """Test displaying cache statistics when data exists."""
        mock_mgr = MagicMock()
        mock_mgr.cache_info.return_value = {
            "hits": 42,
            "misses": 8,
            "total_size": "1.2 GB",
        }
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(model_app, ["cache"])

        assert result.exit_code == 0
        assert "hits" in result.stdout.lower() or "42" in result.stdout
        mock_mgr.cache_info.assert_called_once()

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_cache_no_data(self, mock_mgr_cls):
        """Test cache command when no cache data exists."""
        mock_mgr = MagicMock()
        mock_mgr.cache_info.return_value = None
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(model_app, ["cache"])

        assert result.exit_code == 0
        assert "No cache data" in result.stdout

    @patch("file_organizer.cli.models_cli.ModelManager")
    def test_cache_empty_data(self, mock_mgr_cls):
        """Test cache command with empty cache data."""
        mock_mgr = MagicMock()
        mock_mgr.cache_info.return_value = {}
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(model_app, ["cache"])

        assert result.exit_code == 0
