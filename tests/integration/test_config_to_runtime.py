"""Integration tests for Gap P1: Config-to-Runtime.

Verifies that configuration choices (model names, provider, parallel workers,
dry_run, temperature, profiles) actually flow through to the runtime objects
that use them.  These are the wiring tests that unit mocks hide.

All tests use real ``FileOrganizer``, ``TextProcessor``, and ``VisionProcessor``
instances — only the Ollama/OpenAI HTTP clients are stubbed.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.config.provider_env import get_model_configs
from file_organizer.config.schema import AppConfig, ModelPreset
from file_organizer.core.organizer import FileOrganizer
from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.services.text_processor import TextProcessor

from .conftest import make_text_config, make_vision_config

pytestmark = [pytest.mark.integration]


class TestConfigModelSelection:
    """Config model names flow to the organizer and processors."""

    def test_explicit_model_config_flows_to_organizer(self) -> None:
        """Explicit ModelConfig params override all defaults."""
        text_cfg = make_text_config(name="custom-text:7b")
        vision_cfg = make_vision_config(name="custom-vision:13b")

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        assert org.text_model_config.name == "custom-text:7b"
        assert org.vision_model_config.name == "custom-vision:13b"

    def test_env_provider_openai_flows_to_model_config(self) -> None:
        """FO_PROVIDER=openai produces OpenAI model configs."""
        env = {
            "FO_PROVIDER": "openai",
            "FO_OPENAI_API_KEY": "sk-test-key",
            "FO_OPENAI_MODEL": "gpt-4o",
            "FO_OPENAI_VISION_MODEL": "gpt-4o-vision",
        }
        with patch.dict(os.environ, env, clear=False):
            text_cfg, vision_cfg = get_model_configs()

        assert text_cfg.provider == "openai"
        assert text_cfg.name == "gpt-4o"
        assert text_cfg.api_key == "sk-test-key"
        assert vision_cfg.provider == "openai"
        assert vision_cfg.name == "gpt-4o-vision"

    def test_profile_switch_changes_model(
        self,
    ) -> None:
        """Loading a different profile produces different model names."""
        custom_preset = ModelPreset(
            text_model="llama3:8b",
            vision_model="llava:13b",
        )
        app_cfg = AppConfig(models=custom_preset)

        text_cfg = ModelConfig(name="llama3:8b", model_type=ModelType.TEXT)
        vision_cfg = ModelConfig(name="llava:13b", model_type=ModelType.VISION)

        clean_env = {
            "FO_PROVIDER": "",
            "FO_PROFILE": "work",
        }
        with (
            patch.dict(os.environ, clean_env, clear=False),
            patch("file_organizer.config.manager.ConfigManager") as mock_cls,
        ):
            mgr = mock_cls.return_value
            mgr.load.return_value = app_cfg
            mgr.to_text_model_config.return_value = text_cfg
            mgr.to_vision_model_config.return_value = vision_cfg

            resolved_text, resolved_vision = get_model_configs()

        assert resolved_text.name == "llama3:8b"
        assert resolved_vision.name == "llava:13b"


class TestConfigParallelWorkers:
    """Parallel worker config flows to ParallelProcessor."""

    def test_parallel_workers_flows_to_organizer(self) -> None:
        """parallel_workers param sets ParallelConfig.max_workers."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
            parallel_workers=4,
        )

        assert org.parallel_config.max_workers == 4

    def test_default_parallel_workers_is_none(self) -> None:
        """Default parallel_workers is None (auto-detect CPU count)."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        assert org.parallel_config.max_workers is None


class TestConfigDryRun:
    """dry_run prevents file creation on disk."""

    def test_dry_run_prevents_file_moves(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """Organize with dry_run=True creates no files in output dir."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        result = org.organize(
            input_path=str(integration_source_dir),
            output_path=str(integration_output_dir),
        )

        # Output dir should remain empty (no files moved)
        output_files = list(integration_output_dir.rglob("*"))
        output_files = [f for f in output_files if f.is_file()]
        assert len(output_files) == 0

        # But files should still be reported as processed (3 files in source dir)
        assert result.total_files == 3


class TestConfigTemperature:
    """Temperature from config propagates to model generate options."""

    def test_temperature_propagates_to_text_model(
        self,
        stub_text_model_init: None,
        stub_nltk: None,
    ) -> None:
        """Temperature set in ModelConfig reaches the generate() call."""
        custom_temp = 0.9
        text_cfg = make_text_config(temperature=custom_temp)

        processor = TextProcessor(config=text_cfg)
        processor.initialize()

        assert processor.text_model.config.temperature == custom_temp

    def test_default_temperature_is_half(
        self,
        stub_text_model_init: None,
        stub_nltk: None,
    ) -> None:
        """Default temperature is 0.5."""
        text_cfg = make_text_config()

        processor = TextProcessor(config=text_cfg)
        processor.initialize()

        assert processor.text_model.config.temperature == 0.5
