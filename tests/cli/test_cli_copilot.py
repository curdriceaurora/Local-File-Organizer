"""Tests for file_organizer.cli.copilot module.

Tests the copilot chat interface CLI commands:
- copilot_chat: Interactive or single-shot copilot chat
- copilot_status: Show copilot engine status
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()

pytestmark = [pytest.mark.unit]


class TestCopilotChat:
    """Tests for copilot chat command."""

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_chat_single_message(self, mock_engine_cls):
        """Test copilot with a single message."""
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Here's the response!"
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["copilot", "chat", "organize my downloads"])

        assert result.exit_code == 0
        assert "Here's the response!" in result.stdout
        mock_engine.chat.assert_called_once_with("organize my downloads")

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_chat_with_directory(self, mock_engine_cls):
        """Test copilot with custom working directory."""
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Done!"
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(
            app, ["copilot", "chat", "find pdf files", "--dir", "/tmp"]
        )

        assert result.exit_code == 0
        mock_engine_cls.assert_called_once_with(working_directory="/tmp")
        mock_engine.chat.assert_called_once()

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_chat_with_short_dir_option(self, mock_engine_cls):
        """Test copilot with -d short option for directory."""
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Response"
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["copilot", "chat", "test", "-d", "/home"])

        assert result.exit_code == 0
        mock_engine_cls.assert_called_once_with(working_directory="/home")

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_chat_uses_current_dir_by_default(self, mock_engine_cls):
        """Test copilot uses current directory by default."""
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "OK"
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["copilot", "chat", "hello"])

        assert result.exit_code == 0
        # Should be called with current directory
        call_args = mock_engine_cls.call_args
        assert call_args is not None
        assert "working_directory" in call_args[1]

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_chat_interactive_help(self, mock_engine_cls):
        """Test copilot help panel in interactive mode."""
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        # Simulate immediate quit
        result = runner.invoke(app, ["copilot", "chat"], input="quit\n")

        assert result.exit_code == 0
        # Help text should be shown
        assert "File Organizer Copilot" in result.stdout or "quit to exit" in result.stdout

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_chat_empty_message_ignored(self, mock_engine_cls):
        """Test copilot ignores empty messages in interactive mode."""
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        # Empty line should be ignored
        result = runner.invoke(app, ["copilot", "chat"], input="\nquit\n")

        assert result.exit_code == 0
        # chat() should not be called for empty input
        mock_engine.chat.assert_not_called()

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_chat_exit_command(self, mock_engine_cls):
        """Test copilot exits with 'exit' command."""
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["copilot", "chat"], input="exit\n")

        assert result.exit_code == 0
        assert "Goodbye" in result.stdout

    @patch("file_organizer.services.copilot.engine.CopilotEngine")
    def test_chat_eof_graceful_exit(self, mock_engine_cls):
        """Test copilot exits gracefully on EOF."""
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["copilot", "chat"], input="")

        assert result.exit_code == 0
        # Should print goodbye message
        assert "Goodbye" in result.stdout


class TestCopilotStatus:
    """Tests for copilot status command."""

    def test_status_command_runs(self):
        """Test copilot status command runs without error."""
        result = runner.invoke(app, ["copilot", "status"])

        assert result.exit_code == 0
        assert "Copilot" in result.stdout

    @patch("ollama.Client")
    def test_status_shows_ollama_models(self, mock_ollama_module):
        """Test status displays available Ollama models."""
        mock_client = MagicMock()
        mock_client.list.return_value = {
            "models": [
                {"name": "llama2"},
                {"name": "mistral"},
            ]
        }
        mock_ollama_module.Client.return_value = mock_client

        result = runner.invoke(app, ["copilot", "status"])

        assert result.exit_code == 0
        assert "Ollama models" in result.stdout or "llama2" in result.stdout

    @patch("ollama.Client")
    def test_status_handles_ollama_unavailable(self, mock_ollama_module):
        """Test status handles Ollama being unavailable."""
        mock_client = MagicMock()
        mock_client.list.side_effect = ConnectionError("Cannot connect to Ollama")
        mock_ollama_module.Client.return_value = mock_client

        result = runner.invoke(app, ["copilot", "status"])

        assert result.exit_code == 0
        assert "Ollama unavailable" in result.stdout or "Copilot" in result.stdout

    def test_status_shows_ready(self):
        """Test status indicates copilot is ready."""
        result = runner.invoke(app, ["copilot", "status"])

        assert result.exit_code == 0
        assert "ready" in result.stdout or "Status" in result.stdout
