"""Tests for centralized path manager."""

import os
from pathlib import Path
from unittest.mock import patch

from file_organizer.config.path_manager import PathManager, get_canonical_paths


def test_get_canonical_paths_uses_xdg_when_available():
    """Should use XDG base directories when environment variables set"""
    with patch.dict(os.environ, {
        'XDG_CONFIG_HOME': '/tmp/test-xdg-config',
        'XDG_DATA_HOME': '/tmp/test-xdg-data',
        'XDG_STATE_HOME': '/tmp/test-xdg-state',
    }):
        paths = get_canonical_paths()

        assert paths['config'] == Path('/tmp/test-xdg-config/file-organizer')
        assert paths['data'] == Path('/tmp/test-xdg-data/file-organizer')
        assert paths['state'] == Path('/tmp/test-xdg-state/file-organizer')
        assert paths['cache'] == Path('/tmp/test-xdg-data/file-organizer/cache')


def test_get_canonical_paths_uses_home_defaults():
    """Should use ~/.config, ~/.local/share, ~/.local/state when XDG not set"""
    with patch.dict(os.environ, {
        'XDG_CONFIG_HOME': '',
        'XDG_DATA_HOME': '',
        'XDG_STATE_HOME': '',
        'HOME': '/home/testuser',
    }, clear=False):
        paths = get_canonical_paths()

        assert paths['config'] == Path('/home/testuser/.config/file-organizer')
        assert paths['data'] == Path('/home/testuser/.local/share/file-organizer')
        assert paths['state'] == Path('/home/testuser/.local/state/file-organizer')


def test_path_manager_creates_directories():
    """PathManager should create all necessary directories"""
    with patch.dict(os.environ, {'HOME': '/tmp/test-home'}):
        manager = PathManager()
        # Mock mkdir to verify calls
        with patch.object(Path, 'mkdir') as mock_mkdir:
            manager.ensure_directories()
            # Should create at least config, data, state dirs
            assert mock_mkdir.call_count >= 3


def test_path_manager_provides_specific_paths():
    """PathManager should provide specific file paths"""
    with patch.dict(os.environ, {'HOME': '/home/user'}):
        manager = PathManager()

        assert str(manager.config_file).endswith('config.json')
        assert str(manager.preferences_file).endswith('preferences.json')
        assert str(manager.history_db).endswith('operations.db')
        assert str(manager.undo_redo_db).endswith('undo-redo.db')
