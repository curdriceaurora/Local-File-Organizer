"""Setup wizard for first-run configuration and onboarding.

Provides guided setup with hardware detection, backend validation, and
mode selection (Quick Start vs Power User). Integrates with hardware
profiling and backend detection to recommend optimal configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

from file_organizer.config.manager import ConfigManager
from file_organizer.config.schema import AppConfig, ModelPreset
from file_organizer.core.backend_detector import (
    InstalledModel,
    OllamaStatus,
    detect_ollama,
    list_installed_models,
)
from file_organizer.core.hardware_profile import HardwareProfile, detect_hardware


class WizardMode(Enum):
    """Setup wizard execution mode."""

    QUICK_START = "quick_start"
    POWER_USER = "power_user"


class SetupStatus(Enum):
    """Current status of the setup wizard."""

    NOT_STARTED = "not_started"
    DETECTING_HARDWARE = "detecting_hardware"
    DETECTING_BACKEND = "detecting_backend"
    CONFIGURING = "configuring"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WizardResult:
    """Result of wizard execution.

    Attributes:
        success: Whether setup completed successfully.
        config: Generated AppConfig instance.
        profile_name: Name of the saved configuration profile.
        messages: List of informational messages from the wizard.
        warnings: List of warnings encountered during setup.
        errors: List of errors encountered (empty if success=True).
    """

    success: bool
    config: AppConfig | None = None
    profile_name: str = "default"
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class SystemCapabilities:
    """Detected system capabilities snapshot.

    Attributes:
        hardware: Hardware profile with GPU, RAM, CPU info.
        ollama_status: Ollama installation and runtime status.
        installed_models: List of available Ollama models.
    """

    hardware: HardwareProfile
    ollama_status: OllamaStatus
    installed_models: list[InstalledModel] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize capabilities to a plain dictionary."""
        return {
            "hardware": self.hardware.to_dict(),
            "ollama": {
                "installed": self.ollama_status.installed,
                "running": self.ollama_status.running,
                "version": self.ollama_status.version,
                "models_count": self.ollama_status.models_count,
            },
            "models": [
                {"name": m.name, "size": m.size, "modified": m.modified}
                for m in self.installed_models
            ],
        }


class SetupWizard:
    """Interactive setup wizard for first-run configuration.

    Detects system capabilities, validates AI backend availability,
    and generates optimal configuration based on hardware profile
    and user preferences.

    Args:
        mode: Wizard execution mode (QUICK_START or POWER_USER).
        config_manager: Optional ConfigManager instance.
            Creates a new one if not provided.

    Example:
        >>> wizard = SetupWizard(mode=WizardMode.QUICK_START)
        >>> result = wizard.run()
        >>> if result.success:
        ...     print(f"Setup complete: {result.profile_name}")
    """

    def __init__(
        self,
        mode: WizardMode,
        config_manager: ConfigManager | None = None,
    ) -> None:
        """Initialize the setup wizard."""
        self.mode = mode
        self.config_manager = config_manager or ConfigManager()
        self.status = SetupStatus.NOT_STARTED
        self.capabilities: SystemCapabilities | None = None

        logger.info("Initialized setup wizard in {} mode", mode.value)

    def detect_capabilities(self) -> SystemCapabilities:
        """Detect system hardware and AI backend capabilities.

        Returns:
            SystemCapabilities snapshot with hardware, Ollama status,
            and available models.
        """
        self.status = SetupStatus.DETECTING_HARDWARE
        logger.info("Detecting hardware capabilities...")

        hardware = detect_hardware()

        self.status = SetupStatus.DETECTING_BACKEND
        logger.info("Detecting AI backend capabilities...")

        ollama_status = detect_ollama()
        installed_models: list[InstalledModel] = []

        if ollama_status.running:
            installed_models = list_installed_models()
            logger.info("Found {} installed Ollama models", len(installed_models))

        self.capabilities = SystemCapabilities(
            hardware=hardware,
            ollama_status=ollama_status,
            installed_models=installed_models,
        )

        return self.capabilities

    def generate_config(
        self,
        capabilities: SystemCapabilities | None = None,
        custom_settings: dict[str, Any] | None = None,
    ) -> AppConfig:
        """Generate configuration based on detected capabilities.

        Args:
            capabilities: System capabilities snapshot.
                Uses ``self.capabilities`` if not provided.
            custom_settings: Optional user-provided configuration overrides.

        Returns:
            AppConfig instance with recommended settings.
        """
        if capabilities is None:
            if self.capabilities is None:
                logger.warning("No capabilities detected, using defaults")
                capabilities = self.detect_capabilities()
            else:
                capabilities = self.capabilities

        self.status = SetupStatus.CONFIGURING
        logger.info("Generating configuration from capabilities...")

        # Start with hardware-based recommendations
        hardware = capabilities.hardware
        text_model = hardware.recommended_text_model()

        # Override with available models if Ollama is running
        if capabilities.ollama_status.running and capabilities.installed_models:
            # Prefer the first installed model that matches our recommendations
            available_names = {m.name for m in capabilities.installed_models}

            # Check for recommended models
            recommended_large = "qwen2.5:7b-instruct-q4_K_M"
            recommended_small = "qwen2.5:3b-instruct-q4_K_M"

            if recommended_large in available_names:
                text_model = recommended_large
            elif recommended_small in available_names:
                text_model = recommended_small
            elif capabilities.installed_models:
                # Fallback to first available model
                text_model = capabilities.installed_models[0].name
                logger.info("Using first available model: {}", text_model)

        # Create model preset with auto-detected framework
        # Framework will be set based on custom_settings or left as default
        models = ModelPreset(
            text_model=text_model,
            temperature=0.5,
            max_tokens=3000,
            device="auto",
            framework=custom_settings.get("framework", "ollama") if custom_settings else "ollama",
        )

        # Apply custom overrides if in POWER_USER mode
        if self.mode == WizardMode.POWER_USER and custom_settings:
            if "text_model" in custom_settings:
                models.text_model = custom_settings["text_model"]
            if "vision_model" in custom_settings:
                models.vision_model = custom_settings["vision_model"]
            if "temperature" in custom_settings:
                models.temperature = custom_settings["temperature"]
            if "max_tokens" in custom_settings:
                models.max_tokens = custom_settings["max_tokens"]
            if "device" in custom_settings:
                models.device = custom_settings["device"]
            if "framework" in custom_settings:
                models.framework = custom_settings["framework"]

        # Create base configuration
        config = AppConfig(
            profile_name=custom_settings.get("profile_name", "default")
            if custom_settings
            else "default",
            version="1.0",
            default_methodology="none",
            models=models,
        )

        logger.info("Generated config with model: {}", models.text_model)
        return config

    def validate_config(self, config: AppConfig) -> tuple[bool, list[str]]:
        """Validate a configuration against system capabilities.

        Args:
            config: AppConfig to validate.

        Returns:
            Tuple of (is_valid, error_messages).
        """
        self.status = SetupStatus.VALIDATING
        errors: list[str] = []

        # Validate Ollama is available if using ollama framework
        if config.models.framework == "ollama":
            if self.capabilities is None:
                self.detect_capabilities()

            if self.capabilities and not self.capabilities.ollama_status.running:
                errors.append("Ollama framework selected but Ollama service is not running")

        # Validate model availability
        if self.capabilities and self.capabilities.ollama_status.running:
            available_models = {m.name for m in self.capabilities.installed_models}
            if config.models.text_model not in available_models:
                errors.append(f"Selected text model '{config.models.text_model}' is not installed")

        # Validate temperature range
        if not 0.0 <= config.models.temperature <= 1.0:
            errors.append(
                f"Temperature must be between 0.0 and 1.0, got {config.models.temperature}"
            )

        # Validate max_tokens
        if config.models.max_tokens < 1:
            errors.append(f"max_tokens must be positive, got {config.models.max_tokens}")

        is_valid = len(errors) == 0
        logger.info("Configuration validation: {}", "passed" if is_valid else "failed")
        return is_valid, errors

    def save_config(self, config: AppConfig, profile: str | None = None) -> None:
        """Save configuration to disk.

        Args:
            config: AppConfig to persist.
            profile: Profile name override. Uses config.profile_name if None.
        """
        profile = profile or config.profile_name
        config.setup_completed = True
        self.config_manager.save(config, profile)
        logger.info("Saved configuration profile: {}", profile)

    def run(
        self,
        custom_settings: dict[str, Any] | None = None,
        auto_save: bool = True,
    ) -> WizardResult:
        """Run the complete setup wizard flow.

        Args:
            custom_settings: Optional configuration overrides (POWER_USER mode).
            auto_save: Automatically save configuration on successful validation.

        Returns:
            WizardResult with success status, config, and messages.
        """
        result = WizardResult(success=False)

        try:
            logger.info("Starting setup wizard run in {} mode", self.mode.value)

            # Step 1: Detect capabilities
            result.messages.append("Detecting system capabilities...")
            capabilities = self.detect_capabilities()

            result.messages.append(
                f"Hardware: {capabilities.hardware.gpu_type.value}, "
                f"{capabilities.hardware.ram_gb}GB RAM, "
                f"{capabilities.hardware.cpu_cores} cores"
            )

            if capabilities.ollama_status.running:
                result.messages.append(
                    f"Ollama: Running (v{capabilities.ollama_status.version}), "
                    f"{capabilities.ollama_status.models_count} models available"
                )
            elif capabilities.ollama_status.installed:
                result.warnings.append(
                    "Ollama is installed but not running. Start it with: ollama serve"
                )
            else:
                result.warnings.append("Ollama not detected. Install from: https://ollama.ai")

            # Step 2: Generate configuration
            result.messages.append("Generating configuration...")
            config = self.generate_config(capabilities, custom_settings)

            # Step 3: Validate configuration
            result.messages.append("Validating configuration...")
            is_valid, errors = self.validate_config(config)

            if not is_valid:
                result.success = False
                result.errors.extend(errors)
                self.status = SetupStatus.FAILED
                logger.error("Wizard validation failed: {}", errors)
                return result

            # Step 4: Save configuration
            if auto_save:
                result.messages.append("Saving configuration...")
                self.save_config(config)

            result.success = True
            result.config = config
            result.profile_name = config.profile_name
            self.status = SetupStatus.COMPLETED

            logger.info("Setup wizard completed successfully")

        except (RuntimeError, OSError, ValueError, ImportError) as e:
            result.success = False
            result.errors.append(f"Setup wizard error: {e!s}")
            self.status = SetupStatus.FAILED
            logger.exception("Setup wizard failed with exception")

        return result
