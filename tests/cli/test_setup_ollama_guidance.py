"""Tests for first-run setup Ollama command guidance."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.cli.setup import setup_run
from file_organizer.config.schema import AppConfig
from file_organizer.core.backend_detector import OllamaStatus
from file_organizer.core.hardware_profile import GpuType

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_setup_run_prints_ollama_install_start_and_pull_commands() -> None:
    """Quick-start dry run should print exact commands without pulling models."""
    hardware = MagicMock()
    hardware.gpu_type = GpuType.NONE
    hardware.gpu_name = None
    hardware.vram_gb = None
    hardware.ram_gb = 16
    hardware.cpu_cores = 8
    hardware.os_name = "macOS"
    hardware.recommended_text_model.return_value = "qwen2.5:3b"
    capabilities = SimpleNamespace(
        hardware=hardware,
        ollama_status=OllamaStatus(installed=False, running=False),
        installed_models=[],
    )
    config = AppConfig()
    config.models.text_model = "qwen2.5:3b"
    wizard = MagicMock()
    wizard.detect_capabilities.return_value = capabilities
    wizard.generate_config.return_value = config
    wizard.validate_config.return_value = (True, [])
    console = MagicMock()

    with (
        patch("file_organizer.cli.setup.SetupWizard", return_value=wizard),
        patch("file_organizer.cli.setup.console", console),
    ):
        setup_run(mode="quick-start", profile="default", dry_run=True)

    printed = "\n".join(str(call.args[0]) for call in console.print.call_args_list if call.args)
    assert "https://ollama.com/download" in printed
    assert "ollama serve" in printed
    assert "ollama pull qwen2.5:3b" in printed
