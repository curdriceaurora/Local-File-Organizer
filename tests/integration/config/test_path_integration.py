"""Integration tests for path standardization across modules."""

from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.config.path_manager import PathManager


def test_path_manager_initialization():
    """PathManager should initialize with canonical paths"""
    path_manager = PathManager()

    # Config dir may not exist until ensure_directories() is called
    assert isinstance(path_manager.config_dir, Path)
    assert path_manager.config_file.name == 'config.json'


def test_path_manager_directory_creation(tmp_path):
    """PathManager should create all required directories"""
    with patch.dict('os.environ', {
        'HOME': str(tmp_path),
        'XDG_CONFIG_HOME': str(tmp_path / '.config'),
        'XDG_DATA_HOME': str(tmp_path / '.local' / 'share'),
        'XDG_STATE_HOME': str(tmp_path / '.local' / 'state'),
    }):
        path_manager = PathManager()
        path_manager.ensure_directories()

        # Verify canonical directories created
        assert (path_manager.config_dir).exists()
        assert (path_manager.data_dir).exists()
        assert (path_manager.state_dir).exists()

        # Verify subdirectories
        assert (path_manager.cache_dir).exists()
        assert (path_manager.metadata_dir).exists()


def test_all_paths_follow_xdg_structure(tmp_path):
    """All paths should follow XDG Base Directory structure"""
    # Explicitly set XDG vars to ensure paths resolve under tmp_path,
    # since Path.home() may not respect patched HOME in all environments.
    xdg_config = str(tmp_path / '.config')
    xdg_data = str(tmp_path / '.local' / 'share')
    xdg_state = str(tmp_path / '.local' / 'state')

    with patch.dict('os.environ', {
        'HOME': str(tmp_path),
        'XDG_CONFIG_HOME': xdg_config,
        'XDG_DATA_HOME': xdg_data,
        'XDG_STATE_HOME': xdg_state,
    }):
        path_manager = PathManager()
        path_manager.ensure_directories()

        # Verify path locations follow XDG structure
        config_path_str = str(path_manager.config_dir)
        data_path_str = str(path_manager.data_dir)
        state_path_str = str(path_manager.state_dir)

        assert 'file-organizer' in config_path_str
        assert 'file-organizer' in data_path_str
        assert 'file-organizer' in state_path_str

        # All should be under user directory
        assert str(tmp_path) in config_path_str
        assert str(tmp_path) in data_path_str
        assert str(tmp_path) in state_path_str


def test_path_manager_get_path_by_category(tmp_path):
    """PathManager should retrieve paths by category"""
    with patch.dict('os.environ', {'HOME': str(tmp_path)}):
        path_manager = PathManager()

        config = path_manager.get_path('config')
        data = path_manager.get_path('data')
        state = path_manager.get_path('state')
        cache = path_manager.get_path('cache')

        assert config == path_manager.config_dir
        assert data == path_manager.data_dir
        assert state == path_manager.state_dir
        assert cache == path_manager.cache_dir


def test_path_manager_invalid_category(tmp_path):
    """PathManager should raise error for invalid category"""
    with patch.dict('os.environ', {'HOME': str(tmp_path)}):
        path_manager = PathManager()

        with pytest.raises(ValueError, match="Unknown path category"):
            path_manager.get_path('invalid-category')
