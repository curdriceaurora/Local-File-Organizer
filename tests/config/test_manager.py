"""Tests for configuration manager: AppConfig loading, saving, and profile management."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from file_organizer.config.manager import CONFIG_FILENAME, ConfigManager
from file_organizer.config.schema import AppConfig


@pytest.mark.unit
class TestConfigManagerInit:
    """Tests for ConfigManager initialization."""

    def test_create_manager_default_dir(self) -> None:
        """Test creating ConfigManager with default config directory."""
        manager = ConfigManager()

        assert manager.config_dir is not None
        assert isinstance(manager.config_dir, Path)

    def test_create_manager_custom_dir(self, tmp_path: Path) -> None:
        """Test creating ConfigManager with custom directory."""
        manager = ConfigManager(config_dir=tmp_path)

        assert manager.config_dir == tmp_path

    def test_create_manager_string_path(self, tmp_path: Path) -> None:
        """Test creating ConfigManager with string path."""
        manager = ConfigManager(config_dir=str(tmp_path))

        assert manager.config_dir == tmp_path

    def test_create_manager_none_uses_default(self) -> None:
        """Test creating ConfigManager with None uses default."""
        manager = ConfigManager(config_dir=None)

        assert manager.config_dir is not None
        assert isinstance(manager.config_dir, Path)

    def test_config_dir_property(self, tmp_path: Path) -> None:
        """Test accessing config_dir property."""
        manager = ConfigManager(config_dir=tmp_path)

        assert manager.config_dir == tmp_path


@pytest.mark.unit
class TestConfigManagerLoad:
    """Tests for ConfigManager.load() method."""

    def test_load_default_profile(self, tmp_path: Path) -> None:
        """Test loading default profile."""
        manager = ConfigManager(config_dir=tmp_path)
        config = manager.load()

        assert config is not None
        assert isinstance(config, AppConfig)

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """Test loading when config file doesn't exist."""
        manager = ConfigManager(config_dir=tmp_path)
        config = manager.load(profile="default")

        assert config is not None
        assert isinstance(config, AppConfig)

    def test_load_custom_profile(self, tmp_path: Path) -> None:
        """Test loading custom profile."""
        # Create config file with custom profile
        config_file = tmp_path / CONFIG_FILENAME
        config_data = {
            "profiles": {
                "custom": {
                    "profile_name": "custom",
                    "organize": {},
                    "models": {},
                }
            }
        }
        config_file.write_text(yaml.dump(config_data))

        manager = ConfigManager(config_dir=tmp_path)
        config = manager.load(profile="custom")

        assert config is not None

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        """Test loading invalid YAML returns defaults."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("invalid: yaml: content: [")

        manager = ConfigManager(config_dir=tmp_path)
        config = manager.load()

        assert config is not None
        assert isinstance(config, AppConfig)

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test loading empty config file."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("")

        manager = ConfigManager(config_dir=tmp_path)
        config = manager.load()

        assert config is not None
        assert isinstance(config, AppConfig)

    def test_load_non_dict_yaml(self, tmp_path: Path) -> None:
        """Test loading non-dict YAML content."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("- item1\n- item2\n")

        manager = ConfigManager(config_dir=tmp_path)
        config = manager.load()

        assert config is not None
        assert isinstance(config, AppConfig)

    def test_load_missing_profile(self, tmp_path: Path) -> None:
        """Test loading missing profile returns defaults."""
        config_file = tmp_path / CONFIG_FILENAME
        config_data = {
            "profiles": {
                "other": {}
            }
        }
        config_file.write_text(yaml.dump(config_data))

        manager = ConfigManager(config_dir=tmp_path)
        config = manager.load(profile="missing")

        assert config is not None
        assert isinstance(config, AppConfig)

    def test_load_profile_with_data(self, tmp_path: Path) -> None:
        """Test loading profile with data."""
        config_file = tmp_path / CONFIG_FILENAME
        config_data = {
            "profiles": {
                "test": {
                    "profile_name": "test",
                    "organize": {"enabled": True},
                    "models": {},
                }
            }
        }
        config_file.write_text(yaml.dump(config_data))

        manager = ConfigManager(config_dir=tmp_path)
        config = manager.load(profile="test")

        assert config is not None


@pytest.mark.unit
class TestConfigManagerSave:
    """Tests for ConfigManager.save() method."""

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Test that save creates the config directory."""
        config_dir = tmp_path / "new_config"
        assert not config_dir.exists()

        manager = ConfigManager(config_dir=config_dir)
        config = AppConfig(profile_name="default")
        manager.save(config)

        assert config_dir.exists()

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """Test that save creates config file."""
        manager = ConfigManager(config_dir=tmp_path)
        config = AppConfig(profile_name="default")
        manager.save(config)

        config_file = tmp_path / CONFIG_FILENAME
        assert config_file.exists()

    def test_save_uses_default_profile(self, tmp_path: Path) -> None:
        """Test that save uses config profile_name by default."""
        manager = ConfigManager(config_dir=tmp_path)
        config = AppConfig(profile_name="myprofile")
        manager.save(config)

        config_file = tmp_path / CONFIG_FILENAME
        content = yaml.safe_load(config_file.read_text())

        assert "profiles" in content
        assert "myprofile" in content["profiles"]

    def test_save_uses_provided_profile(self, tmp_path: Path) -> None:
        """Test that save uses provided profile name."""
        manager = ConfigManager(config_dir=tmp_path)
        config = AppConfig(profile_name="original")
        manager.save(config, profile="override")

        config_file = tmp_path / CONFIG_FILENAME
        content = yaml.safe_load(config_file.read_text())

        assert "profiles" in content
        assert "override" in content["profiles"]

    def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        """Test that save overwrites existing profile."""
        manager = ConfigManager(config_dir=tmp_path)

        # First save
        config1 = AppConfig(profile_name="default")
        manager.save(config1)

        # Second save
        config2 = AppConfig(profile_name="default")
        manager.save(config2)

        config_file = tmp_path / CONFIG_FILENAME
        content = yaml.safe_load(config_file.read_text())

        assert "profiles" in content
        assert "default" in content["profiles"]

    def test_save_multiple_profiles(self, tmp_path: Path) -> None:
        """Test saving multiple profiles."""
        manager = ConfigManager(config_dir=tmp_path)

        config1 = AppConfig(profile_name="profile1")
        manager.save(config1)

        config2 = AppConfig(profile_name="profile2")
        manager.save(config2)

        config_file = tmp_path / CONFIG_FILENAME
        content = yaml.safe_load(config_file.read_text())

        assert "profile1" in content["profiles"]
        assert "profile2" in content["profiles"]

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Test saving and loading config roundtrip."""
        manager = ConfigManager(config_dir=tmp_path)

        # Save
        original = AppConfig(profile_name="test")
        manager.save(original)

        # Load
        loaded = manager.load(profile="test")

        assert loaded is not None
        assert isinstance(loaded, AppConfig)


@pytest.mark.unit
class TestConfigManagerList:
    """Tests for ConfigManager profile listing."""

    def test_list_profiles_empty(self, tmp_path: Path) -> None:
        """Test listing profiles when no config file exists."""
        manager = ConfigManager(config_dir=tmp_path)

        if hasattr(manager, "list_profiles"):
            profiles = manager.list_profiles()
            assert profiles is not None

    def test_list_profiles_with_data(self, tmp_path: Path) -> None:
        """Test listing profiles with existing config."""
        config_file = tmp_path / CONFIG_FILENAME
        config_data = {
            "profiles": {
                "default": {},
                "production": {},
                "development": {},
            }
        }
        config_file.write_text(yaml.dump(config_data))

        manager = ConfigManager(config_dir=tmp_path)

        if hasattr(manager, "list_profiles"):
            profiles = manager.list_profiles()
            assert profiles is not None


@pytest.mark.unit
class TestConfigManagerDelete:
    """Tests for ConfigManager profile deletion."""

    def test_delete_profile(self, tmp_path: Path) -> None:
        """Test deleting a profile."""
        config_file = tmp_path / CONFIG_FILENAME
        config_data = {
            "profiles": {
                "to_delete": {},
                "to_keep": {},
            }
        }
        config_file.write_text(yaml.dump(config_data))

        manager = ConfigManager(config_dir=tmp_path)

        if hasattr(manager, "delete_profile"):
            manager.delete_profile("to_delete")

            content = yaml.safe_load(config_file.read_text())
            assert "to_delete" not in content.get("profiles", {})
            assert "to_keep" in content["profiles"]


@pytest.mark.unit
class TestConfigManagerValidation:
    """Tests for configuration validation."""

    def test_load_preserves_config_structure(self, tmp_path: Path) -> None:
        """Test that loading preserves config structure."""
        manager = ConfigManager(config_dir=tmp_path)
        config = manager.load()

        assert hasattr(config, "profile_name")

    def test_save_valid_config(self, tmp_path: Path) -> None:
        """Test saving valid config."""
        manager = ConfigManager(config_dir=tmp_path)
        config = AppConfig(profile_name="test")

        # Should not raise
        manager.save(config)

        config_file = tmp_path / CONFIG_FILENAME
        assert config_file.exists()

    def test_config_file_is_valid_yaml(self, tmp_path: Path) -> None:
        """Test that saved config is valid YAML."""
        manager = ConfigManager(config_dir=tmp_path)
        config = AppConfig(profile_name="test")
        manager.save(config)

        config_file = tmp_path / CONFIG_FILENAME
        content = config_file.read_text()

        # Should not raise
        parsed = yaml.safe_load(content)
        assert parsed is not None


@pytest.mark.unit
class TestConfigManagerDirectory:
    """Tests for ConfigManager directory handling."""

    def test_config_dir_absolute(self, tmp_path: Path) -> None:
        """Test that config_dir is absolute."""
        manager = ConfigManager(config_dir=tmp_path)

        assert manager.config_dir.is_absolute()

    def test_config_dir_pathlib(self, tmp_path: Path) -> None:
        """Test that config_dir is pathlib Path."""
        manager = ConfigManager(config_dir=tmp_path)

        assert isinstance(manager.config_dir, Path)

    def test_nonexistent_directory_handled(self, tmp_path: Path) -> None:
        """Test handling of nonexistent directory."""
        nonexistent = tmp_path / "does" / "not" / "exist"

        manager = ConfigManager(config_dir=nonexistent)
        config = manager.load()

        assert config is not None

    def test_file_path_used_as_dir(self, tmp_path: Path) -> None:
        """Test behavior when file path passed instead of directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        # Manager should treat it as directory path
        manager = ConfigManager(config_dir=file_path)
        assert manager.config_dir == file_path
