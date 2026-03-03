"""Tests for file_organizer.cli.config_cli module.

Tests the configuration management CLI commands:
- config show: Display current configuration
- config list: List available profiles
- config edit: Edit configuration profile
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.config_cli import config_app

runner = CliRunner()

pytestmark = [pytest.mark.unit]


class TestConfigShow:
    """Tests for config show command."""

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_show_default_profile(self, mock_mgr_cls):
        """Test showing default profile configuration."""
        mock_mgr = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.profile_name = "default"
        mock_cfg.default_methodology = "para"
        mock_cfg.models.text_model = "qwen2.5:3b"
        mock_cfg.models.vision_model = "qwen2.5vl:7b"
        mock_cfg.models.temperature = 0.7
        mock_cfg.models.device = "auto"
        mock_cfg.updates.check_on_startup = True
        mock_cfg.updates.interval_hours = 24
        mock_cfg.updates.repo = "curdriceaurora/Local-File-Organizer"
        mock_cfg.updates.include_prereleases = False
        mock_mgr.load.return_value = mock_cfg
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["show"])

        assert result.exit_code == 0
        assert "default" in result.stdout
        assert "para" in result.stdout
        mock_mgr.load.assert_called_once_with(profile="default")

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_show_custom_profile(self, mock_mgr_cls):
        """Test showing custom profile configuration."""
        mock_mgr = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.profile_name = "work"
        mock_cfg.default_methodology = "jd"
        mock_cfg.models.text_model = "mistral"
        mock_cfg.models.vision_model = "llava"
        mock_cfg.models.temperature = 0.5
        mock_cfg.models.device = "cuda"
        mock_cfg.updates.check_on_startup = False
        mock_cfg.updates.interval_hours = 12
        mock_cfg.updates.repo = "user/custom"
        mock_cfg.updates.include_prereleases = True
        mock_mgr.load.return_value = mock_cfg
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["show", "--profile", "work"])

        assert result.exit_code == 0
        assert "work" in result.stdout
        mock_mgr.load.assert_called_once_with(profile="work")

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_show_displays_all_settings(self, mock_mgr_cls):
        """Test show displays all configuration settings."""
        mock_mgr = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.profile_name = "test"
        mock_cfg.default_methodology = "none"
        mock_cfg.models.text_model = "model1"
        mock_cfg.models.vision_model = "model2"
        mock_cfg.models.temperature = 0.3
        mock_cfg.models.device = "cpu"
        mock_cfg.updates.check_on_startup = True
        mock_cfg.updates.interval_hours = 48
        mock_cfg.updates.repo = "test/repo"
        mock_cfg.updates.include_prereleases = False
        mock_mgr.load.return_value = mock_cfg
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["show"])

        assert result.exit_code == 0
        assert "Profile" in result.stdout
        assert "Methodology" in result.stdout
        assert "model" in result.stdout.lower()


class TestConfigList:
    """Tests for config list command."""

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_list_profiles(self, mock_mgr_cls):
        """Test listing available profiles."""
        mock_mgr = MagicMock()
        mock_mgr.list_profiles.return_value = ["default", "work", "personal"]
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["list"])

        assert result.exit_code == 0
        assert "default" in result.stdout
        assert "work" in result.stdout
        assert "personal" in result.stdout

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_list_no_profiles(self, mock_mgr_cls):
        """Test list when no profiles exist."""
        mock_mgr = MagicMock()
        mock_mgr.list_profiles.return_value = []
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["list"])

        assert result.exit_code == 0
        assert "No profiles found" in result.stdout


class TestConfigEdit:
    """Tests for config edit command."""

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_edit_text_model(self, mock_mgr_cls):
        """Test editing text model setting."""
        mock_mgr = MagicMock()
        mock_cfg = MagicMock()
        mock_mgr.load.return_value = mock_cfg
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(
            config_app, ["edit", "--text-model", "mistral:7b"]
        )

        assert result.exit_code == 0
        assert "Saved profile" in result.stdout
        assert mock_cfg.models.text_model == "mistral:7b"
        mock_mgr.save.assert_called_once()

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_edit_vision_model(self, mock_mgr_cls):
        """Test editing vision model setting."""
        mock_mgr = MagicMock()
        mock_cfg = MagicMock()
        mock_mgr.load.return_value = mock_cfg
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(
            config_app, ["edit", "--vision-model", "llava:13b"]
        )

        assert result.exit_code == 0
        mock_mgr.save.assert_called_once()
        assert mock_cfg.models.vision_model == "llava:13b"

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_edit_temperature_valid(self, mock_mgr_cls):
        """Test editing temperature with valid value."""
        mock_mgr = MagicMock()
        mock_cfg = MagicMock()
        mock_mgr.load.return_value = mock_cfg
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["edit", "--temperature", "0.5"])

        assert result.exit_code == 0
        assert mock_cfg.models.temperature == 0.5

    def test_edit_temperature_invalid_high(self):
        """Test editing temperature with value > 1.0."""
        result = runner.invoke(config_app, ["edit", "--temperature", "1.5"])

        assert result.exit_code == 1
        assert "must be between 0.0 and 1.0" in result.stdout

    def test_edit_temperature_invalid_low(self):
        """Test editing temperature with negative value."""
        result = runner.invoke(config_app, ["edit", "--temperature", "-0.5"])

        assert result.exit_code == 1
        assert "must be between 0.0 and 1.0" in result.stdout

    def test_edit_device_invalid(self):
        """Test editing device with invalid value."""
        result = runner.invoke(config_app, ["edit", "--device", "gpu"])

        assert result.exit_code == 1
        assert "device must be one of" in result.stdout

    def test_edit_device_valid_options(self):
        """Test editing device with valid options."""
        valid_devices = ["auto", "cpu", "cuda", "mps", "metal"]
        for device in valid_devices[:2]:  # Test a couple
            with patch("file_organizer.cli.config_cli.ConfigManager") as mock_mgr_cls:
                mock_mgr = MagicMock()
                mock_cfg = MagicMock()
                mock_mgr.load.return_value = mock_cfg
                mock_mgr_cls.return_value = mock_mgr

                result = runner.invoke(config_app, ["edit", "--device", device])
                assert result.exit_code == 0

    def test_edit_methodology_invalid(self):
        """Test editing methodology with invalid value."""
        result = runner.invoke(config_app, ["edit", "--methodology", "custom"])

        assert result.exit_code == 1
        assert "methodology must be one of" in result.stdout

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_edit_methodology_valid_options(self, mock_mgr_cls):
        """Test editing methodology with valid options."""
        valid_methods = ["none", "para", "jd"]
        for method in valid_methods[:2]:  # Test a couple
            mock_mgr = MagicMock()
            mock_cfg = MagicMock()
            mock_mgr.load.return_value = mock_cfg
            mock_mgr_cls.return_value = mock_mgr

            result = runner.invoke(config_app, ["edit", "--methodology", method])
            assert result.exit_code == 0

    @patch("file_organizer.cli.config_cli.ConfigManager")
    def test_edit_custom_profile(self, mock_mgr_cls):
        """Test editing a custom profile."""
        mock_mgr = MagicMock()
        mock_cfg = MagicMock()
        mock_mgr.load.return_value = mock_cfg
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(
            config_app, ["edit", "--profile", "work", "--device", "cpu"]
        )

        assert result.exit_code == 0
        mock_mgr.load.assert_called_once_with(profile="work")
