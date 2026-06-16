"""Integration tests for cli/config_cli.py.

Covers:
  - ``config show`` / ``config list`` / ``config edit`` happy paths against a
    real ``ConfigManager`` writing under a temporary config directory.
  - ``config edit`` refusing to overwrite a profile whose on-disk schema version
    is unsupported (the ``UnsupportedConfigVersionError`` handler — lines
    100, 101, 107 of config_cli.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = pytest.mark.integration

runner = CliRunner()


# ---------------------------------------------------------------------------
# UnsupportedConfigVersionError handler (lines 100, 101, 107)
# ---------------------------------------------------------------------------


class TestConfigEditUnsupportedVersion:
    @patch("file_organizer.config.ConfigManager")
    def test_edit_refuses_unsupported_version(self, mock_cls: MagicMock) -> None:
        from file_organizer.config.manager import UnsupportedConfigVersionError

        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.load.return_value = MagicMock()
        mock_mgr.save.side_effect = UnsupportedConfigVersionError("default", "99.0")

        result = runner.invoke(app, ["config", "edit", "--methodology", "para"])

        assert result.exit_code == 1
        assert "unsupported" in result.output.lower()
        mock_mgr.load.assert_called_once_with(profile="default")
        mock_mgr.save.assert_called_once()


# ---------------------------------------------------------------------------
# Real ConfigManager happy paths (config_dir pinned under tmp_path)
# ---------------------------------------------------------------------------


class TestConfigEditRealManager:
    """Exercise the CLI against a real ConfigManager rooted under tmp_path.

    ``config_edit`` instantiates ``ConfigManager()`` with no directory, which
    captures ``DEFAULT_CONFIG_DIR`` (resolved at import). Repointing that module
    constant keeps all reads/writes inside the temporary directory.
    """

    def test_edit_then_show_roundtrips_methodology(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("file_organizer.config.manager.DEFAULT_CONFIG_DIR", tmp_path)

        edit = runner.invoke(app, ["config", "edit", "--methodology", "para"])
        assert edit.exit_code == 0
        assert "Saved" in edit.output
        # The profile file was actually written under the temp config dir.
        assert (tmp_path / "config.yaml").exists()

        show = runner.invoke(app, ["config", "show"])
        assert show.exit_code == 0
        assert "para" in show.output

    def test_edit_text_model_persists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("file_organizer.config.manager.DEFAULT_CONFIG_DIR", tmp_path)

        edit = runner.invoke(app, ["config", "edit", "--text-model", "llama3:8b"])
        assert edit.exit_code == 0

        show = runner.invoke(app, ["config", "show"])
        assert show.exit_code == 0
        assert "llama3:8b" in show.output

    def test_list_reports_saved_profile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("file_organizer.config.manager.DEFAULT_CONFIG_DIR", tmp_path)

        # No profiles yet.
        empty = runner.invoke(app, ["config", "list"])
        assert empty.exit_code == 0
        assert "No profiles found" in empty.output

        # Create one via edit, then list should report it.
        runner.invoke(app, ["config", "edit", "--profile", "work", "--device", "cpu"])
        listed = runner.invoke(app, ["config", "list"])
        assert listed.exit_code == 0
        assert "work" in listed.output
