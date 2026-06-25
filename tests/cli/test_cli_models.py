"""Tests for the model CLI sub-app (models_cli.py).

Tests ``model list``, ``model pull``, and ``model cache`` commands.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit]

runner = CliRunner()


# ---------------------------------------------------------------------------
# model list
# ---------------------------------------------------------------------------


class TestModelList:
    """Tests for ``model list``."""

    @patch("file_organizer.models.model_manager.ModelManager")
    def test_list_all_models(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["model", "list"])
        assert result.exit_code == 0
        mock_mgr.display_models.assert_called_once_with(type_filter=None)

    @patch("file_organizer.models.model_manager.ModelManager")
    def test_list_filter_by_type(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["model", "list", "--type", "vision"])
        assert result.exit_code == 0
        mock_mgr.display_models.assert_called_once_with(type_filter="vision")


# ---------------------------------------------------------------------------
# model pull
# ---------------------------------------------------------------------------


class TestModelPull:
    """Tests for ``model pull``."""

    @patch("file_organizer.models.model_manager.ModelManager")
    def test_pull_success(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.pull_model.return_value = True

        result = runner.invoke(app, ["model", "pull", "qwen2.5:3b"])
        assert result.exit_code == 0
        mock_mgr.pull_model.assert_called_once_with(name="qwen2.5:3b")

    @patch("file_organizer.models.model_manager.ModelManager")
    def test_pull_failure(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.pull_model.return_value = False

        result = runner.invoke(app, ["model", "pull", "nonexistent:model"])
        assert result.exit_code == 1
        mock_mgr.pull_model.assert_called_once_with(name="nonexistent:model")


# ---------------------------------------------------------------------------
# model cache
# ---------------------------------------------------------------------------


class TestModelCache:
    """Tests for ``model cache``."""

    @patch("file_organizer.models.model_manager.ModelManager")
    def test_cache_with_data(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.cache_info.return_value = {
            "Total size": "2.5 GB",
            "Models cached": "3",
        }

        result = runner.invoke(app, ["model", "cache"])
        assert result.exit_code == 0
        assert "2.5 GB" in result.output

    @patch("file_organizer.models.model_manager.ModelManager")
    def test_cache_empty(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.cache_info.return_value = None

        result = runner.invoke(app, ["model", "cache"])
        assert result.exit_code == 0
        assert "No cache data" in result.output
