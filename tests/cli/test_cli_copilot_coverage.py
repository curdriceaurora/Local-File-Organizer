"""Coverage tests for file_organizer.cli.copilot — uncovered lines 43-79, 85-100."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

runner = CliRunner()


class TestCopilotChat:
    """Covers the chat command — single-shot and REPL modes."""

    def test_single_shot_mode(self) -> None:
        from file_organizer.cli.copilot import copilot_app

        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Done: moved 3 files."

        with patch(
            "file_organizer.services.copilot.engine.CopilotEngine", return_value=mock_engine
        ):
            result = runner.invoke(copilot_app, ["chat", "organise ~/Downloads"])

        assert result.exit_code == 0
        assert "moved 3 files" in result.output

    def test_repl_quit(self) -> None:
        """REPL exits on 'quit'."""
        from file_organizer.cli.copilot import copilot_app

        mock_engine = MagicMock()

        with patch(
            "file_organizer.services.copilot.engine.CopilotEngine", return_value=mock_engine
        ):
            result = runner.invoke(copilot_app, ["chat"], input="quit\n")

        assert result.exit_code == 0
        assert "Goodbye" in result.output

    def test_repl_exit(self) -> None:
        """REPL exits on 'exit'."""
        from file_organizer.cli.copilot import copilot_app

        mock_engine = MagicMock()

        with patch(
            "file_organizer.services.copilot.engine.CopilotEngine", return_value=mock_engine
        ):
            result = runner.invoke(copilot_app, ["chat"], input="exit\n")

        assert result.exit_code == 0

    def test_repl_empty_input_then_quit(self) -> None:
        """Empty lines are skipped."""
        from file_organizer.cli.copilot import copilot_app

        mock_engine = MagicMock()

        with patch(
            "file_organizer.services.copilot.engine.CopilotEngine", return_value=mock_engine
        ):
            result = runner.invoke(copilot_app, ["chat"], input="\nq\n")

        assert result.exit_code == 0

    def test_repl_chat_then_quit(self) -> None:
        """Send a message in REPL then quit."""
        from file_organizer.cli.copilot import copilot_app

        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Response text"

        with patch(
            "file_organizer.services.copilot.engine.CopilotEngine", return_value=mock_engine
        ):
            result = runner.invoke(copilot_app, ["chat"], input="hello\nquit\n")

        assert result.exit_code == 0
        assert "Response text" in result.output

    def test_repl_eof_handling(self) -> None:
        """REPL handles EOF gracefully (no input at all)."""
        from file_organizer.cli.copilot import copilot_app

        mock_engine = MagicMock()

        with patch(
            "file_organizer.services.copilot.engine.CopilotEngine", return_value=mock_engine
        ):
            # Empty input triggers EOFError from console.input
            result = runner.invoke(copilot_app, ["chat"], input="")

        # Should exit cleanly
        assert result.exit_code == 0

    def test_with_directory_option(self) -> None:
        from file_organizer.cli.copilot import copilot_app

        mock_engine = MagicMock()
        mock_engine.chat.return_value = "ok"

        with patch(
            "file_organizer.services.copilot.engine.CopilotEngine", return_value=mock_engine
        ) as mock_cls:
            result = runner.invoke(copilot_app, ["chat", "--dir", "/tmp/test", "hello"])

        assert result.exit_code == 0
        mock_cls.assert_called_once_with(working_directory="/tmp/test")


class TestCopilotStatus:
    """Covers the status command — lines 85-100."""

    def test_status_with_ollama(self) -> None:
        from file_organizer.cli.copilot import copilot_app

        mock_client = MagicMock()
        mock_client.list.return_value = {
            "models": [
                {"name": "qwen:7b"},
                {"name": "llama3:latest"},
            ]
        }

        mock_ollama = MagicMock()
        mock_ollama.Client.return_value = mock_client

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            result = runner.invoke(copilot_app, ["status"])

        assert result.exit_code == 0
        assert "ready" in result.output

    def test_status_ollama_unavailable(self) -> None:
        from file_organizer.cli.copilot import copilot_app

        # Simulate ollama import succeeding but Client() raising
        mock_ollama = MagicMock()
        mock_ollama.Client.side_effect = Exception("connection refused")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            result = runner.invoke(copilot_app, ["status"])

        assert result.exit_code == 0
        assert "ready" in result.output
