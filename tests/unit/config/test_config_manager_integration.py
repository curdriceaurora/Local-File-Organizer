"""Tests for ConfigManager integration with PathManager."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from file_organizer.config.manager import ConfigManager
from file_organizer.config.path_manager import PathManager
from file_organizer.config.schema import AppConfig


def test_config_manager_with_path_manager():
    """ConfigManager should use PathManager for config directory"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create PathManager with temp dir
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            path_manager = PathManager()
            path_manager.ensure_directories()

            # Create ConfigManager using PathManager's config_dir
            config_manager = ConfigManager(config_dir=path_manager.config_dir)

            # Verify ConfigManager uses the correct directory
            assert config_manager.config_dir == path_manager.config_dir
            assert config_manager.config_dir.exists()


def test_config_manager_saves_to_path_manager_dir():
    """ConfigManager should save config to PathManager directory"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            path_manager = PathManager()
            path_manager.ensure_directories()

            config_manager = ConfigManager(config_dir=path_manager.config_dir)

            # Create and save a config
            config = AppConfig(profile_name="test")
            config_manager.save(config, profile="test")

            # Verify config file exists in PathManager's config_dir
            config_file = path_manager.config_dir / "config.yaml"
            assert config_file.exists()


def test_config_manager_loads_from_path_manager_dir():
    """ConfigManager should load config from PathManager directory"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            path_manager = PathManager()
            path_manager.ensure_directories()

            config_manager = ConfigManager(config_dir=path_manager.config_dir)

            # Save a config
            original_config = AppConfig(profile_name="test")
            config_manager.save(original_config, profile="test")

            # Load it back
            loaded_config = config_manager.load(profile="test")

            assert loaded_config.profile_name == "test"
            assert loaded_config == original_config


def test_config_manager_default_dir_vs_path_manager():
    """ConfigManager default dir differs from PathManager when XDG is customized"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Set XDG_CONFIG_HOME to a custom location so PathManager differs
        # from ConfigManager's hardcoded default (~/.config/file-organizer)
        custom_xdg = tmp_path / "custom-xdg-config"
        with patch.dict(
            os.environ,
            {
                "HOME": str(tmp_path),
                "XDG_CONFIG_HOME": str(custom_xdg),
            },
        ):
            # Default ConfigManager uses hardcoded legacy path
            default_cm = ConfigManager()

            # PathManager respects XDG_CONFIG_HOME
            path_manager = PathManager()
            path_manager.ensure_directories()

            # They should be different when XDG_CONFIG_HOME is customized
            assert default_cm.config_dir != path_manager.config_dir

            # When created with PathManager, ConfigManager uses XDG path
            xdg_cm = ConfigManager(config_dir=path_manager.config_dir)
            assert xdg_cm.config_dir == path_manager.config_dir
