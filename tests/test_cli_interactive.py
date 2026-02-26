"""Tests for CLI interactive prompts and completion helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.unit
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
class TestInteractiveFlags:
    """Tests for interactive module flag management."""

    def test_set_flags(self) -> None:
        from file_organizer.cli import interactive

        interactive.set_flags(yes=True, no_interactive=False)
        assert interactive._yes is True
        assert interactive._no_interactive is False

        interactive.set_flags(yes=False, no_interactive=True)
        assert interactive._yes is False
        assert interactive._no_interactive is True

        # Reset
        interactive.set_flags(yes=False, no_interactive=False)


@pytest.mark.unit
class TestConfirmAction:
    """Tests for confirm_action."""

    def test_auto_confirm_with_yes(self) -> None:
        from file_organizer.cli import interactive

        interactive.set_flags(yes=True)
        assert interactive.confirm_action("Delete?") is True
        interactive.set_flags(yes=False)

    def test_returns_default_when_no_interactive(self) -> None:
        from file_organizer.cli import interactive

        interactive.set_flags(no_interactive=True)
        assert interactive.confirm_action("Do?", default=False) is False
        assert interactive.confirm_action("Do?", default=True) is True
        interactive.set_flags(no_interactive=False)

    def test_prompts_user_normally(self) -> None:
        from file_organizer.cli import interactive

        interactive.set_flags(yes=False, no_interactive=False)
        with patch.object(interactive, "Confirm") as mock_confirm:
            mock_confirm.ask.return_value = True
            result = interactive.confirm_action("Proceed?")
            assert result is True
            mock_confirm.ask.assert_called_once()


@pytest.mark.unit
class TestPromptChoice:
    """Tests for prompt_choice."""

    def test_returns_default_when_no_interactive(self) -> None:
        from file_organizer.cli import interactive

        interactive.set_flags(no_interactive=True)
        result = interactive.prompt_choice("Pick", ["a", "b", "c"], default="b")
        assert result == "b"
        interactive.set_flags(no_interactive=False)


@pytest.mark.unit
class TestCreateProgress:
    """Tests for create_progress."""

    def test_returns_progress_instance(self) -> None:
        from rich.progress import Progress

        from file_organizer.cli.interactive import create_progress

        prog = create_progress()
        assert isinstance(prog, Progress)


@pytest.mark.unit
class TestMainCallbackFlags:
    """Test that global flags are wired into main.py."""

    def test_main_module_has_yes_flag(self) -> None:
        import importlib

        main_mod = importlib.import_module("file_organizer.cli.main")
        assert hasattr(main_mod, "_yes")
        assert hasattr(main_mod, "_no_interactive")
