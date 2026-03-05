"""Tests for the copilot CLI sub-app (copilot.py).

Tests the ``copilot chat`` single-shot mode and ``copilot status`` commands.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit]

runner = CliRunner()


# ---------------------------------------------------------------------------
# copilot chat (single-shot)
# ---------------------------------------------------------------------------


class TestCopilotChat:
    """Tests for ``copilot chat`` in single-shot mode."""

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_single_shot_message(self, mock_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_cls.return_value = mock_engine
        mock_engine.chat.return_value = "I organized 5 files."

        result = runner.invoke(app, ["copilot", "chat", "organize my downloads"])
        assert result.exit_code == 0
        assert "I organized 5 files." in result.output
        mock_engine.chat.assert_called_once_with("organize my downloads")

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_single_shot_with_dir(self, mock_cls: MagicMock, tmp_path) -> None:
        mock_engine = MagicMock()
        mock_cls.return_value = mock_engine
        mock_engine.chat.return_value = "Done."

        result = runner.invoke(
            app,
            ["copilot", "chat", "--dir", str(tmp_path), "list files"],
        )
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(working_directory=str(tmp_path))

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_chat_help(self, mock_cls: MagicMock) -> None:
        result = runner.invoke(app, ["copilot", "chat", "--help"])
        assert result.exit_code == 0
        assert "message" in result.output.lower() or "MESSAGE" in result.output


# ---------------------------------------------------------------------------
# copilot status
# ---------------------------------------------------------------------------


class TestCopilotStatus:
    """Tests for ``copilot status``."""

    def test_status_without_ollama(self) -> None:
        with patch.dict("sys.modules", {"ollama": None}):
            result = runner.invoke(app, ["copilot", "status"])
            assert result.exit_code == 0
            assert "Copilot" in result.output

    def test_status_with_ollama(self) -> None:
        mock_ollama = MagicMock()
        mock_client = MagicMock()
        mock_ollama.Client.return_value = mock_client
        mock_client.list.return_value = {"models": [{"name": "qwen2.5:3b"}]}

        with (
            patch.dict("sys.modules", {"ollama": mock_ollama}),
            patch("file_organizer.cli.copilot.console"),
        ):
            result = runner.invoke(app, ["copilot", "status"])
        assert result.exit_code == 0
        mock_client.list.assert_called_once()
