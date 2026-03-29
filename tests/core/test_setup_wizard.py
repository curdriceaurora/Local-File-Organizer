"""Unit tests for setup_wizard module."""

from __future__ import annotations

from unittest.mock import Mock, patch

from file_organizer.config.schema import AppConfig
from file_organizer.core.backend_detector import InstalledModel, OllamaStatus
from file_organizer.core.hardware_profile import GpuType, HardwareProfile
from file_organizer.core.setup_wizard import (
    SetupStatus,
    SetupWizard,
    SystemCapabilities,
    WizardMode,
    WizardResult,
)


class TestSetupWizardInitialization:
    """Tests for SetupWizard initialization."""

    def test_init_quick_start_mode(self):
        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        assert wizard.mode == WizardMode.QUICK_START
        assert wizard.status == SetupStatus.NOT_STARTED
        assert wizard.capabilities is None
        assert wizard.config_manager is not None

    def test_init_power_user_mode(self):
        wizard = SetupWizard(mode=WizardMode.POWER_USER)
        assert wizard.mode == WizardMode.POWER_USER
        assert wizard.status == SetupStatus.NOT_STARTED

    def test_init_with_custom_config_manager(self):
        mock_manager = Mock()
        wizard = SetupWizard(mode=WizardMode.QUICK_START, config_manager=mock_manager)
        assert wizard.config_manager is mock_manager


class TestDetectCapabilities:
    """Tests for detect_capabilities() method."""

    @patch("file_organizer.core.setup_wizard.list_installed_models")
    @patch("file_organizer.core.setup_wizard.detect_ollama")
    @patch("file_organizer.core.setup_wizard.detect_hardware")
    def test_detect_capabilities_ollama_running(
        self, mock_detect_hw, mock_detect_ollama, mock_list_models
    ):
        # Setup mocks
        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.gpu_type = GpuType.NVIDIA
        mock_hw.vram_gb = 8.0
        mock_hw.ram_gb = 16.0
        mock_detect_hw.return_value = mock_hw

        mock_ollama = OllamaStatus(installed=True, running=True, version="0.1.29", models_count=2)
        mock_detect_ollama.return_value = mock_ollama

        mock_models = [
            InstalledModel(name="llama2:7b", size=4000000000),
            InstalledModel(name="qwen2.5:3b", size=2000000000),
        ]
        mock_list_models.return_value = mock_models

        # Execute
        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        capabilities = wizard.detect_capabilities()

        # Verify
        assert capabilities.hardware.gpu_type == GpuType.NVIDIA
        assert capabilities.ollama_status.running is True
        assert len(capabilities.installed_models) == 2
        assert wizard.status == SetupStatus.DETECTING_BACKEND

        mock_detect_hw.assert_called_once()
        mock_detect_ollama.assert_called_once()
        mock_list_models.assert_called_once()

    @patch("file_organizer.core.setup_wizard.list_installed_models")
    @patch("file_organizer.core.setup_wizard.detect_ollama")
    @patch("file_organizer.core.setup_wizard.detect_hardware")
    def test_detect_capabilities_ollama_not_running(
        self, mock_detect_hw, mock_detect_ollama, mock_list_models
    ):
        mock_detect_hw.return_value = Mock(spec=HardwareProfile)
        mock_detect_ollama.return_value = OllamaStatus(installed=True, running=False)

        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        capabilities = wizard.detect_capabilities()

        assert capabilities.ollama_status.running is False
        assert len(capabilities.installed_models) == 0
        mock_list_models.assert_not_called()  # Should not list models if not running

    @patch("file_organizer.core.setup_wizard.list_installed_models")
    @patch("file_organizer.core.setup_wizard.detect_ollama")
    @patch("file_organizer.core.setup_wizard.detect_hardware")
    def test_detect_capabilities_ollama_not_installed(
        self, mock_detect_hw, mock_detect_ollama, mock_list_models
    ):
        mock_detect_hw.return_value = Mock(spec=HardwareProfile)
        mock_detect_ollama.return_value = OllamaStatus(installed=False, running=False)

        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        capabilities = wizard.detect_capabilities()

        assert capabilities.ollama_status.installed is False
        assert capabilities.ollama_status.running is False
        assert len(capabilities.installed_models) == 0


class TestGenerateConfig:
    """Tests for generate_config() method."""

    def test_generate_config_quick_start(self):
        # Setup wizard with capabilities
        wizard = SetupWizard(mode=WizardMode.QUICK_START)

        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.recommended_text_model.return_value = "qwen2.5:3b-instruct-q4_K_M"

        wizard.capabilities = SystemCapabilities(
            hardware=mock_hw,
            ollama_status=OllamaStatus(installed=True, running=True, models_count=1),
            installed_models=[InstalledModel(name="qwen2.5:3b-instruct-q4_K_M")],
        )

        # Execute
        config = wizard.generate_config()

        # Verify
        assert isinstance(config, AppConfig)
        assert config.models.text_model == "qwen2.5:3b-instruct-q4_K_M"
        assert config.models.framework == "ollama"
        mock_hw.recommended_text_model.assert_called_once()

    def test_generate_config_power_user_custom_settings(self):
        wizard = SetupWizard(mode=WizardMode.POWER_USER)

        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.recommended_text_model.return_value = "qwen2.5:3b-instruct-q4_K_M"

        wizard.capabilities = SystemCapabilities(
            hardware=mock_hw,
            ollama_status=OllamaStatus(installed=True, running=True),
            installed_models=[InstalledModel(name="llama2:13b")],
        )

        custom_settings = {"text_model": "llama2:13b", "temperature": 0.8, "max_tokens": 4096}

        config = wizard.generate_config(custom_settings=custom_settings)

        assert isinstance(config, AppConfig)
        assert config.models.text_model == "llama2:13b"
        assert config.models.temperature == 0.8
        assert config.models.max_tokens == 4096

    def test_generate_config_uses_first_available_model(self):
        wizard = SetupWizard(mode=WizardMode.QUICK_START)

        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.recommended_text_model.return_value = "qwen2.5:3b-instruct-q4_K_M"

        wizard.capabilities = SystemCapabilities(
            hardware=mock_hw,
            ollama_status=OllamaStatus(installed=True, running=True),
            installed_models=[
                InstalledModel(name="custom-model:latest"),
                InstalledModel(name="another-model:7b"),
            ],
        )

        config = wizard.generate_config()

        # Should use first available model since recommended not found
        assert config.models.text_model == "custom-model:latest"

    @patch("file_organizer.core.setup_wizard.detect_hardware")
    @patch("file_organizer.core.setup_wizard.detect_ollama")
    @patch("file_organizer.core.setup_wizard.list_installed_models")
    def test_generate_config_auto_detect_if_no_capabilities(
        self, mock_list_models, mock_detect_ollama, mock_detect_hw
    ):
        """When capabilities not set, should auto-detect."""
        wizard = SetupWizard(mode=WizardMode.QUICK_START)

        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.recommended_text_model.return_value = "qwen2.5:3b-instruct-q4_K_M"
        mock_detect_hw.return_value = mock_hw

        mock_detect_ollama.return_value = OllamaStatus(installed=True, running=True)
        mock_list_models.return_value = [InstalledModel(name="llama2:7b")]

        config = wizard.generate_config()

        assert isinstance(config, AppConfig)
        mock_detect_hw.assert_called_once()
        mock_detect_ollama.assert_called_once()

    def test_generate_config_prefers_recommended_large_model(self):
        """Should prefer qwen2.5:7b-instruct-q4_K_M if available."""
        wizard = SetupWizard(mode=WizardMode.QUICK_START)

        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.recommended_text_model.return_value = "some-default"

        wizard.capabilities = SystemCapabilities(
            hardware=mock_hw,
            ollama_status=OllamaStatus(installed=True, running=True),
            installed_models=[
                InstalledModel(name="qwen2.5:7b-instruct-q4_K_M"),
                InstalledModel(name="qwen2.5:3b-instruct-q4_K_M"),
            ],
        )

        config = wizard.generate_config()

        assert config.models.text_model == "qwen2.5:7b-instruct-q4_K_M"

    def test_generate_config_prefers_recommended_small_model(self):
        """Should use qwen2.5:3b-instruct-q4_K_M if large not available."""
        wizard = SetupWizard(mode=WizardMode.QUICK_START)

        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.recommended_text_model.return_value = "some-default"

        wizard.capabilities = SystemCapabilities(
            hardware=mock_hw,
            ollama_status=OllamaStatus(installed=True, running=True),
            installed_models=[
                InstalledModel(name="qwen2.5:3b-instruct-q4_K_M"),
                InstalledModel(name="llama2:7b"),
            ],
        )

        config = wizard.generate_config()

        assert config.models.text_model == "qwen2.5:3b-instruct-q4_K_M"


class TestValidateConfig:
    """Tests for validate_config() method."""

    def test_validate_config_success(self):
        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        wizard.capabilities = SystemCapabilities(
            hardware=Mock(spec=HardwareProfile),
            ollama_status=OllamaStatus(installed=True, running=True),
            installed_models=[InstalledModel(name="qwen2.5:3b")],
        )

        config = AppConfig()
        config.models.text_model = "qwen2.5:3b"
        config.models.temperature = 0.5
        config.models.max_tokens = 3000

        is_valid, errors = wizard.validate_config(config)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_config_ollama_not_running(self):
        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        wizard.capabilities = SystemCapabilities(
            hardware=Mock(spec=HardwareProfile),
            ollama_status=OllamaStatus(installed=False, running=False),
            installed_models=[],
        )

        config = AppConfig()
        config.models.framework = "ollama"

        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert len(errors) > 0
        assert any("Ollama" in err for err in errors)

    def test_validate_config_model_not_installed(self):
        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        wizard.capabilities = SystemCapabilities(
            hardware=Mock(spec=HardwareProfile),
            ollama_status=OllamaStatus(installed=True, running=True),
            installed_models=[InstalledModel(name="llama2:7b")],
        )

        config = AppConfig()
        config.models.text_model = "nonexistent-model:latest"

        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert any("not installed" in err for err in errors)

    def test_validate_config_invalid_temperature(self):
        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        wizard.capabilities = SystemCapabilities(
            hardware=Mock(spec=HardwareProfile),
            ollama_status=OllamaStatus(installed=True, running=True),
            installed_models=[InstalledModel(name="qwen2.5:3b")],
        )

        config = AppConfig()
        config.models.text_model = "qwen2.5:3b"
        config.models.temperature = 1.5  # Invalid

        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert any("Temperature" in err for err in errors)

    def test_validate_config_invalid_max_tokens(self):
        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        wizard.capabilities = SystemCapabilities(
            hardware=Mock(spec=HardwareProfile),
            ollama_status=OllamaStatus(installed=True, running=True),
            installed_models=[InstalledModel(name="qwen2.5:3b")],
        )

        config = AppConfig()
        config.models.text_model = "qwen2.5:3b"
        config.models.max_tokens = 0  # Invalid

        is_valid, errors = wizard.validate_config(config)

        assert is_valid is False
        assert any("max_tokens" in err for err in errors)

    @patch("file_organizer.core.setup_wizard.detect_hardware")
    @patch("file_organizer.core.setup_wizard.detect_ollama")
    @patch("file_organizer.core.setup_wizard.list_installed_models")
    def test_validate_config_auto_detects_if_no_capabilities(
        self, mock_list_models, mock_detect_ollama, mock_detect_hw
    ):
        """When capabilities not set, should auto-detect before validating."""
        wizard = SetupWizard(mode=WizardMode.QUICK_START)

        mock_hw = Mock(spec=HardwareProfile)
        mock_detect_hw.return_value = mock_hw
        mock_detect_ollama.return_value = OllamaStatus(installed=True, running=True)
        mock_list_models.return_value = [InstalledModel(name="qwen2.5:3b")]

        config = AppConfig()
        config.models.text_model = "qwen2.5:3b"

        is_valid, errors = wizard.validate_config(config)

        assert wizard.capabilities is not None
        mock_detect_hw.assert_called_once()


class TestSaveConfig:
    """Tests for save_config() method."""

    def test_save_config(self):
        mock_manager = Mock()
        wizard = SetupWizard(mode=WizardMode.QUICK_START, config_manager=mock_manager)

        config = AppConfig(profile_name="test-profile")

        wizard.save_config(config)

        mock_manager.save.assert_called_once()
        saved_config, saved_profile = mock_manager.save.call_args[0]
        assert saved_config.setup_completed is True
        assert saved_profile == "test-profile"

    def test_save_config_with_profile_override(self):
        mock_manager = Mock()
        wizard = SetupWizard(mode=WizardMode.QUICK_START, config_manager=mock_manager)

        config = AppConfig(profile_name="original")

        wizard.save_config(config, profile="override")

        mock_manager.save.assert_called_once()
        saved_config, saved_profile = mock_manager.save.call_args[0]
        assert saved_config.setup_completed is True
        assert saved_profile == "override"


class TestWizardRun:
    """Tests for run() method - full wizard flow."""

    @patch.object(SetupWizard, "save_config")
    @patch.object(SetupWizard, "validate_config")
    @patch.object(SetupWizard, "generate_config")
    @patch.object(SetupWizard, "detect_capabilities")
    def test_run_quick_start_success(self, mock_detect, mock_generate, mock_validate, mock_save):
        # Setup mocks
        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.gpu_type = GpuType.NVIDIA
        mock_hw.ram_gb = 16.0
        mock_hw.cpu_cores = 8

        mock_capabilities = Mock(spec=SystemCapabilities)
        mock_capabilities.hardware = mock_hw
        mock_capabilities.ollama_status = OllamaStatus(
            installed=True, running=True, version="0.1.29", models_count=2
        )
        mock_detect.return_value = mock_capabilities

        mock_config = Mock(spec=AppConfig)
        mock_config.profile_name = "default"
        mock_generate.return_value = mock_config

        mock_validate.return_value = (True, [])
        mock_save.return_value = None

        # Execute
        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        result = wizard.run()

        # Verify
        assert isinstance(result, WizardResult)
        assert result.success is True
        assert wizard.status == SetupStatus.COMPLETED

        mock_detect.assert_called_once()
        mock_generate.assert_called_once()
        mock_validate.assert_called_once()
        mock_save.assert_called_once()

    @patch.object(SetupWizard, "detect_capabilities")
    def test_run_ollama_not_installed(self, mock_detect):
        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.gpu_type = GpuType.NONE
        mock_hw.ram_gb = 8.0
        mock_hw.cpu_cores = 4

        mock_capabilities = SystemCapabilities(
            hardware=mock_hw,
            ollama_status=OllamaStatus(installed=False, running=False),
            installed_models=[],
        )

        def assign_capabilities(wizard):
            wizard.capabilities = mock_capabilities
            return mock_capabilities

        mock_detect.side_effect = lambda: assign_capabilities(wizard)

        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        result = wizard.run()

        # Should complete but with warnings
        assert isinstance(result, WizardResult)
        assert len(result.warnings) > 0
        assert any("Ollama" in w for w in result.warnings)

    @patch.object(SetupWizard, "validate_config")
    @patch.object(SetupWizard, "generate_config")
    @patch.object(SetupWizard, "detect_capabilities")
    def test_run_validation_fails(self, mock_detect, mock_generate, mock_validate):
        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.gpu_type = GpuType.NVIDIA
        mock_hw.ram_gb = 16.0
        mock_hw.cpu_cores = 8

        mock_capabilities = Mock(spec=SystemCapabilities)
        mock_capabilities.hardware = mock_hw
        mock_capabilities.ollama_status = OllamaStatus(installed=True, running=True)
        mock_detect.return_value = mock_capabilities

        mock_config = Mock(spec=AppConfig)
        mock_generate.return_value = mock_config

        # Validation fails
        mock_validate.return_value = (False, ["Model not installed", "Invalid temperature"])

        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        result = wizard.run()

        assert result.success is False
        assert len(result.errors) == 2
        assert wizard.status == SetupStatus.FAILED

    @patch.object(SetupWizard, "detect_capabilities")
    def test_run_handles_exception(self, mock_detect):
        mock_detect.side_effect = Exception("Hardware detection failed")

        wizard = SetupWizard(mode=WizardMode.QUICK_START)
        result = wizard.run()

        assert result.success is False
        assert len(result.errors) > 0
        assert wizard.status == SetupStatus.FAILED

    @patch.object(SetupWizard, "save_config")
    @patch.object(SetupWizard, "validate_config")
    @patch.object(SetupWizard, "generate_config")
    @patch.object(SetupWizard, "detect_capabilities")
    def test_run_with_custom_settings_power_user(
        self, mock_detect, mock_generate, mock_validate, mock_save
    ):
        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.gpu_type = GpuType.NVIDIA
        mock_hw.ram_gb = 32.0
        mock_hw.cpu_cores = 16

        mock_capabilities = Mock(spec=SystemCapabilities)
        mock_capabilities.hardware = mock_hw
        mock_capabilities.ollama_status = OllamaStatus(installed=True, running=True)
        mock_detect.return_value = mock_capabilities

        mock_config = Mock(spec=AppConfig)
        mock_config.profile_name = "custom"
        mock_generate.return_value = mock_config

        mock_validate.return_value = (True, [])

        wizard = SetupWizard(mode=WizardMode.POWER_USER)
        custom_settings = {"text_model": "llama2:13b", "temperature": 0.9}
        result = wizard.run(custom_settings=custom_settings)

        assert result.success is True
        mock_generate.assert_called_once_with(mock_capabilities, custom_settings)

    @patch.object(SetupWizard, "validate_config")
    @patch.object(SetupWizard, "generate_config")
    @patch.object(SetupWizard, "detect_capabilities")
    def test_run_no_auto_save(self, mock_detect, mock_generate, mock_validate):
        """When auto_save=False, config should not be saved."""
        mock_hw = Mock(spec=HardwareProfile)
        mock_hw.gpu_type = GpuType.NVIDIA
        mock_hw.ram_gb = 16.0
        mock_hw.cpu_cores = 8

        mock_capabilities = Mock(spec=SystemCapabilities)
        mock_capabilities.hardware = mock_hw
        mock_capabilities.ollama_status = OllamaStatus(installed=True, running=True)
        mock_detect.return_value = mock_capabilities

        mock_config = Mock(spec=AppConfig)
        mock_config.profile_name = "default"
        mock_generate.return_value = mock_config

        mock_validate.return_value = (True, [])

        mock_manager = Mock()
        wizard = SetupWizard(mode=WizardMode.QUICK_START, config_manager=mock_manager)
        result = wizard.run(auto_save=False)

        assert result.success is True
        mock_manager.save.assert_not_called()


class TestSystemCapabilities:
    """Tests for SystemCapabilities dataclass."""

    def test_to_dict_serialization(self):
        hw = Mock(spec=HardwareProfile)
        hw.to_dict.return_value = {"gpu_type": "NVIDIA", "vram_gb": 8.0}

        ollama = OllamaStatus(installed=True, running=True, version="0.1.29", models_count=2)
        models = [InstalledModel(name="llama2", size=4000000000)]

        caps = SystemCapabilities(hardware=hw, ollama_status=ollama, installed_models=models)
        result = caps.to_dict()

        assert "hardware" in result
        assert "ollama" in result
        assert "models" in result
        assert result["ollama"]["running"] is True
        assert len(result["models"]) == 1

    def test_to_dict_with_empty_models(self):
        hw = Mock(spec=HardwareProfile)
        hw.to_dict.return_value = {"gpu_type": "NONE", "vram_gb": 0.0}

        ollama = OllamaStatus(installed=False, running=False)

        caps = SystemCapabilities(hardware=hw, ollama_status=ollama, installed_models=[])
        result = caps.to_dict()

        assert result["models"] == []


class TestWizardResult:
    """Tests for WizardResult dataclass."""

    def test_success_result(self):
        config = Mock(spec=AppConfig)
        result = WizardResult(
            success=True, config=config, messages=["Setup completed successfully"]
        )

        assert result.success is True
        assert result.config is config
        assert len(result.errors) == 0

    def test_failure_result(self):
        result = WizardResult(success=False, errors=["Ollama not installed", "No models available"])

        assert result.success is False
        assert len(result.errors) == 2
        assert result.config is None

    def test_result_with_warnings(self):
        result = WizardResult(success=True, warnings=["Ollama not running", "Limited VRAM"])

        assert result.success is True
        assert len(result.warnings) == 2