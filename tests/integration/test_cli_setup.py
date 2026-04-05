"""Integration tests for the setup wizard CLI sub-app.

Covers: setup run (quick-start, power-user, invalid mode, dry-run, validation
failure, save confirmation), and the default callback.

All external service calls (SetupWizard, console, confirm_action) are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.setup import setup_app

pytestmark = [pytest.mark.integration, pytest.mark.ci]

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_capabilities(
    ollama_running: bool = True,
    ollama_installed: bool = True,
    models: list | None = None,
) -> MagicMock:
    """Build a minimal SystemCapabilities mock that the CLI reads."""
    caps = MagicMock()
    caps.hardware.gpu_type.value = "none"
    caps.hardware.gpu_name = None
    caps.hardware.vram_gb = 0.0
    caps.hardware.ram_gb = 8.0
    caps.hardware.cpu_cores = 4
    caps.hardware.os_name = "Linux"
    caps.hardware.recommended_text_model.return_value = "qwen2.5:3b-instruct-q4_K_M"

    caps.ollama_status.running = ollama_running
    caps.ollama_status.installed = ollama_installed
    caps.ollama_status.version = "0.3.0"
    caps.ollama_status.models_count = len(models or [])

    if models:
        caps.installed_models = models
    else:
        caps.installed_models = []

    return caps


def _make_installed_model(name: str = "qwen2.5:3b-instruct-q4_K_M") -> MagicMock:
    m = MagicMock()
    m.name = name
    m.size = 2_000_000_000
    return m


def _make_config(
    profile_name: str = "default",
    text_model: str = "qwen2.5:3b-instruct-q4_K_M",
    temperature: float = 0.5,
    framework: str = "ollama",
    device: str = "cpu",
    methodology: str = "none",
    vision_model: str | None = None,
) -> MagicMock:
    """Build a minimal AppConfig mock that the CLI reads."""
    cfg = MagicMock()
    cfg.profile_name = profile_name
    cfg.default_methodology = methodology
    cfg.models.text_model = text_model
    cfg.models.vision_model = vision_model
    cfg.models.temperature = temperature
    cfg.models.framework = framework
    cfg.models.device = device
    return cfg


# ---------------------------------------------------------------------------
# setup run — quick-start mode
# ---------------------------------------------------------------------------


class TestSetupRunQuickStart:
    def test_quick_start_ollama_running_with_models(self) -> None:
        model = _make_installed_model()
        caps = _make_capabilities(ollama_running=True, models=[model])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "quick-start"])

        assert result.exit_code == 0
        mock_wiz.detect_capabilities.assert_called_once()
        mock_wiz.generate_config.assert_called_once()
        mock_wiz.validate_config.assert_called_once()
        mock_wiz.save_config.assert_called_once()

    def test_quick_start_no_models_uses_recommended(self) -> None:
        caps = _make_capabilities(ollama_running=True, models=[])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "quick-start"])

        assert result.exit_code == 0

    def test_quick_start_ollama_installed_but_not_running(self) -> None:
        caps = _make_capabilities(ollama_running=False, ollama_installed=True, models=[])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "quick-start"])

        assert result.exit_code == 0

    def test_quick_start_ollama_not_installed(self) -> None:
        caps = _make_capabilities(ollama_running=False, ollama_installed=False, models=[])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "quick-start"])

        assert result.exit_code == 0

    def test_quick_start_model_not_recommended_falls_back_to_first(self) -> None:
        model = _make_installed_model("llama3.2:1b")
        caps = _make_capabilities(ollama_running=True, models=[model])
        # recommended returns a model NOT in the installed list
        caps.hardware.recommended_text_model.return_value = "qwen2.5:3b-instruct-q4_K_M"
        cfg = _make_config(text_model="llama3.2:1b")

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "quick-start"])

        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# setup run — invalid mode
# ---------------------------------------------------------------------------


class TestSetupRunInvalidMode:
    def test_invalid_mode_exits_1(self) -> None:
        with (
            patch("file_organizer.cli.setup.SetupWizard"),
            patch("file_organizer.cli.setup.console"),
        ):
            result = runner.invoke(setup_app, ["run", "--mode", "unknown-mode"])

        assert result.exit_code == 1

    def test_underscore_mode_normalised(self) -> None:
        """Mode 'quick_start' should be normalised to 'quick-start' (not invalid)."""
        model = _make_installed_model()
        caps = _make_capabilities(ollama_running=True, models=[model])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "quick_start"])

        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# setup run — dry_run flag
# ---------------------------------------------------------------------------


class TestSetupRunDryRun:
    def test_dry_run_does_not_save(self) -> None:
        model = _make_installed_model()
        caps = _make_capabilities(ollama_running=True, models=[model])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--dry-run"])

        assert result.exit_code == 0
        mock_wiz.save_config.assert_not_called()


# ---------------------------------------------------------------------------
# setup run — validation failure
# ---------------------------------------------------------------------------


class TestSetupRunValidationFailure:
    def test_validation_failure_exits_1(self) -> None:
        model = _make_installed_model()
        caps = _make_capabilities(ollama_running=True, models=[model])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (
                False,
                ["Selected model is not installed", "Invalid temperature"],
            )

            result = runner.invoke(setup_app, ["run", "--mode", "quick-start"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# setup run — save confirmation declined
# ---------------------------------------------------------------------------


class TestSetupRunSaveDeclined:
    def test_save_declined_does_not_call_save_config(self) -> None:
        model = _make_installed_model()
        caps = _make_capabilities(ollama_running=True, models=[model])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.confirm_action", return_value=False),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "quick-start"])

        assert result.exit_code == 0
        mock_wiz.save_config.assert_not_called()


# ---------------------------------------------------------------------------
# setup run — power-user mode (prompt_choice mocked)
# ---------------------------------------------------------------------------


class TestSetupRunPowerUser:
    def test_power_user_prompts_and_saves(self) -> None:
        model = _make_installed_model()
        caps = _make_capabilities(ollama_running=True, models=[model])
        cfg = _make_config(framework="ollama")

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.prompt_choice", return_value="ollama"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
            patch("typer.prompt", return_value="0.7"),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "power-user"])

        assert result.exit_code == 0
        mock_wiz.save_config.assert_called_once()

    def test_power_user_invalid_temperature_uses_default(self) -> None:
        model = _make_installed_model()
        caps = _make_capabilities(ollama_running=True, models=[model])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.prompt_choice", return_value="ollama"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
            patch("typer.prompt", return_value="not-a-float"),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "power-user"])

        assert result.exit_code == 0
        # Temperature should have defaulted to 0.5
        call_kwargs = mock_wiz.generate_config.call_args
        settings_arg = call_kwargs[0][1]
        assert settings_arg["temperature"] == 0.5

    def test_power_user_no_installed_models(self) -> None:
        """Power-user mode skips model prompt when no models are installed."""
        caps = _make_capabilities(ollama_running=True, models=[])
        cfg = _make_config()

        with (
            patch("file_organizer.cli.setup.SetupWizard") as mock_wiz_cls,
            patch("file_organizer.cli.setup.console"),
            patch("file_organizer.cli.setup.prompt_choice", return_value="none"),
            patch("file_organizer.cli.setup.confirm_action", return_value=True),
            patch("typer.prompt", return_value="0.5"),
        ):
            mock_wiz = mock_wiz_cls.return_value
            mock_wiz.detect_capabilities.return_value = caps
            mock_wiz.generate_config.return_value = cfg
            mock_wiz.validate_config.return_value = (True, [])

            result = runner.invoke(setup_app, ["run", "--mode", "power-user"])

        assert result.exit_code == 0
