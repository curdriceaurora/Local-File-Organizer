"""Tests for cross-platform config path resolution using platformdirs."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from file_organizer.config.path_manager import (
    APP_NAME,
    PathManager,
    get_cache_dir,
    get_canonical_paths,
    get_config_dir,
    get_data_dir,
    get_state_dir,
)


@pytest.mark.unit
class TestGetConfigDir:
    """Tests for get_config_dir()."""

    def test_returns_path(self) -> None:
        """get_config_dir() should return a Path instance."""
        result = get_config_dir()
        assert isinstance(result, Path)

    def test_contains_app_name(self) -> None:
        """Config dir should contain the app name."""
        result = get_config_dir()
        assert APP_NAME in str(result)

    def test_respects_xdg_config_home(self, tmp_path: Path) -> None:
        """XDG_CONFIG_HOME env var should override the default on Linux/macOS."""
        custom_xdg = str(tmp_path / "custom_xdg")
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": custom_xdg}):
            result = get_config_dir()
        assert result == Path(custom_xdg) / APP_NAME

    def test_empty_xdg_config_home_falls_back_to_platformdirs(self) -> None:
        """Empty XDG_CONFIG_HOME should fall back to platformdirs default."""
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}):
            result = get_config_dir()
        # Should be a valid Path containing the app name
        assert isinstance(result, Path)
        assert APP_NAME in str(result)

    @pytest.mark.skipif(sys.platform != "darwin", reason="See #1072 - macOS-specific path validation")
    def test_macos_path_format(self) -> None:
        """On macOS, config dir should be under ~/Library/Application Support."""
        with mock.patch.dict(os.environ, {}, clear=False):
            # Remove XDG overrides to get native macOS path
            env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
            with mock.patch.dict(os.environ, env, clear=True):
                result = get_config_dir()
        home = Path.home()
        assert str(result).startswith(str(home / "Library" / "Application Support"))

    @pytest.mark.skipif(sys.platform != "linux", reason="See #1072 - Linux-specific path validation")
    def test_linux_path_format(self) -> None:
        """On Linux without XDG override, config dir should be under ~/.config."""
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        with mock.patch.dict(os.environ, env, clear=True):
            result = get_config_dir()
        home = Path.home()
        assert str(result).startswith(str(home / ".config"))

    @pytest.mark.skipif(sys.platform != "win32", reason="See #1072 - Windows-specific path validation")
    def test_windows_path_format(self) -> None:
        """On Windows, config dir should be under %APPDATA%."""
        result = get_config_dir()
        app_data = os.environ.get("APPDATA", "")
        assert app_data and str(result).startswith(app_data)


@pytest.mark.unit
class TestGetDataDir:
    """Tests for get_data_dir()."""

    def test_returns_path(self) -> None:
        """get_data_dir() should return a Path instance."""
        assert isinstance(get_data_dir(), Path)

    def test_contains_app_name(self) -> None:
        """Data dir should contain the app name."""
        assert APP_NAME in str(get_data_dir())

    def test_respects_xdg_data_home(self, tmp_path: Path) -> None:
        """XDG_DATA_HOME env var should override the default."""
        custom_xdg = str(tmp_path / "custom_data")
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": custom_xdg}):
            result = get_data_dir()
        assert result == Path(custom_xdg) / APP_NAME


@pytest.mark.unit
class TestGetStateDir:
    """Tests for get_state_dir()."""

    def test_returns_path(self) -> None:
        """get_state_dir() should return a Path instance."""
        assert isinstance(get_state_dir(), Path)

    def test_contains_app_name(self) -> None:
        """State dir should contain the app name."""
        assert APP_NAME in str(get_state_dir())


@pytest.mark.unit
class TestGetCacheDir:
    """Tests for get_cache_dir()."""

    def test_returns_path(self) -> None:
        """get_cache_dir() should return a Path instance."""
        assert isinstance(get_cache_dir(), Path)

    def test_contains_app_name(self) -> None:
        """Cache dir should contain the app name."""
        assert APP_NAME in str(get_cache_dir())


@pytest.mark.unit
class TestGetCanonicalPaths:
    """Tests for get_canonical_paths()."""

    def test_returns_dict_with_expected_keys(self) -> None:
        """Should return dict with all required path keys."""
        paths = get_canonical_paths()
        expected_keys = {"config", "data", "state", "cache", "history", "metadata", "logs"}
        assert expected_keys == set(paths.keys())

    def test_all_values_are_paths(self) -> None:
        """All values in canonical paths dict should be Path instances."""
        paths = get_canonical_paths()
        for key, value in paths.items():
            assert isinstance(value, Path), f"paths['{key}'] is not a Path"

    def test_all_paths_contain_app_name(self) -> None:
        """All paths should contain the app name."""
        paths = get_canonical_paths()
        for key, value in paths.items():
            assert APP_NAME in str(value), f"paths['{key}'] does not contain '{APP_NAME}'"

    def test_history_is_under_data(self) -> None:
        """History path should be under the data directory."""
        paths = get_canonical_paths()
        assert str(paths["history"]).startswith(str(paths["data"]))

    def test_metadata_is_under_data(self) -> None:
        """Metadata path should be under the data directory."""
        paths = get_canonical_paths()
        assert str(paths["metadata"]).startswith(str(paths["data"]))

    def test_logs_is_under_state(self) -> None:
        """Logs path should be under the state directory."""
        paths = get_canonical_paths()
        assert str(paths["logs"]).startswith(str(paths["state"]))


@pytest.mark.unit
class TestPathManager:
    """Tests for PathManager class."""

    def test_config_dir_returns_path(self) -> None:
        """PathManager.config_dir should return a Path."""
        pm = PathManager()
        assert isinstance(pm.config_dir, Path)

    def test_config_dir_contains_app_name(self) -> None:
        """PathManager.config_dir should contain the app name."""
        pm = PathManager()
        assert APP_NAME in str(pm.config_dir)

    def test_config_file_is_under_config_dir(self) -> None:
        """Config file path should be under config_dir."""
        pm = PathManager()
        assert str(pm.config_file).startswith(str(pm.config_dir))

    def test_preferences_file_is_under_config_dir(self) -> None:
        """Preferences file path should be under config_dir."""
        pm = PathManager()
        assert str(pm.preferences_file).startswith(str(pm.config_dir))

    def test_data_dir_returns_path(self) -> None:
        """PathManager.data_dir should return a Path."""
        pm = PathManager()
        assert isinstance(pm.data_dir, Path)

    def test_cache_dir_returns_path(self) -> None:
        """PathManager.cache_dir should return a Path."""
        pm = PathManager()
        assert isinstance(pm.cache_dir, Path)

    def test_ensure_directories_creates_dirs(self, tmp_path: Path) -> None:
        """ensure_directories() should create all required directories."""
        # Patch get_canonical_paths to use tmp_path
        mock_paths = {
            "config": tmp_path / "config",
            "data": tmp_path / "data",
            "state": tmp_path / "state",
            "cache": tmp_path / "cache",
            "history": tmp_path / "data" / "history",
            "metadata": tmp_path / "data" / "metadata",
            "logs": tmp_path / "state" / "logs",
        }
        with mock.patch(
            "file_organizer.config.path_manager.get_canonical_paths",
            return_value=mock_paths,
        ):
            pm = PathManager()
            pm.ensure_directories()

        for key, path in mock_paths.items():
            assert path.exists(), f"Directory for '{key}' was not created: {path}"

    def test_get_path_raises_for_unknown_category(self) -> None:
        """get_path() should raise ValueError for unknown categories."""
        pm = PathManager()
        with pytest.raises(ValueError, match="Unknown path category"):
            pm.get_path("nonexistent_category")

    def test_get_path_returns_correct_path(self) -> None:
        """get_path() should return the same path as direct property access."""
        pm = PathManager()
        assert pm.get_path("config") == pm.config_dir
        assert pm.get_path("data") == pm.data_dir
        assert pm.get_path("cache") == pm.cache_dir
