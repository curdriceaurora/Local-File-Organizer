"""Tests for persistent TUI parallelism settings."""

from __future__ import annotations

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

    mock_save.assert_called_once_with(
        ParallelRuntimeSettings(max_workers=6, prefetch_depth=2),
        profile="default",
    )


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
