"""Tests for the config CLI sub-app (config_cli.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from file_organizer.cli.main import app
from file_organizer.config.manager import UnsupportedConfigVersionError

runner = CliRunner()


class TestConfigEdit:
    """Tests for `fo config edit`."""

    @patch("file_organizer.config.ConfigManager")
    def test_edit_unsupported_version_prints_friendly_error_and_exits_1(
        self, mock_cm_cls: MagicMock
    ) -> None:
        """ConfigManager.save() raising UnsupportedConfigVersionError must
        produce a clean error message + exit code 1, not a raw traceback."""
        mock_mgr = MagicMock()
        mock_cm_cls.return_value = mock_mgr
        mock_mgr.save.side_effect = UnsupportedConfigVersionError("default", "99.0")

        result = runner.invoke(app, ["config", "edit", "--text-model", "gpt-x"])

        assert result.exit_code == 1
        assert "unsupported" in result.output.lower()
        assert "Traceback" not in result.output
