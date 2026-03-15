"""Tests for persistent TUI parallelism settings."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.config.schema import AppConfig
from file_organizer.tui.settings_view import (
    ParallelRuntimeSettings,
    SettingsView,
    load_parallel_runtime_settings,
    save_parallel_runtime_settings,
)

pytestmark = [pytest.mark.unit]


def test_load_parallel_runtime_settings_defaults() -> None:
    """Missing overrides should load safe defaults."""
    mock_manager = MagicMock()
    mock_manager.load.return_value = AppConfig()

    settings = load_parallel_runtime_settings(manager=mock_manager)

    assert settings.max_workers is None
    assert settings.prefetch_depth == 2
    assert settings.sequential is False
    mock_manager.load.assert_called_once_with(profile="default")


def test_load_parallel_runtime_settings_uses_overrides() -> None:
    """Parallel overrides should round-trip from config."""
    mock_manager = MagicMock()
    config = AppConfig()
    config.parallel = {"max_workers": 1, "prefetch_depth": 0}
    mock_manager.load.return_value = config

    settings = load_parallel_runtime_settings(manager=mock_manager)

    assert settings.max_workers == 1
    assert settings.prefetch_depth == 0
    assert settings.sequential is True


def test_load_parallel_runtime_settings_caps_workers_to_cpu_count() -> None:
    """Worker override should be capped to machine CPU count."""
    mock_manager = MagicMock()
    config = AppConfig()
    config.parallel = {"max_workers": 9999, "prefetch_depth": 1}
    mock_manager.load.return_value = config

    with patch("file_organizer.tui.settings_view._MAX_WORKERS_CAP", 4):
        settings = load_parallel_runtime_settings(manager=mock_manager)

    assert settings.max_workers == 4
    assert settings.prefetch_depth == 1


def test_load_parallel_runtime_settings_uses_cpu_count_fallback_when_unavailable() -> None:
    """Module-level worker cap should fall back to 1 when ``os.cpu_count()`` is unavailable."""
    code = """
from unittest.mock import MagicMock, patch
import importlib

from file_organizer.config.schema import AppConfig
import file_organizer.tui.settings_view as settings_view_module

mock_manager = MagicMock()
config = AppConfig()
config.parallel = {"max_workers": 9999, "prefetch_depth": 3}
mock_manager.load.return_value = config

with patch("os.cpu_count", return_value=None):
    importlib.reload(settings_view_module)
    settings = settings_view_module.load_parallel_runtime_settings(manager=mock_manager)

    print(f"{settings.max_workers},{settings.prefetch_depth}")
"""
    src_root = Path(__file__).resolve().parents[2] / "src"
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    merged_pythonpath = (
        f"{src_root}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(src_root)
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env={**os.environ, "PYTHONPATH": merged_pythonpath},
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "1,3"


def test_save_parallel_runtime_settings_persists_values() -> None:
    """Saving should update ``AppConfig.parallel`` and persist via manager."""
    mock_manager = MagicMock()
    config = AppConfig()
    config.parallel = {"max_workers": 8, "prefetch_depth": 4}
    mock_manager.load.return_value = config

    save_parallel_runtime_settings(
        ParallelRuntimeSettings(max_workers=None, prefetch_depth=0),
        manager=mock_manager,
    )

    assert config.parallel == {"prefetch_depth": 0}
    mock_manager.save.assert_called_once_with(config, profile="default")


def test_save_parallel_runtime_settings_omits_default_prefetch_override() -> None:
    """Default prefetch depth should not be persisted as an explicit override."""
    mock_manager = MagicMock()
    config = AppConfig()
    config.parallel = {"max_workers": 3, "prefetch_depth": 4}
    mock_manager.load.return_value = config

    save_parallel_runtime_settings(
        ParallelRuntimeSettings(max_workers=None, prefetch_depth=2),
        manager=mock_manager,
    )

    assert config.parallel is None
    mock_manager.save.assert_called_once_with(config, profile="default")


def test_settings_view_toggle_sequential_round_trip() -> None:
    """Sequential toggle should set and restore worker/prefetch values."""
    view = SettingsView()
    view._max_workers = 4
    view._prefetch_depth = 3
    view._record_non_sequential_snapshot()

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_toggle_sequential()
        assert view._max_workers == 1
        assert view._prefetch_depth == 0
        assert view._is_sequential is True

        view.action_toggle_sequential()
        assert view._max_workers == 4
        assert view._prefetch_depth == 3
        assert view._is_sequential is False


def test_settings_view_save_action_persists_current_values() -> None:
    """Save action should persist current in-memory values."""
    view = SettingsView()
    view._max_workers = 6
    view._prefetch_depth = 2

    with (
        patch("file_organizer.tui.settings_view.save_parallel_runtime_settings") as mock_save,
        patch.object(view, "_refresh_panel"),
        patch.object(view, "_set_status"),
    ):
        view.action_save_settings()

    mock_save.assert_called_once()
    persisted = mock_save.call_args.args[0]
    assert persisted.max_workers == 6
    assert persisted.prefetch_depth == 2
    assert mock_save.call_args.kwargs == {"profile": "default"}


def test_settings_view_save_action_handles_persistence_failure() -> None:
    """Save action should surface save failures without raising."""
    view = SettingsView()
    view._max_workers = 2
    view._prefetch_depth = 1

    with (
        patch(
            "file_organizer.tui.settings_view.save_parallel_runtime_settings",
            side_effect=RuntimeError("config is read-only"),
        ),
        patch.object(view, "_refresh_panel"),
        patch.object(view, "_set_status") as mock_set_status,
    ):
        view.action_save_settings()

    mock_set_status.assert_called_once_with("Failed to save settings: config is read-only")


def test_settings_view_reload_action_handles_load_failure() -> None:
    """Reload action should surface load failures without raising."""
    view = SettingsView()

    with (
        patch(
            "file_organizer.tui.settings_view.load_parallel_runtime_settings",
            side_effect=RuntimeError("config is unreadable"),
        ),
        patch.object(view, "_refresh_panel"),
        patch.object(view, "_set_status") as mock_set_status,
    ):
        view.action_reload_settings()

    mock_set_status.assert_called_once_with("Failed to load settings: config is unreadable")


def test_settings_view_workers_up_respects_cpu_cap() -> None:
    """Workers-up action should stop at the machine cap."""
    view = SettingsView()
    view._max_workers = 4
    view._prefetch_depth = 2

    with (
        patch("file_organizer.tui.settings_view._MAX_WORKERS_CAP", 4),
        patch.object(view, "_refresh_panel"),
        patch.object(view, "_set_status") as mock_set_status,
    ):
        view.action_workers_up()

    assert view._max_workers == 4
    mock_set_status.assert_called_once_with("Max workers capped at 4 for this machine.")
