"""Tests for consolidated CLI entry points (desktop and docs subcommands)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


@pytest.fixture
def mock_launch() -> Generator[MagicMock, None, None]:
    """Fixture to mock desktop.app.launch."""
    with patch("file_organizer.desktop.app.launch") as mock:
        yield mock


@pytest.fixture
def mock_shutil_which() -> Generator[MagicMock, None, None]:
    """Fixture to mock shutil.which."""
    with patch("shutil.which") as mock:
        yield mock


@pytest.fixture
def mock_subprocess_run() -> Generator[MagicMock, None, None]:
    """Fixture to mock subprocess.run."""
    with patch("subprocess.run") as mock:
        mock.return_value.returncode = 0
        yield mock


class TestDesktopSubcommand:
    """Verify 'fo desktop' command behavior and error handling."""

    def test_desktop_command_registered(self) -> None:
        """Verify the desktop command is registered in the Typer app."""
        result = runner.invoke(app, ["desktop", "--help"])
        assert result.exit_code == 0
        assert "Launch the native desktop window" in result.output

    def test_desktop_command_success(self, mock_launch: MagicMock) -> None:
        """Verify fo desktop successfully launches the window with custom options."""
        result = runner.invoke(
            app,
            [
                "desktop",
                "--title",
                "Custom Window Title",
                "--width",
                "1024",
                "--height",
                "768",
            ],
        )
        assert result.exit_code == 0
        mock_launch.assert_called_once_with(
            title="Custom Window Title",
            width=1024,
            height=768,
        )

    def test_desktop_command_import_error(self) -> None:
        """Verify fo desktop prints a friendly error when pywebview is missing."""
        # Simulate pywebview missing by patching the import block
        with patch.dict("sys.modules", {"file_organizer.desktop.app": None}):
            result = runner.invoke(app, ["desktop"])
            assert result.exit_code == 1
            assert "pywebview is not installed" in result.output
            assert "pip install 'file-organizer[desktop]'" in result.output

    def test_desktop_command_launch_error(self, mock_launch: MagicMock) -> None:
        """Verify fo desktop handles launch failures gracefully."""
        mock_launch.side_effect = RuntimeError("Failed to allocate window")
        result = runner.invoke(app, ["desktop"])
        assert result.exit_code == 1
        assert "Error launching desktop: Failed to allocate window" in result.output


class TestDocsSubcommand:
    """Verify 'fo docs' command behavior, build/serve modes, and validations."""

    def test_docs_command_registered(self) -> None:
        """Verify the docs command is registered in the Typer app."""
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        assert "Build or serve the project documentation" in result.output

    def test_docs_command_missing_mkdocs(self, mock_shutil_which: MagicMock) -> None:
        """Verify fo docs exits cleanly and suggests installation if mkdocs is missing."""
        mock_shutil_which.return_value = None
        result = runner.invoke(app, ["docs"])
        assert result.exit_code == 1
        assert "mkdocs is not installed" in result.output
        assert "pip install 'file-organizer[docs]'" in result.output

    def test_docs_command_missing_config(
        self, mock_shutil_which: MagicMock, tmp_path: Path
    ) -> None:
        """Verify fo docs fails gracefully if mkdocs.yml is not found."""
        mock_shutil_which.return_value = "/usr/local/bin/mkdocs"

        # Run from a temporary directory without mkdocs.yml
        with patch("pathlib.Path.exists", return_value=False):
            result = runner.invoke(app, ["docs"])
            assert result.exit_code == 1
            assert "mkdocs.yml not found" in result.output

    def test_docs_command_build_success(
        self, mock_shutil_which: MagicMock, mock_subprocess_run: MagicMock
    ) -> None:
        """Verify fo docs --build compiles documentation to HTML."""
        mock_shutil_which.return_value = "/usr/local/bin/mkdocs"

        # Mock mkdocs.yml presence check
        with patch("pathlib.Path.exists", return_value=True):
            result = runner.invoke(app, ["docs", "--build"])
            assert result.exit_code == 0
            assert "Building documentation to HTML" in result.output
            assert "Documentation built successfully" in result.output

            mock_subprocess_run.assert_called_once()
            args = mock_subprocess_run.call_args[0][0]
            assert args == ["/usr/local/bin/mkdocs", "build"]

    def test_docs_command_build_error(
        self, mock_shutil_which: MagicMock, mock_subprocess_run: MagicMock
    ) -> None:
        """Verify fo docs --build handles compilation failure cleanly."""
        mock_shutil_which.return_value = "/usr/local/bin/mkdocs"
        mock_subprocess_run.return_value.returncode = 1

        with patch("pathlib.Path.exists", return_value=True):
            result = runner.invoke(app, ["docs", "--build"])
            assert result.exit_code == 1
            assert "Failed to build documentation" in result.output

    def test_docs_command_serve_success(
        self, mock_shutil_which: MagicMock, mock_subprocess_run: MagicMock
    ) -> None:
        """Verify fo docs serves documentation with default options."""
        mock_shutil_which.return_value = "/usr/local/bin/mkdocs"

        with patch("pathlib.Path.exists", return_value=True):
            result = runner.invoke(app, ["docs", "--host", "0.0.0.0", "--port", "9000"])
            assert result.exit_code == 0
            assert "Starting documentation server at http://0.0.0.0:9000/" in result.output

            mock_subprocess_run.assert_called_once()
            args = mock_subprocess_run.call_args[0][0]
            assert args == ["/usr/local/bin/mkdocs", "serve", "--dev-addr", "0.0.0.0:9000"]
