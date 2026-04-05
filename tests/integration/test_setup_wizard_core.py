"""Integration tests for the SetupWizard core module.

Covers: WizardMode, SetupStatus, WizardResult, SystemCapabilities.to_dict(),
SetupWizard.detect_capabilities(), generate_config(), validate_config(),
save_config(), and run() — happy path, validation failure, exception path,
auto_save=False, and Ollama warning variants.

All Ollama/hardware calls are mocked — no external services required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_HW_TARGET = "file_organizer.core.setup_wizard.detect_hardware"
_OLLAMA_TARGET = "file_organizer.core.setup_wizard.detect_ollama"
_MODELS_TARGET = "file_organizer.core.setup_wizard.list_installed_models"
_CFG_MGR_TARGET = "file_organizer.core.setup_wizard.ConfigManager"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hardware(ram_gb: float = 16.0, cpu_cores: int = 8) -> MagicMock:
    """Return a MagicMock HardwareProfile with realistic defaults."""
    from file_organizer.core.hardware_profile import GpuType

    hw = MagicMock()
    hw.gpu_type = GpuType.NONE
    hw.ram_gb = ram_gb
    hw.cpu_cores = cpu_cores
    hw.recommended_text_model.return_value = "qwen2.5:3b-instruct-q4_K_M"
    hw.to_dict.return_value = {
        "gpu_type": "none",
        "vram_gb": 0.0,
        "ram_gb": ram_gb,
        "cpu_cores": cpu_cores,
    }
    return hw


def _make_ollama_status(
    *,
    installed: bool = True,
    running: bool = True,
    version: str | None = "0.5.1",
    models_count: int = 2,
) -> MagicMock:
    """Return a MagicMock OllamaStatus."""
    status = MagicMock()
    status.installed = installed
    status.running = running
    status.version = version
    status.models_count = models_count
    return status


def _make_installed_model(name: str, size: int = 1_000_000) -> MagicMock:
    """Return a MagicMock InstalledModel."""
    m = MagicMock()
    m.name = name
    m.size = size
    m.modified = "2025-01-01T00:00:00Z"
    return m


# ---------------------------------------------------------------------------
# WizardMode
# ---------------------------------------------------------------------------


class TestWizardMode:
    """Tests for the WizardMode enum."""

    def test_quick_start_value(self) -> None:
        from file_organizer.core.setup_wizard import WizardMode

        assert WizardMode.QUICK_START.value == "quick_start"

    def test_power_user_value(self) -> None:
        from file_organizer.core.setup_wizard import WizardMode

        assert WizardMode.POWER_USER.value == "power_user"

    def test_two_modes_total(self) -> None:
        from file_organizer.core.setup_wizard import WizardMode

        assert len(WizardMode) == 2


# ---------------------------------------------------------------------------
# SetupStatus
# ---------------------------------------------------------------------------


class TestSetupStatus:
    """Tests for the SetupStatus enum."""

    def test_all_statuses_exist(self) -> None:
        from file_organizer.core.setup_wizard import SetupStatus

        expected = {
            "NOT_STARTED",
            "DETECTING_HARDWARE",
            "DETECTING_BACKEND",
            "CONFIGURING",
            "VALIDATING",
            "COMPLETED",
            "FAILED",
        }
        actual = {s.name for s in SetupStatus}
        assert actual == expected

    def test_not_started_value(self) -> None:
        from file_organizer.core.setup_wizard import SetupStatus

        assert SetupStatus.NOT_STARTED.value == "not_started"

    def test_completed_value(self) -> None:
        from file_organizer.core.setup_wizard import SetupStatus

        assert SetupStatus.COMPLETED.value == "completed"


# ---------------------------------------------------------------------------
# WizardResult
# ---------------------------------------------------------------------------


class TestWizardResult:
    """Tests for the WizardResult dataclass."""

    def test_default_fields(self) -> None:
        from file_organizer.core.setup_wizard import WizardResult

        result = WizardResult(success=True)
        assert result.success is True
        assert result.config is None
        assert result.profile_name == "default"
        assert result.messages == []
        assert result.warnings == []
        assert result.errors == []

    def test_failure_result(self) -> None:
        from file_organizer.core.setup_wizard import WizardResult

        result = WizardResult(success=False, errors=["something went wrong"])
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0] == "something went wrong"

    def test_lists_are_independent_across_instances(self) -> None:
        from file_organizer.core.setup_wizard import WizardResult

        r1 = WizardResult(success=True)
        r2 = WizardResult(success=True)
        r1.messages.append("msg")
        assert r2.messages == []


# ---------------------------------------------------------------------------
# SystemCapabilities.to_dict()
# ---------------------------------------------------------------------------


class TestSystemCapabilitiesToDict:
    """Tests for SystemCapabilities.to_dict() serialization."""

    def test_keys_present(self) -> None:
        from file_organizer.core.setup_wizard import SystemCapabilities

        hw = _make_hardware()
        ollama = _make_ollama_status()
        model = _make_installed_model("qwen2.5:3b-instruct-q4_K_M")

        caps = SystemCapabilities(
            hardware=hw,
            ollama_status=ollama,
            installed_models=[model],
        )
        result = caps.to_dict()

        assert "hardware" in result
        assert "ollama" in result
        assert "models" in result

    def test_ollama_subkeys(self) -> None:
        from file_organizer.core.setup_wizard import SystemCapabilities

        hw = _make_hardware()
        ollama = _make_ollama_status(installed=True, running=True, version="0.5.1", models_count=1)

        caps = SystemCapabilities(hardware=hw, ollama_status=ollama, installed_models=[])
        ollama_dict = caps.to_dict()["ollama"]

        assert ollama_dict["installed"] is True
        assert ollama_dict["running"] is True
        assert ollama_dict["version"] == "0.5.1"
        assert ollama_dict["models_count"] == 1

    def test_models_list_serialized(self) -> None:
        from file_organizer.core.setup_wizard import SystemCapabilities

        hw = _make_hardware()
        ollama = _make_ollama_status()
        m1 = _make_installed_model("modelA", size=500_000)
        m2 = _make_installed_model("modelB", size=800_000)

        caps = SystemCapabilities(hardware=hw, ollama_status=ollama, installed_models=[m1, m2])
        models_list = caps.to_dict()["models"]

        assert len(models_list) == 2
        assert models_list[0]["name"] == "modelA"
        assert models_list[0]["size"] == 500_000
        assert models_list[1]["name"] == "modelB"

    def test_empty_models_list(self) -> None:
        from file_organizer.core.setup_wizard import SystemCapabilities

        hw = _make_hardware()
        ollama = _make_ollama_status(running=False, models_count=0)

        caps = SystemCapabilities(hardware=hw, ollama_status=ollama, installed_models=[])
        assert caps.to_dict()["models"] == []


# ---------------------------------------------------------------------------
# SetupWizard.detect_capabilities()
# ---------------------------------------------------------------------------


class TestDetectCapabilities:
    """Tests for SetupWizard.detect_capabilities()."""

    def test_returns_system_capabilities(self) -> None:
        from file_organizer.core.setup_wizard import (
            SetupWizard,
            SystemCapabilities,
            WizardMode,
        )

        hw = _make_hardware()
        ollama = _make_ollama_status(running=True)
        model = _make_installed_model("qwen2.5:7b-instruct-q4_K_M")

        with (
            patch(_HW_TARGET, return_value=hw),
            patch(_OLLAMA_TARGET, return_value=ollama),
            patch(_MODELS_TARGET, return_value=[model]),
            patch(_CFG_MGR_TARGET),
        ):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            caps = wizard.detect_capabilities()

        assert isinstance(caps, SystemCapabilities)
        assert caps.hardware is hw
        assert caps.ollama_status is ollama
        assert len(caps.installed_models) == 1
        assert caps.installed_models[0].name == "qwen2.5:7b-instruct-q4_K_M"

    def test_status_set_to_detecting_backend(self) -> None:
        """Status after detect_capabilities() should be DETECTING_BACKEND."""
        from file_organizer.core.setup_wizard import SetupStatus, SetupWizard, WizardMode

        hw = _make_hardware()
        ollama = _make_ollama_status(running=True)

        with (
            patch(_HW_TARGET, return_value=hw),
            patch(_OLLAMA_TARGET, return_value=ollama),
            patch(_MODELS_TARGET, return_value=[]),
            patch(_CFG_MGR_TARGET),
        ):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            wizard.detect_capabilities()

        assert wizard.status == SetupStatus.DETECTING_BACKEND

    def test_models_not_listed_when_ollama_not_running(self) -> None:
        """list_installed_models() must NOT be called when Ollama is not running."""
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        hw = _make_hardware()
        ollama = _make_ollama_status(running=False)
        mock_list = MagicMock()

        with (
            patch(_HW_TARGET, return_value=hw),
            patch(_OLLAMA_TARGET, return_value=ollama),
            patch(_MODELS_TARGET, mock_list),
            patch(_CFG_MGR_TARGET),
        ):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            caps = wizard.detect_capabilities()

        mock_list.assert_not_called()
        assert caps.installed_models == []

    def test_capabilities_stored_on_wizard(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        hw = _make_hardware()
        ollama = _make_ollama_status(running=False)

        with (
            patch(_HW_TARGET, return_value=hw),
            patch(_OLLAMA_TARGET, return_value=ollama),
            patch(_MODELS_TARGET, return_value=[]),
            patch(_CFG_MGR_TARGET),
        ):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            caps = wizard.detect_capabilities()

        assert wizard.capabilities is caps


# ---------------------------------------------------------------------------
# SetupWizard.generate_config()
# ---------------------------------------------------------------------------


class TestGenerateConfig:
    """Tests for SetupWizard.generate_config()."""

    def _make_caps(
        self,
        *,
        running: bool = True,
        model_names: list[str] | None = None,
    ):
        from file_organizer.core.setup_wizard import SystemCapabilities

        hw = _make_hardware()
        ollama = _make_ollama_status(running=running)
        models = [_make_installed_model(n) for n in (model_names or [])]
        return SystemCapabilities(hardware=hw, ollama_status=ollama, installed_models=models)

    def test_returns_app_config(self) -> None:
        from file_organizer.config.schema import AppConfig
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
        caps = self._make_caps(running=False)
        config = wizard.generate_config(caps)

        assert isinstance(config, AppConfig)

    def test_prefers_recommended_large_model(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(
            running=True,
            model_names=["qwen2.5:7b-instruct-q4_K_M", "qwen2.5:3b-instruct-q4_K_M"],
        )
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
        config = wizard.generate_config(caps)

        assert config.models.text_model == "qwen2.5:7b-instruct-q4_K_M"

    def test_falls_back_to_recommended_small(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(
            running=True,
            model_names=["qwen2.5:3b-instruct-q4_K_M", "some-other-model:8b"],
        )
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
        config = wizard.generate_config(caps)

        assert config.models.text_model == "qwen2.5:3b-instruct-q4_K_M"

    def test_falls_back_to_first_available_model(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(running=True, model_names=["custom-model:latest"])
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
        config = wizard.generate_config(caps)

        assert config.models.text_model == "custom-model:latest"

    def test_power_user_custom_text_model_override(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(running=True, model_names=["qwen2.5:3b-instruct-q4_K_M"])
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.POWER_USER)
        config = wizard.generate_config(caps, custom_settings={"text_model": "llama3:8b"})

        assert config.models.text_model == "llama3:8b"

    def test_power_user_temperature_override(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(running=False)
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.POWER_USER)
        config = wizard.generate_config(caps, custom_settings={"temperature": 0.9})

        assert config.models.temperature == pytest.approx(0.9)

    def test_power_user_max_tokens_override(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(running=False)
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.POWER_USER)
        config = wizard.generate_config(caps, custom_settings={"max_tokens": 8000})

        assert config.models.max_tokens == 8000

    def test_quick_start_ignores_custom_model_override(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(running=True, model_names=["qwen2.5:7b-instruct-q4_K_M"])
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
        config = wizard.generate_config(caps, custom_settings={"text_model": "my-custom-model"})

        # QUICK_START mode does NOT apply custom_settings overrides;
        # it picks the first matching recommended model from available list
        assert config.models.text_model != "my-custom-model"
        assert config.models.text_model == "qwen2.5:7b-instruct-q4_K_M"

    def test_no_capabilities_triggers_detect(self) -> None:
        """When capabilities=None and self.capabilities is None, detect_capabilities is called."""
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        hw = _make_hardware()
        ollama = _make_ollama_status(running=False)

        hw_mock = MagicMock(return_value=hw)
        ollama_mock = MagicMock(return_value=ollama)
        with (
            patch(_HW_TARGET, hw_mock),
            patch(_OLLAMA_TARGET, ollama_mock),
            patch(_MODELS_TARGET, return_value=[]),
            patch(_CFG_MGR_TARGET),
        ):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            config = wizard.generate_config()  # no caps passed, no caps stored

        assert config is not None
        assert wizard.capabilities is not None
        # Verify detect_capabilities() ran the hardware and Ollama discovery paths
        hw_mock.assert_called()
        ollama_mock.assert_called()

    def test_uses_stored_capabilities_if_present(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(running=False)
        hw_mock = MagicMock()  # will raise if called
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
        wizard.capabilities = caps

        with patch(_HW_TARGET, hw_mock):
            config = wizard.generate_config()  # should use stored caps

        hw_mock.assert_not_called()
        assert config is not None

    def test_profile_name_from_custom_settings(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(running=False)
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
        config = wizard.generate_config(caps, custom_settings={"profile_name": "my-profile"})

        assert config.profile_name == "my-profile"

    def test_default_profile_name(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        caps = self._make_caps(running=False)
        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
        config = wizard.generate_config(caps)

        assert config.profile_name == "default"


# ---------------------------------------------------------------------------
# SetupWizard.validate_config()
# ---------------------------------------------------------------------------


class TestValidateConfig:
    """Tests for SetupWizard.validate_config()."""

    def _make_wizard_with_caps(self, *, running: bool, model_names: list[str] | None = None):
        from file_organizer.core.setup_wizard import SetupWizard, SystemCapabilities, WizardMode

        hw = _make_hardware()
        ollama = _make_ollama_status(running=running)
        models = [_make_installed_model(n) for n in (model_names or [])]
        caps = SystemCapabilities(hardware=hw, ollama_status=ollama, installed_models=models)

        with patch(_CFG_MGR_TARGET):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
        wizard.capabilities = caps
        return wizard

    def test_passes_with_valid_config(self) -> None:
        from file_organizer.config.schema import AppConfig, ModelPreset

        wizard = self._make_wizard_with_caps(
            running=True, model_names=["qwen2.5:3b-instruct-q4_K_M"]
        )
        config = AppConfig(
            models=ModelPreset(
                text_model="qwen2.5:3b-instruct-q4_K_M",
                temperature=0.5,
                max_tokens=3000,
                framework="ollama",
            )
        )
        is_valid, errors = wizard.validate_config(config)

        assert is_valid is True
        assert errors == []

    def test_ollama_not_running_returns_error(self) -> None:
        from file_organizer.config.schema import AppConfig, ModelPreset

        wizard = self._make_wizard_with_caps(running=False)
        config = AppConfig(
            models=ModelPreset(
                text_model="qwen2.5:3b-instruct-q4_K_M",
                temperature=0.5,
                max_tokens=3000,
                framework="ollama",
            )
        )
        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert any("not running" in e for e in errors)

    def test_model_not_installed_returns_error(self) -> None:
        from file_organizer.config.schema import AppConfig, ModelPreset

        wizard = self._make_wizard_with_caps(running=True, model_names=["some-other-model:latest"])
        config = AppConfig(
            models=ModelPreset(
                text_model="missing-model:7b",
                temperature=0.5,
                max_tokens=3000,
                framework="ollama",
            )
        )
        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert any("missing-model:7b" in e for e in errors)

    def test_temperature_out_of_range_high(self) -> None:
        from file_organizer.config.schema import AppConfig, ModelPreset

        wizard = self._make_wizard_with_caps(running=False)
        config = AppConfig(
            models=ModelPreset(
                text_model="any-model",
                temperature=1.5,  # > 1.0
                max_tokens=3000,
                framework="ollama",
            )
        )
        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert any("Temperature" in e for e in errors)

    def test_temperature_out_of_range_low(self) -> None:
        from file_organizer.config.schema import AppConfig, ModelPreset

        wizard = self._make_wizard_with_caps(running=False)
        config = AppConfig(
            models=ModelPreset(
                text_model="any-model",
                temperature=-0.1,  # < 0.0
                max_tokens=3000,
                framework="ollama",
            )
        )
        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert any("Temperature" in e for e in errors)

    def test_max_tokens_zero_returns_error(self) -> None:
        from file_organizer.config.schema import AppConfig, ModelPreset

        wizard = self._make_wizard_with_caps(running=False)
        config = AppConfig(
            models=ModelPreset(
                text_model="any-model",
                temperature=0.5,
                max_tokens=0,  # < 1
                framework="ollama",
            )
        )
        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert any("max_tokens" in e for e in errors)

    def test_max_tokens_negative_returns_error(self) -> None:
        from file_organizer.config.schema import AppConfig, ModelPreset

        wizard = self._make_wizard_with_caps(running=False)
        config = AppConfig(
            models=ModelPreset(
                text_model="any-model",
                temperature=0.5,
                max_tokens=-1,
                framework="ollama",
            )
        )
        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert any("max_tokens" in e for e in errors)

    def test_multiple_errors_accumulated(self) -> None:
        """Both temperature and max_tokens errors should be reported together."""
        from file_organizer.config.schema import AppConfig, ModelPreset

        wizard = self._make_wizard_with_caps(running=False)
        config = AppConfig(
            models=ModelPreset(
                text_model="any-model",
                temperature=2.0,
                max_tokens=-5,
                framework="ollama",
            )
        )
        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert len(errors) >= 2
        # Both temperature and max_tokens violations must be reported
        errors_lower = [e.lower() for e in errors]
        assert any("temperature" in e for e in errors_lower)
        assert any("max_token" in e or "token" in e for e in errors_lower)

    def test_non_ollama_framework_skips_ollama_check(self) -> None:
        """If framework != 'ollama', Ollama-running check should be skipped."""
        from file_organizer.config.schema import AppConfig, ModelPreset

        wizard = self._make_wizard_with_caps(running=False)
        config = AppConfig(
            models=ModelPreset(
                text_model="any-model",
                temperature=0.5,
                max_tokens=1000,
                framework="llama_cpp",
            )
        )
        is_valid, errors = wizard.validate_config(config)

        # Only temperature/max_tokens checks apply; no Ollama error
        assert is_valid is True
        assert errors == []

    def test_status_set_to_validating(self) -> None:
        from file_organizer.config.schema import AppConfig
        from file_organizer.core.setup_wizard import SetupStatus

        wizard = self._make_wizard_with_caps(running=False)
        config = AppConfig()
        wizard.validate_config(config)

        assert wizard.status == SetupStatus.VALIDATING


# ---------------------------------------------------------------------------
# SetupWizard.save_config()
# ---------------------------------------------------------------------------


class TestSaveConfig:
    """Tests for SetupWizard.save_config()."""

    def test_calls_config_manager_save(self) -> None:
        from file_organizer.config.schema import AppConfig
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        mock_mgr = MagicMock()
        with patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)

        config = AppConfig(profile_name="default")
        wizard.save_config(config)

        mock_mgr.save.assert_called_once_with(config, "default")

    def test_sets_setup_completed_true(self) -> None:
        from file_organizer.config.schema import AppConfig
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        mock_mgr = MagicMock()
        with patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)

        config = AppConfig(profile_name="default", setup_completed=False)
        # Capture setup_completed at the moment save() is invoked — it must be True
        # already at that point, not set afterward.
        state_at_save: list[bool] = []
        mock_mgr.save.side_effect = lambda cfg, _profile: state_at_save.append(cfg.setup_completed)
        wizard.save_config(config)

        assert config.setup_completed is True
        assert state_at_save == [True], "setup_completed must be True before save() is called"

    def test_profile_name_override(self) -> None:
        from file_organizer.config.schema import AppConfig
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        mock_mgr = MagicMock()
        with patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)

        config = AppConfig(profile_name="default")
        wizard.save_config(config, profile="my-custom-profile")

        mock_mgr.save.assert_called_once_with(config, "my-custom-profile")


# ---------------------------------------------------------------------------
# SetupWizard.run() — full flow
# ---------------------------------------------------------------------------


class TestWizardRun:
    """Tests for SetupWizard.run() complete flow."""

    def _patch_for_run(
        self,
        *,
        running: bool = True,
        version: str | None = "0.5.1",
        installed: bool = True,
        model_names: list[str] | None = None,
    ):
        """Context managers for a full wizard run."""
        hw = _make_hardware()
        ollama = _make_ollama_status(
            installed=installed,
            running=running,
            version=version,
            models_count=len(model_names or []),
        )
        models = [_make_installed_model(n) for n in (model_names or [])]
        return (
            patch(_HW_TARGET, return_value=hw),
            patch(_OLLAMA_TARGET, return_value=ollama),
            patch(_MODELS_TARGET, return_value=models),
        )

    def test_happy_path_returns_success(self) -> None:
        from file_organizer.core.setup_wizard import SetupStatus, SetupWizard, WizardMode

        hw_p, ollama_p, models_p = self._patch_for_run(
            running=True, model_names=["qwen2.5:3b-instruct-q4_K_M"]
        )
        mock_mgr = MagicMock()

        with hw_p, ollama_p, models_p, patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            result = wizard.run()

        assert result.success is True
        assert result.config is not None
        assert result.profile_name == "default"
        assert wizard.status == SetupStatus.COMPLETED

    def test_happy_path_config_saved(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        hw_p, ollama_p, models_p = self._patch_for_run(
            running=True, model_names=["qwen2.5:3b-instruct-q4_K_M"]
        )
        mock_mgr = MagicMock()

        with hw_p, ollama_p, models_p, patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            wizard.run(auto_save=True)

        mock_mgr.save.assert_called_once()

    def test_auto_save_false_skips_save(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        hw_p, ollama_p, models_p = self._patch_for_run(
            running=True, model_names=["qwen2.5:3b-instruct-q4_K_M"]
        )
        mock_mgr = MagicMock()

        with hw_p, ollama_p, models_p, patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            result = wizard.run(auto_save=False)

        assert result.success is True
        mock_mgr.save.assert_not_called()

    def test_validation_failure_returns_failure_result(self) -> None:
        from file_organizer.core.setup_wizard import SetupStatus, SetupWizard, WizardMode

        hw_p, ollama_p, models_p = self._patch_for_run(
            running=False,  # Ollama not running → validation fails for ollama framework
        )
        mock_mgr = MagicMock()

        with hw_p, ollama_p, models_p, patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            result = wizard.run()

        assert result.success is False
        assert len(result.errors) >= 1
        # Specifically: Ollama-not-running error must be present
        assert any("ollama" in e.lower() and "not running" in e.lower() for e in result.errors)
        assert wizard.status == SetupStatus.FAILED

    def test_exception_in_detect_returns_failure(self) -> None:
        from file_organizer.core.setup_wizard import SetupStatus, SetupWizard, WizardMode

        mock_mgr = MagicMock()

        with (
            patch(_HW_TARGET, side_effect=RuntimeError("GPU detection failed")),
            patch(_OLLAMA_TARGET),
            patch(_MODELS_TARGET, return_value=[]),
            patch(_CFG_MGR_TARGET, return_value=mock_mgr),
        ):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            result = wizard.run()

        assert result.success is False
        assert any("GPU detection failed" in e for e in result.errors)
        assert wizard.status == SetupStatus.FAILED

    def test_ollama_installed_not_running_adds_warning(self) -> None:
        """Ollama installed but not running should produce a warning in result."""
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        hw_p, ollama_p, models_p = self._patch_for_run(
            installed=True,
            running=False,
        )
        mock_mgr = MagicMock()

        with hw_p, ollama_p, models_p, patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            result = wizard.run()

        assert any("not running" in w for w in result.warnings)

    def test_ollama_not_installed_adds_warning(self) -> None:
        """Ollama not installed at all should produce a different warning."""
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        hw_p, ollama_p, models_p = self._patch_for_run(
            installed=False,
            running=False,
        )
        mock_mgr = MagicMock()

        with hw_p, ollama_p, models_p, patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            result = wizard.run()

        # Source emits: "Ollama not detected. Install from: https://ollama.ai"
        assert any("Ollama not detected" in w for w in result.warnings)

    def test_messages_populated_on_success(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        hw_p, ollama_p, models_p = self._patch_for_run(
            running=True, model_names=["qwen2.5:3b-instruct-q4_K_M"]
        )
        mock_mgr = MagicMock()

        with hw_p, ollama_p, models_p, patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.QUICK_START)
            result = wizard.run()

        assert len(result.messages) >= 2

    def test_power_user_custom_settings_applied(self) -> None:
        from file_organizer.core.setup_wizard import SetupWizard, WizardMode

        hw_p, ollama_p, models_p = self._patch_for_run(
            running=True,
            model_names=["llama3:8b", "qwen2.5:3b-instruct-q4_K_M"],
        )
        mock_mgr = MagicMock()

        with hw_p, ollama_p, models_p, patch(_CFG_MGR_TARGET, return_value=mock_mgr):
            wizard = SetupWizard(mode=WizardMode.POWER_USER)
            result = wizard.run(custom_settings={"text_model": "llama3:8b"})

        assert result.success is True
        assert result.config is not None
        assert result.config.models.text_model == "llama3:8b"
