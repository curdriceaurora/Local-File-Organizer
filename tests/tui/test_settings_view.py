"""Tests for persistent TUI parallelism settings."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import Input

from file_organizer.config.schema import AppConfig
from file_organizer.tui.settings_view import (
    ParallelRuntimeSettings,
    SettingsView,
    WorkflowSettings,
    load_parallel_runtime_settings,
    load_workflow_settings,
    save_parallel_runtime_settings,
    save_workflow_settings,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


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
    """Save action should persist current in-memory parallel and workflow values."""
    view = SettingsView()
    view._max_workers = 6
    view._prefetch_depth = 2

    with (
        patch("file_organizer.tui.settings_view.save_parallel_runtime_settings") as mock_save,
        patch("file_organizer.tui.settings_view.save_workflow_settings"),
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
        patch(
            "file_organizer.tui.settings_view.load_workflow_settings",
            return_value=WorkflowSettings(
                default_input_dir="",
                default_output_dir="",
                methodology="none",
                text_model="qwen2.5:3b-instruct-q4_K_M",
                provider="ollama",
                check_updates_on_startup=True,
                include_prereleases=False,
            ),
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


# ---------------------------------------------------------------------------
# Workflow settings (methodology / model / update toggles / directories)
# ---------------------------------------------------------------------------


def test_load_workflow_settings_defaults() -> None:
    """A default config should load safe workflow defaults."""
    mock_manager = MagicMock()
    mock_manager.load.return_value = AppConfig()

    settings = load_workflow_settings(manager=mock_manager)

    assert settings.default_input_dir == ""
    assert settings.default_output_dir == ""
    assert settings.methodology == "none"
    assert settings.text_model == "qwen2.5:3b-instruct-q4_K_M"
    assert settings.check_updates_on_startup is True
    assert settings.include_prereleases is False
    mock_manager.load.assert_called_once_with(profile="default")


def test_load_workflow_settings_uses_overrides() -> None:
    """Workflow overrides should round-trip from config."""
    mock_manager = MagicMock()
    config = AppConfig()
    config.default_input_dir = "/data/in"
    config.default_output_dir = "/data/out"
    config.default_methodology = "para"
    config.models.text_model = "llama3.2:3b-instruct-q4_K_M"
    config.updates.check_on_startup = False
    config.updates.include_prereleases = True
    mock_manager.load.return_value = config

    settings = load_workflow_settings(manager=mock_manager)

    assert settings.default_input_dir == "/data/in"
    assert settings.default_output_dir == "/data/out"
    assert settings.methodology == "para"
    assert settings.text_model == "llama3.2:3b-instruct-q4_K_M"
    assert settings.check_updates_on_startup is False
    assert settings.include_prereleases is True


def test_load_workflow_settings_normalizes_unknown_methodology() -> None:
    """An unrecognized methodology should fall back to ``none``."""
    mock_manager = MagicMock()
    config = AppConfig()
    config.default_methodology = "content_based"  # not a TUI methodology
    mock_manager.load.return_value = config

    settings = load_workflow_settings(manager=mock_manager)

    assert settings.methodology == "none"


def test_save_workflow_settings_persists_values() -> None:
    """Saving should update AppConfig workflow fields and persist via manager."""
    mock_manager = MagicMock()
    config = AppConfig()
    mock_manager.load.return_value = config

    save_workflow_settings(
        WorkflowSettings(
            default_input_dir="  /data/in  ",
            default_output_dir="/data/out",
            methodology="jd",
            text_model="  gemma2:2b-instruct-q4_K_M  ",
            provider="openai",
            check_updates_on_startup=False,
            include_prereleases=True,
        ),
        manager=mock_manager,
    )

    assert config.default_input_dir == "/data/in"  # trimmed
    assert config.default_output_dir == "/data/out"
    assert config.default_methodology == "jd"
    assert config.models.text_model == "gemma2:2b-instruct-q4_K_M"  # trimmed
    assert config.models.framework == "openai"
    assert config.updates.check_on_startup is False
    assert config.updates.include_prereleases is True
    mock_manager.save.assert_called_once_with(config, profile="default")


def test_save_workflow_settings_empty_model_falls_back_to_default() -> None:
    """A blank text model should be replaced with the default preset."""
    mock_manager = MagicMock()
    config = AppConfig()
    mock_manager.load.return_value = config

    save_workflow_settings(
        WorkflowSettings(
            default_input_dir="",
            default_output_dir="",
            methodology="none",
            text_model="   ",
            provider="ollama",
            check_updates_on_startup=True,
            include_prereleases=False,
        ),
        manager=mock_manager,
    )

    assert config.models.text_model == "qwen2.5:3b-instruct-q4_K_M"


def test_save_workflow_settings_unknown_provider_falls_back_to_default() -> None:
    """An out-of-range provider value should be replaced with the ollama default."""
    mock_manager = MagicMock()
    config = AppConfig()
    mock_manager.load.return_value = config

    save_workflow_settings(
        WorkflowSettings(
            default_input_dir="",
            default_output_dir="",
            methodology="none",
            text_model="qwen2.5:3b-instruct-q4_K_M",
            provider="not-a-real-provider",
            check_updates_on_startup=True,
            include_prereleases=False,
        ),
        manager=mock_manager,
    )

    assert config.models.framework == "ollama"


def test_settings_view_cycle_methodology_round_trips() -> None:
    """Cycling methodology should advance none -> para -> jd -> none."""
    view = SettingsView()
    view._methodology = "none"

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_cycle_methodology()
        assert view._methodology == "para"
        view.action_cycle_methodology()
        assert view._methodology == "jd"
        view.action_cycle_methodology()
        assert view._methodology == "none"


def test_settings_view_cycle_text_model_advances_through_presets() -> None:
    """Cycling from a known preset should advance to the next preset."""
    view = SettingsView()
    view._text_model = "qwen2.5:3b-instruct-q4_K_M"

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_cycle_text_model()

    assert view._text_model == "qwen2.5:7b-instruct-q4_K_M"


def test_settings_view_cycle_text_model_preserves_custom_value() -> None:
    """A custom model should be kept in the cycle and reachable again."""
    view = SettingsView()
    view._text_model = "my-custom:latest"

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        # Custom value is prepended; first cycle moves to the first preset.
        view.action_cycle_text_model()
        assert view._text_model == "qwen2.5:3b-instruct-q4_K_M"


def test_settings_view_cycle_provider_round_trips() -> None:
    """Cycling provider should advance through all five supported providers and wrap (#1660)."""
    view = SettingsView()
    view._provider = "ollama"

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_cycle_provider()
        assert view._provider == "openai"
        view.action_cycle_provider()
        assert view._provider == "llama_cpp"
        view.action_cycle_provider()
        assert view._provider == "mlx"
        view.action_cycle_provider()
        assert view._provider == "claude"
        view.action_cycle_provider()
        assert view._provider == "ollama"


def test_settings_view_cycle_provider_syncs_to_workspace() -> None:
    """Cycling provider should immediately update both workspace model providers (#1660)."""
    from file_organizer.tui.workspace import TUIWorkspace

    workspace = TUIWorkspace()
    view = SettingsView(workspace=workspace)
    view._provider = "ollama"

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_cycle_provider()

    assert workspace.options.text_provider == "openai"
    assert workspace.options.vision_provider == "openai"


def test_settings_view_toggle_update_check() -> None:
    """Toggling update-check should flip the flag."""
    view = SettingsView()
    view._check_updates = True

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_toggle_update_check()
        assert view._check_updates is False
        view.action_toggle_update_check()
        assert view._check_updates is True


def test_settings_view_toggle_prereleases() -> None:
    """Toggling pre-releases should flip the flag."""
    view = SettingsView()
    view._include_prereleases = False

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_toggle_prereleases()
        assert view._include_prereleases is True


def test_settings_view_input_changed_updates_directory_state() -> None:
    """Editing the directory inputs should update in-memory state."""
    view = SettingsView()

    input_event = MagicMock()
    input_event.input.id = "settings-input-dir"
    input_event.value = "/data/in"
    view.on_input_changed(input_event)
    assert view._input_dir == "/data/in"

    output_event = MagicMock()
    output_event.input.id = "settings-output-dir"
    output_event.value = "/data/out"
    view.on_input_changed(output_event)
    assert view._output_dir == "/data/out"


def test_settings_view_save_action_persists_workflow_values() -> None:
    """Save action should persist the current workflow snapshot."""
    view = SettingsView()
    view._input_dir = "/data/in"
    view._output_dir = "/data/out"
    view._methodology = "para"
    view._text_model = "gemma2:2b-instruct-q4_K_M"
    view._check_updates = False
    view._include_prereleases = True

    with (
        patch("file_organizer.tui.settings_view.save_parallel_runtime_settings"),
        patch("file_organizer.tui.settings_view.save_workflow_settings") as mock_save,
        patch.object(view, "_refresh_panel"),
        patch.object(view, "_set_status"),
    ):
        view.action_save_settings()

    mock_save.assert_called_once()
    persisted = mock_save.call_args.args[0]
    assert persisted.default_input_dir == "/data/in"
    assert persisted.default_output_dir == "/data/out"
    assert persisted.methodology == "para"
    assert persisted.text_model == "gemma2:2b-instruct-q4_K_M"
    assert persisted.check_updates_on_startup is False
    assert persisted.include_prereleases is True
    assert mock_save.call_args.kwargs == {"profile": "default"}


# ---------------------------------------------------------------------------
# Parallelism actions (worker / prefetch adjustments)
# ---------------------------------------------------------------------------


def test_settings_view_workers_up_increments_from_auto() -> None:
    """Workers up from auto (None) should set an explicit count."""
    view = SettingsView()
    view._max_workers = None

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_workers_up()

    assert view._max_workers == 2


def test_settings_view_workers_down_returns_to_auto_at_one() -> None:
    """Workers down at 1 should drop back to auto (None)."""
    view = SettingsView()
    view._max_workers = 1

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_workers_down()

    assert view._max_workers is None


def test_settings_view_prefetch_up_and_down() -> None:
    """Prefetch depth should increase and clamp at zero."""
    view = SettingsView()
    view._max_workers = 2
    view._prefetch_depth = 0

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_prefetch_up()
        assert view._prefetch_depth == 1
        view.action_prefetch_down()
        view.action_prefetch_down()  # clamps, does not go negative
        assert view._prefetch_depth == 0


def test_settings_view_toggle_auto_workers() -> None:
    """Auto-workers toggle should flip between auto (None) and explicit 1."""
    view = SettingsView()
    view._max_workers = None

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_toggle_auto_workers()
        assert view._max_workers == 1
        view.action_toggle_auto_workers()
        assert view._max_workers is None


def test_settings_view_actions_blocked_in_sequential_mode() -> None:
    """Worker/prefetch actions should be inert while sequential mode is on."""
    view = SettingsView()
    view._max_workers = 1
    view._prefetch_depth = 0  # sequential

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status") as status:
        view.action_workers_up()
        view.action_prefetch_up()
        view.action_toggle_auto_workers()

    assert view._is_sequential is True
    assert status.call_count == 3  # each action reports the blocked state


def test_settings_view_toggle_sequential_restores_previous_values() -> None:
    """Leaving sequential mode should restore the prior worker/prefetch values."""
    view = SettingsView()
    view._max_workers = 4
    view._prefetch_depth = 3
    view._record_non_sequential_snapshot()

    with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status"):
        view.action_toggle_sequential()  # enable
        assert view._is_sequential is True
        view.action_toggle_sequential()  # disable -> restore

    assert view._max_workers == 4
    assert view._prefetch_depth == 3


# ---------------------------------------------------------------------------
# Mounted view: compose / on_mount / refresh / directory-input sync
# ---------------------------------------------------------------------------


async def test_settings_view_mounted_end_to_end(monkeypatch) -> None:
    """Mount the real view inside the app and exercise mount-bound methods."""
    from file_organizer.tui import settings_view as sv
    from file_organizer.tui.app import FileOrganizerApp

    # Keep the test hermetic: never touch the real config file on load or save.
    monkeypatch.setattr(sv, "save_parallel_runtime_settings", lambda *a, **k: None)
    monkeypatch.setattr(sv, "save_workflow_settings", lambda *a, **k: None)
    monkeypatch.setattr(
        sv,
        "load_parallel_runtime_settings",
        lambda **k: ParallelRuntimeSettings(max_workers=2, prefetch_depth=2),
    )
    monkeypatch.setattr(
        sv,
        "load_workflow_settings",
        lambda **k: WorkflowSettings(
            default_input_dir="/seed/in",
            default_output_dir="/seed/out",
            methodology="para",
            text_model="qwen2.5:7b-instruct-q4_K_M",
            provider="ollama",
            check_updates_on_startup=False,
            include_prereleases=True,
        ),
    )

    app = FileOrganizerApp()
    app.workspace.set_roots("/seed/in", "/seed/out")
    app.workspace.set_options(
        methodology="para",
        text_model="qwen2.5:7b-instruct-q4_K_M",
        parallel_workers=2,
        prefetch_depth=2,
    )
    async with app.run_test() as pilot:
        await app.action_switch_view("settings")
        await pilot.pause()
        view = app.query_one(SettingsView)

        # Mount reflects the shared session rather than replacing it with stale config.
        input_field = view.query_one("#settings-input-dir", Input)
        output_field = view.query_one("#settings-output-dir", Input)
        # set_roots stores a Path, so the field renders native separators — compare
        # against the same normalization rather than the POSIX spelling (on Windows
        # "/seed/in" round-trips as "\\seed\\in").
        assert input_field.value == str(Path("/") / "seed" / "in")
        assert output_field.value == str(Path("/") / "seed" / "out")

        # Editing an input updates in-memory state (real Input.Changed event).
        input_field.value = "/edited/in"
        await pilot.pause()
        assert view._input_dir == "/edited/in"

        # Exercise the actions against the mounted view (real _refresh_panel /
        # _set_status paths, including the StatusBar update).
        view.action_cycle_methodology()
        view.action_cycle_text_model()
        view.action_toggle_update_check()
        view.action_toggle_prereleases()
        view.action_workers_up()
        view.action_prefetch_up()
        view.action_toggle_sequential()
        view.action_save_settings()
        view.action_reload_settings()
        await pilot.pause()
