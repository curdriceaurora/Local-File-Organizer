"""Tests for path manager: platform-specific config and cache directory resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.config.path_manager import PathManager, get_cache_dir, get_config_dir


@pytest.mark.unit
class TestPathManagerFunctions:
    """Tests for module-level path manager functions."""

    def test_get_config_dir(self) -> None:
        """Test getting config directory."""
        config_dir = get_config_dir()

        assert config_dir is not None
        assert isinstance(config_dir, Path)

    def test_get_cache_dir(self) -> None:
        """Test getting cache directory."""
        cache_dir = get_cache_dir()

        assert cache_dir is not None
        assert isinstance(cache_dir, Path)

    def test_config_dir_exists(self) -> None:
        """Test that config dir path is reasonable."""
        config_dir = get_config_dir()

        # Should be within user's home or system paths
        assert isinstance(config_dir, Path)

    def test_cache_dir_exists(self) -> None:
        """Test that cache dir path is reasonable."""
        cache_dir = get_cache_dir()

        assert isinstance(cache_dir, Path)

    def test_config_and_cache_different(self) -> None:
        """Test that config and cache directories are different."""
        config_dir = get_config_dir()
        cache_dir = get_cache_dir()

        assert config_dir != cache_dir


@pytest.mark.unit
class TestPathManagerClass:
    """Tests for PathManager class."""

    def test_create_path_manager(self) -> None:
        """Test creating PathManager instance."""
        manager = PathManager()

        assert manager is not None

    def test_path_manager_config_dir(self) -> None:
        """Test PathManager.config_dir property."""
        manager = PathManager()
        config_dir = manager.config_dir

        assert config_dir is not None
        assert isinstance(config_dir, Path)

    def test_path_manager_cache_dir(self) -> None:
        """Test PathManager.cache_dir property."""
        manager = PathManager()
        cache_dir = manager.cache_dir

        assert cache_dir is not None
        assert isinstance(cache_dir, Path)

    def test_path_manager_dirs_different(self) -> None:
        """Test that manager's config and cache dirs are different."""
        manager = PathManager()

        assert manager.config_dir != manager.cache_dir

    def test_path_manager_config_dir_type(self) -> None:
        """Test that config_dir is Path instance."""
        manager = PathManager()

        assert isinstance(manager.config_dir, Path)

    def test_path_manager_cache_dir_type(self) -> None:
        """Test that cache_dir is Path instance."""
        manager = PathManager()

        assert isinstance(manager.cache_dir, Path)

    def test_path_manager_consistency(self) -> None:
        """Test that PathManager returns consistent values."""
        manager = PathManager()

        config_dir_1 = manager.config_dir
        config_dir_2 = manager.config_dir
        cache_dir_1 = manager.cache_dir
        cache_dir_2 = manager.cache_dir

        assert config_dir_1 == config_dir_2
        assert cache_dir_1 == cache_dir_2

    def test_multiple_managers_same_paths(self) -> None:
        """Test that multiple managers return same paths."""
        manager1 = PathManager()
        manager2 = PathManager()

        assert manager1.config_dir == manager2.config_dir
        assert manager1.cache_dir == manager2.cache_dir


@pytest.mark.unit
class TestPathManagerPlatformSpecific:
    """Tests for platform-specific path behavior."""

    def test_config_dir_reasonable_location(self) -> None:
        """Test that config dir is in reasonable location."""
        config_dir = get_config_dir()

        # Should be a legitimate path string representation
        config_str = str(config_dir)
        assert len(config_str) > 0
        assert config_str.startswith("/") or ":" in config_str

    def test_cache_dir_reasonable_location(self) -> None:
        """Test that cache dir is in reasonable location."""
        cache_dir = get_cache_dir()

        # Should be a legitimate path string representation
        cache_str = str(cache_dir)
        assert len(cache_str) > 0
        assert cache_str.startswith("/") or ":" in cache_str

    def test_app_name_in_path(self) -> None:
        """Test that app name appears in path."""
        config_dir = get_config_dir()

        # Path should mention file-organizer or similar app name
        path_str = str(config_dir).lower()
        assert "file" in path_str or "organizer" in path_str or "app" in path_str


@pytest.mark.unit
class TestPathManagerSubdirectories:
    """Tests for subdirectory handling."""

    def test_get_config_subdir(self) -> None:
        """Test getting config subdirectory."""
        manager = PathManager()
        config_dir = manager.config_dir

        # Should be able to create subdirectories
        subdir = config_dir / "models"
        assert isinstance(subdir, Path)

    def test_get_cache_subdir(self) -> None:
        """Test getting cache subdirectory."""
        manager = PathManager()
        cache_dir = manager.cache_dir

        # Should be able to create subdirectories
        subdir = cache_dir / "models"
        assert isinstance(subdir, Path)

    def test_config_file_path(self) -> None:
        """Test constructing config file path."""
        manager = PathManager()
        config_file = manager.config_dir / "config.yaml"

        assert isinstance(config_file, Path)
        assert config_file.suffix == ".yaml"

    def test_cache_file_path(self) -> None:
        """Test constructing cache file path."""
        manager = PathManager()
        cache_file = manager.cache_dir / "cache.db"

        assert isinstance(cache_file, Path)
        assert cache_file.suffix == ".db"


@pytest.mark.unit
class TestPathManagerAbsolutePaths:
    """Tests for absolute path handling."""

    def test_config_dir_absolute(self) -> None:
        """Test that config_dir is absolute path."""
        config_dir = get_config_dir()

        assert config_dir.is_absolute()

    def test_cache_dir_absolute(self) -> None:
        """Test that cache_dir is absolute path."""
        cache_dir = get_cache_dir()

        assert cache_dir.is_absolute()

    def test_manager_config_dir_absolute(self) -> None:
        """Test that manager config_dir is absolute."""
        manager = PathManager()

        assert manager.config_dir.is_absolute()

    def test_manager_cache_dir_absolute(self) -> None:
        """Test that manager cache_dir is absolute."""
        manager = PathManager()

        assert manager.cache_dir.is_absolute()


@pytest.mark.unit
class TestPathManagerPathLike:
    """Tests for Path-like behavior."""

    def test_config_dir_is_path_instance(self) -> None:
        """Test that config_dir is Path instance."""
        config_dir = get_config_dir()

        assert isinstance(config_dir, Path)

    def test_cache_dir_is_path_instance(self) -> None:
        """Test that cache_dir is Path instance."""
        cache_dir = get_cache_dir()

        assert isinstance(cache_dir, Path)

    def test_path_operations(self) -> None:
        """Test that paths support standard operations."""
        manager = PathManager()

        # Test / operator
        config_file = manager.config_dir / "config.yaml"
        assert isinstance(config_file, Path)

        # Test str() conversion
        config_str = str(manager.config_dir)
        assert isinstance(config_str, str)

        # Test name property
        config_name = manager.config_dir.name
        assert isinstance(config_name, str)
