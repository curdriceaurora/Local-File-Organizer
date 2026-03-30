"""Setup wizard endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_config_manager, get_settings
from file_organizer.config.manager import ConfigManager
from file_organizer.core.hardware_profile import GpuType
from file_organizer.core.setup_wizard import SetupWizard, WizardMode

router = APIRouter(tags=["setup"])


class SetupStatusResponse(BaseModel):
    """Setup completion status."""

    completed: bool
    profile: str = "default"


class HardwareInfo(BaseModel):
    """Hardware information."""

    total_ram_gb: float
    gpu_available: bool
    gpu_vram_gb: float | None = None
    gpu_name: str | None = None
    cpu_cores: int
    recommended_model: str


class OllamaInfo(BaseModel):
    """Ollama installation status."""

    installed: bool
    running: bool
    version: str | None = None
    models_count: int = 0


class ModelInfo(BaseModel):
    """Installed model information."""

    name: str
    size: int | None = None
    modified: str | None = None


class CapabilitiesResponse(BaseModel):
    """System capabilities detection response."""

    hardware: HardwareInfo
    ollama: OllamaInfo
    models: list[ModelInfo] = []


class SetupRequest(BaseModel):
    """Setup wizard execution request."""

    mode: str = "quick_start"
    profile: str = "default"
    custom_settings: dict[str, Any] | None = None


class SetupResponse(BaseModel):
    """Setup wizard execution response."""

    success: bool
    profile: str
    messages: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []


@router.get("/setup/status", response_model=SetupStatusResponse)
def get_setup_status(
    settings: ApiSettings = Depends(get_settings),
    manager: ConfigManager = Depends(get_config_manager),
) -> SetupStatusResponse:
    """Check if the guided setup wizard has been completed."""
    config = manager.load()
    return SetupStatusResponse(
        completed=config.setup_completed,
        profile=config.profile_name,
    )


@router.get("/setup/capabilities", response_model=CapabilitiesResponse)
def detect_capabilities(
    settings: ApiSettings = Depends(get_settings),
) -> CapabilitiesResponse:
    """Detect system hardware and AI backend capabilities."""
    wizard = SetupWizard(mode=WizardMode.QUICK_START)
    capabilities = wizard.detect_capabilities()

    hardware_info = HardwareInfo(
        total_ram_gb=capabilities.hardware.ram_gb,
        gpu_available=(capabilities.hardware.gpu_type != GpuType.NONE),
        gpu_vram_gb=capabilities.hardware.vram_gb,
        gpu_name=capabilities.hardware.gpu_name,
        cpu_cores=capabilities.hardware.cpu_cores,
        recommended_model=capabilities.hardware.recommended_text_model(),
    )

    ollama_info = OllamaInfo(
        installed=capabilities.ollama_status.installed,
        running=capabilities.ollama_status.running,
        version=capabilities.ollama_status.version,
        models_count=capabilities.ollama_status.models_count,
    )

    models = [
        ModelInfo(
            name=model.name,
            size=model.size,
            modified=model.modified,
        )
        for model in capabilities.installed_models
    ]

    return CapabilitiesResponse(
        hardware=hardware_info,
        ollama=ollama_info,
        models=models,
    )


@router.post("/setup/complete", response_model=SetupResponse)
def complete_setup(
    request: SetupRequest,
    settings: ApiSettings = Depends(get_settings),
    manager: ConfigManager = Depends(get_config_manager),
) -> SetupResponse:
    """Execute the setup wizard and save configuration."""
    # Parse wizard mode
    mode = WizardMode.QUICK_START
    if request.mode.lower() == "power_user":
        mode = WizardMode.POWER_USER

    # Run the wizard
    wizard = SetupWizard(mode=mode, config_manager=manager)
    capabilities = wizard.detect_capabilities()
    config = wizard.generate_config(
        capabilities=capabilities,
        custom_settings=request.custom_settings,
    )

    # Validate configuration
    valid, validation_errors = wizard.validate_config(config)
    if not valid:
        return SetupResponse(
            success=False,
            profile=request.profile,
            errors=validation_errors,
        )

    # Mark setup as completed
    config.setup_completed = True
    config.profile_name = request.profile

    # Save configuration
    manager.save(config, request.profile)

    return SetupResponse(
        success=True,
        profile=request.profile,
        messages=[f"Setup completed successfully with model: {config.models.text_model}"],
    )
