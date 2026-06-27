"""Tests for CLI interactive prompts and completion helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.unit
@pytest.mark.integration
class TestCompletion:
    """Tests for path completion callbacks."""

    def test_complete_directory_returns_dirs(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_directory

        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "file.txt").touch()

        results = list(complete_directory(str(tmp_path) + "/"))
        paths = [r[0] for r in results]
        assert any("alpha" in p for p in paths)
        assert any("beta" in p for p in paths)
        # file.txt should NOT appear (only dirs)
        assert not any("file.txt" in p for p in paths)

    def test_complete_directory_prefix(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_directory

        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()

        results = list(complete_directory(str(tmp_path / "al")))
        paths = [r[0] for r in results]
        assert any("alpha" in p for p in paths)
        assert not any("beta" in p for p in paths)

    def test_complete_directory_nonexistent(self) -> None:
        from file_organizer.cli.completion import complete_directory

        results = list(complete_directory("/nonexistent_xyz_abc/foo"))
        assert results == []

    def test_complete_file_returns_all(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_file

        (tmp_path / "dir1").mkdir()
        (tmp_path / "file.py").touch()

        results = list(complete_file(str(tmp_path) + "/"))
        paths = [r[0] for r in results]
        assert any("dir1" in p for p in paths)
        assert any("file.py" in p for p in paths)


@pytest.mark.unit
@pytest.mark.integration
class TestConfirmAction:
    """Tests for confirm_action."""

    def test_auto_confirm_with_yes(self) -> None:
        from file_organizer.cli import interactive
        from file_organizer.cli.state import CLIState

        with patch.object(interactive, "_get_state", return_value=CLIState(yes=True)):
            assert interactive.confirm_action("Delete?") is True

    def test_returns_default_when_no_interactive(self) -> None:
        from file_organizer.cli import interactive
        from file_organizer.cli.state import CLIState

        with patch.object(interactive, "_get_state", return_value=CLIState(no_interactive=True)):
            assert interactive.confirm_action("Do?", default=False) is False
            assert interactive.confirm_action("Do?", default=True) is True

    def test_prompts_user_normally(self) -> None:
        from file_organizer.cli import interactive
        from file_organizer.cli.state import CLIState

        with (
            patch.object(interactive, "_get_state", return_value=CLIState()),
            patch.object(interactive, "Confirm") as mock_confirm,
        ):
            mock_confirm.ask.return_value = True
            result = interactive.confirm_action("Proceed?")
            assert result is True
            mock_confirm.ask.assert_called_once()


@pytest.mark.unit
@pytest.mark.integration
@pytest.mark.ci
class TestPromptChoice:
    """Tests for prompt_choice."""

    def test_returns_default_when_no_interactive(self) -> None:
        from file_organizer.cli import interactive
        from file_organizer.cli.state import CLIState

        with patch.object(interactive, "_get_state", return_value=CLIState(no_interactive=True)):
            result = interactive.prompt_choice("Pick", ["a", "b", "c"], default="b")
            assert result == "b"

    def test_prompts_with_default_in_interactive_mode(self) -> None:
        from file_organizer.cli import interactive
        from file_organizer.cli.state import CLIState

        with (
            patch.object(interactive, "_get_state", return_value=CLIState()),
            patch.object(interactive, "Prompt") as mock_prompt,
        ):
            mock_prompt.ask.return_value = "a"
            result = interactive.prompt_choice("Pick", ["a", "b"], default="a")
            assert result == "a"
            mock_prompt.ask.assert_called_once()
            # `default` arg is forwarded when provided
            assert mock_prompt.ask.call_args.kwargs.get("default") == "a"

    def test_prompts_without_default_in_interactive_mode(self) -> None:
        from file_organizer.cli import interactive
        from file_organizer.cli.state import CLIState

        with (
            patch.object(interactive, "_get_state", return_value=CLIState()),
            patch.object(interactive, "Prompt") as mock_prompt,
        ):
            mock_prompt.ask.return_value = "b"
            result = interactive.prompt_choice("Pick", ["a", "b"], default=None)
            assert result == "b"
            # default is *not* forwarded when the caller didn't supply one
            assert "default" not in mock_prompt.ask.call_args.kwargs


@pytest.mark.unit
@pytest.mark.integration
class TestPromptDirectory:
    """Tests for prompt_directory — the loop that keeps asking until a
    real directory is provided. D#167 removed the legacy dedupe CLI's
    directory prompt, which was the only integration path hitting this.
    """

    def test_returns_resolved_path_on_valid_directory(self, tmp_path: Path) -> None:
        from file_organizer.cli import interactive

        with patch.object(interactive, "Prompt") as mock_prompt:
            mock_prompt.ask.return_value = str(tmp_path)
            result = interactive.prompt_directory("Where?")
        assert result == tmp_path.resolve()

    def test_reprompts_until_valid_directory(self, tmp_path: Path) -> None:
        from file_organizer.cli import interactive

        good = tmp_path / "exists"
        good.mkdir()

        with patch.object(interactive, "Prompt") as mock_prompt:
            # First two answers are invalid; third is the real dir.
            mock_prompt.ask.side_effect = [
                str(tmp_path / "nope1"),
                str(tmp_path / "nope2"),
                str(good),
            ]
            result = interactive.prompt_directory()

        assert result == good.resolve()
        assert mock_prompt.ask.call_count == 3


@pytest.mark.unit
@pytest.mark.integration
class TestCreateProgress:
    """Tests for create_progress."""

    def test_returns_progress_instance(self) -> None:
        from rich.progress import Progress

        from file_organizer.cli.interactive import create_progress

        prog = create_progress()
        assert isinstance(prog, Progress)


@pytest.mark.unit
@pytest.mark.integration
class TestMainCallbackFlags:
    """Test that global flags are wired into main.py."""

    def test_cli_state_has_yes_and_no_interactive_flags(self) -> None:
        from file_organizer.cli.state import CLIState

        state = CLIState()
        assert state.yes is False
        assert state.no_interactive is False

        state = CLIState(yes=True, no_interactive=True)
        assert state.yes is True
        assert state.no_interactive is True
