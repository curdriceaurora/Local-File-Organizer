"""Integration tests for CLI config commands.

Covers: config show, config list (empty / with profiles), config edit
(valid field updates, temperature/device/methodology validation failures).
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.integration]

runner = CliRunner()


class TestConfigShow:
    def test_config_show_default_profile_exits_zero(self) -> None:
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0

    def test_config_show_prints_profile_fields(self) -> None:
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        # These labels appear in the output for every profile
        assert "profile" in result.output.lower() or "text model" in result.output.lower()

    def test_config_show_explicit_profile_name(self) -> None:
        result = runner.invoke(app, ["config", "show", "--profile", "default"])
        assert result.exit_code == 0


class TestConfigList:
    def test_config_list_exits_zero(self) -> None:
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0

    def test_config_list_empty_shows_hint(self) -> None:
        """When no profiles exist, the output contains a guidance message."""
        from unittest.mock import patch

        with patch(
            "file_organizer.config.ConfigManager.list_profiles",
            return_value=[],
        ):
            result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "no profiles" in result.output.lower() or "config edit" in result.output.lower()

    def test_config_list_with_profiles_prints_names(self) -> None:
        from unittest.mock import patch

        with patch(
            "file_organizer.config.ConfigManager.list_profiles",
            return_value=["default", "work", "personal"],
        ):
            result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "work" in result.output
        assert "personal" in result.output


class TestConfigEdit:
    def test_config_edit_valid_text_model(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--text-model", "llama3:8b"])
        assert result.exit_code == 0
        assert "saved" in result.output.lower()

    def test_config_edit_valid_vision_model(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--vision-model", "llava:7b"])
        assert result.exit_code == 0
        assert "saved" in result.output.lower()

    def test_config_edit_valid_temperature(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--temperature", "0.7"])
        assert result.exit_code == 0
        assert "saved" in result.output.lower()

    def test_config_edit_temperature_zero(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--temperature", "0.0"])
        assert result.exit_code == 0

    def test_config_edit_temperature_one(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--temperature", "1.0"])
        assert result.exit_code == 0

    def test_config_edit_temperature_above_range_exits_1(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--temperature", "1.5"])
        assert result.exit_code == 1
        assert "temperature" in result.output.lower()

    def test_config_edit_temperature_below_range_exits_1(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--temperature", "-0.1"])
        assert result.exit_code == 1
        assert "temperature" in result.output.lower()

    def test_config_edit_valid_device_cpu(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--device", "cpu"])
        assert result.exit_code == 0

    def test_config_edit_valid_device_cuda(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--device", "cuda"])
        assert result.exit_code == 0

    def test_config_edit_valid_device_mps(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--device", "mps"])
        assert result.exit_code == 0

    def test_config_edit_valid_device_metal(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--device", "metal"])
        assert result.exit_code == 0

    def test_config_edit_valid_device_auto(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--device", "auto"])
        assert result.exit_code == 0

    def test_config_edit_invalid_device_exits_1(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--device", "gpu"])
        assert result.exit_code == 1
        assert "device" in result.output.lower()

    def test_config_edit_valid_methodology_none(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--methodology", "none"])
        assert result.exit_code == 0

    def test_config_edit_valid_methodology_para(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--methodology", "para"])
        assert result.exit_code == 0

    def test_config_edit_valid_methodology_jd(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--methodology", "jd"])
        assert result.exit_code == 0

    def test_config_edit_invalid_methodology_exits_1(self) -> None:
        result = runner.invoke(app, ["config", "edit", "--methodology", "gtd"])
        assert result.exit_code == 1
        assert "methodology" in result.output.lower()

    def test_config_edit_multiple_fields_at_once(self) -> None:
        result = runner.invoke(
            app,
            [
                "config",
                "edit",
                "--text-model",
                "qwen2.5:7b",
                "--temperature",
                "0.3",
                "--device",
                "cpu",
            ],
        )
        assert result.exit_code == 0
        assert "saved" in result.output.lower()

    def test_config_edit_persists_text_model(self) -> None:
        """After editing, config show reflects the updated text model."""
        runner.invoke(app, ["config", "edit", "--text-model", "llama3.2:3b"])
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "llama3.2:3b" in result.output

    def test_config_edit_custom_profile(self) -> None:
        result = runner.invoke(
            app,
            [
                "config",
                "edit",
                "--profile",
                "test-profile",
                "--text-model",
                "mistral:7b",
            ],
        )
        assert result.exit_code == 0
        assert "test-profile" in result.output
