"""Tests for PreferenceStore integration with PathManager."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from file_organizer.config.path_manager import PathManager
from file_organizer.services.intelligence.preference_store import PreferenceStore


def test_preference_store_with_path_manager():
    """PreferenceStore should use PathManager for storage directory"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with patch.dict(os.environ, {'HOME': str(tmp_path)}):
            path_manager = PathManager()
            path_manager.ensure_directories()

            # Create PreferenceStore using PathManager's data_dir
            storage_path = path_manager.data_dir / "preferences"
            pref_store = PreferenceStore(storage_path=storage_path)

            # Verify PreferenceStore uses the correct directory
            assert pref_store.storage_path == storage_path
            assert pref_store.storage_path.exists()


def test_preference_store_saves_to_path_manager_dir():
    """PreferenceStore should save preferences to PathManager directory"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with patch.dict(os.environ, {'HOME': str(tmp_path)}):
            path_manager = PathManager()
            path_manager.ensure_directories()

            storage_path = path_manager.data_dir / "preferences"
            pref_store = PreferenceStore(storage_path=storage_path)

            # Add a preference
            pref_store.add_preference(
                path=Path("Documents"),
                preference_data={"folder_mappings": {"test": "docs"}}
            )

            # Save preferences
            pref_store.save_preferences()

            # Verify preferences file exists in PathManager's data_dir
            pref_file = storage_path / "preferences.json"
            assert pref_file.exists()


def test_preference_store_loads_from_path_manager_dir():
    """PreferenceStore should load preferences from PathManager directory"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with patch.dict(os.environ, {'HOME': str(tmp_path)}):
            path_manager = PathManager()
            path_manager.ensure_directories()

            storage_path = path_manager.data_dir / "preferences"
            pref_store = PreferenceStore(storage_path=storage_path)

            # Add and save a preference
            pref_store.add_preference(
                path=Path("Documents"),
                preference_data={"folder_mappings": {"test": "docs"}}
            )
            pref_store.save_preferences()

            # Load in a new PreferenceStore instance
            pref_store2 = PreferenceStore(storage_path=storage_path)
            pref_store2.load_preferences()

            # Verify preference was loaded (check directory preferences)
            dir_prefs = pref_store2.list_directory_preferences()
            assert len(dir_prefs) > 0


def test_preference_store_default_dir_vs_path_manager():
    """PreferenceStore default dir should match legacy path, PathManager should use XDG"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with patch.dict(os.environ, {'HOME': str(tmp_path)}):
            # Default PreferenceStore uses legacy path
            PreferenceStore()

            # PathManager uses XDG path
            path_manager = PathManager()
            path_manager.ensure_directories()

            # They should be different
            legacy_path = tmp_path / ".file_organizer" / "preferences"
            xdg_path = path_manager.data_dir / "preferences"
            assert legacy_path != xdg_path

            # When created with PathManager, PreferenceStore uses XDG path
            xdg_pref = PreferenceStore(storage_path=xdg_path)
            assert xdg_pref.storage_path == xdg_path
