"""Tests for the config CLI sub-app (config_cli.py).

Tests the ``config show``, ``config list``, and ``config edit`` commands
using mocked ConfigManager.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit]

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reload_config_cli_under_unit_context() -> None:
    """Force config_cli's module-level code to execute under this file's unit context.

    ``cli/lazy.py`` imports ``config_cli`` lazily on first ``fo config ...``
    dispatch and Python only runs a module's top-level code once per
    process; whichever test happens to be the first to trigger that import
    in the full combined run is the only one whose coverage context sees
    those lines. Reloading here pins that first execution to this
    unit-marked file regardless of collection/run order (same pattern as
    the ``file_organizer.api.db`` reload in tests/api/test_db_module.py).
    """
    import importlib

    import file_organizer.cli.config_cli

    importlib.reload(file_organizer.cli.config_cli)


def _make_config(
    profile_name: str = "default",
    methodology: str = "none",
    text_model: str = "qwen2.5:3b",
    vision_model: str = "qwen2.5vl:7b",
    temperature: float = 0.7,
    device: str = "auto",
    check_on_startup: bool = True,
    interval_hours: int = 24,
    repo: str = "curdriceaurora/fo-core",
    include_prereleases: bool = False,
) -> MagicMock:
    """Return a mock AppConfig object."""
    cfg = MagicMock()
    cfg.profile_name = profile_name
    cfg.default_methodology = methodology
    cfg.models.text_model = text_model
    cfg.models.vision_model = vision_model
    cfg.models.temperature = temperature
    cfg.models.device = device
    cfg.updates.check_on_startup = check_on_startup
    cfg.updates.interval_hours = interval_hours
    cfg.updates.repo = repo
    cfg.updates.include_prereleases = include_prereleases
    return cfg


# ---------------------------------------------------------------------------
# config show
# ---------------------------------------------------------------------------


class TestConfigShow:
    """Tests for ``config show``."""

    @patch("file_organizer.config.ConfigManager")
    def test_show_default_profile(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.load.return_value = _make_config()

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "qwen2.5:3b" in result.output
        assert "qwen2.5vl:7b" in result.output

    @patch("file_organizer.config.ConfigManager")
    def test_show_custom_profile(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.load.return_value = _make_config(profile_name="work")

        result = runner.invoke(app, ["config", "show", "--profile", "work"])
        assert result.exit_code == 0
        assert "work" in result.output
        mock_mgr.load.assert_called_once_with(profile="work")


# ---------------------------------------------------------------------------
# config list
# ---------------------------------------------------------------------------


class TestConfigList:
    """Tests for ``config list``."""

    @patch("file_organizer.config.ConfigManager")
    def test_list_profiles(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.list_profiles.return_value = ["default", "work", "personal"]

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "work" in result.output
        assert "personal" in result.output

    @patch("file_organizer.config.ConfigManager")
    def test_list_empty(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.list_profiles.return_value = []

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "No profiles found" in result.output


# ---------------------------------------------------------------------------
# config edit
# ---------------------------------------------------------------------------


class TestConfigEdit:
    """Tests for ``config edit``."""

    @patch("file_organizer.config.ConfigManager")
    def test_edit_text_model(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        cfg = _make_config()
        mock_mgr.load.return_value = cfg

        result = runner.invoke(app, ["config", "edit", "--text-model", "llama3:8b"])
        assert result.exit_code == 0
        assert "Saved" in result.output
        assert cfg.models.text_model == "llama3:8b"

    @patch("file_organizer.config.ConfigManager")
    def test_edit_invalid_temperature(self, mock_cls: MagicMock) -> None:
        result = runner.invoke(app, ["config", "edit", "--temperature", "2.5"])
        assert result.exit_code == 1
        assert "temperature must be between" in result.output
        mock_cls.assert_not_called()  # invalid input must never touch config

    @patch("file_organizer.config.ConfigManager")
    def test_edit_invalid_device(self, mock_cls: MagicMock) -> None:
        # Step 3 swapped the validation-error format from "device must be
        # one of [...]" to the hint-rich "Invalid value 'tpu' for device.
        # Valid values: ..." style (lists valid values + "did you mean").
        # Use wrap-immune word checks since Rich may break long messages.
        result = runner.invoke(app, ["config", "edit", "--device", "tpu"])
        assert result.exit_code == 1
        normalized = " ".join(result.output.lower().split())
        assert "invalid value" in normalized
        assert "device" in normalized
        assert "'tpu'" in normalized
        mock_cls.assert_not_called()  # invalid input must never touch config

    @patch("file_organizer.config.ConfigManager")
    def test_edit_invalid_methodology(self, mock_cls: MagicMock) -> None:
        result = runner.invoke(app, ["config", "edit", "--methodology", "custom"])
        assert result.exit_code == 1
        normalized = " ".join(result.output.lower().split())
        assert "invalid value" in normalized
        assert "methodology" in normalized
        assert "'custom'" in normalized
        mock_cls.assert_not_called()  # invalid input must never touch config

    @patch("file_organizer.config.ConfigManager")
    def test_edit_valid_device(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        cfg = _make_config()
        mock_mgr.load.return_value = cfg

        result = runner.invoke(app, ["config", "edit", "--device", "cpu"])
        assert result.exit_code == 0
        assert cfg.models.device == "cpu"

    @patch("file_organizer.config.ConfigManager")
    def test_edit_methodology(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        cfg = _make_config()
        mock_mgr.load.return_value = cfg

        result = runner.invoke(app, ["config", "edit", "--methodology", "para"])
        assert result.exit_code == 0
        assert cfg.default_methodology == "para"

    @patch("file_organizer.config.ConfigManager")
    def test_edit_unsupported_config_version_exits_with_error(self, mock_cls: MagicMock) -> None:
        from file_organizer.config.manager import UnsupportedConfigVersionError

        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        cfg = _make_config()
        mock_mgr.load.return_value = cfg
        mock_mgr.save.side_effect = UnsupportedConfigVersionError("default", 99)

        result = runner.invoke(app, ["config", "edit", "--text-model", "llama3:8b"])

        normalized = " ".join(result.output.split())
        assert result.exit_code == 1
        assert "unsupported config version" in normalized
        assert "on-disk schema version 99 is unsupported" in normalized
        assert "Saved" not in normalized
