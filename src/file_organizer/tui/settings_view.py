"""TUI view for persistent runtime parallelism controls.

This view is intentionally scoped to parallelism controls that map directly to
``FileOrganizer`` runtime knobs:
- max workers
- prefetch depth
- sequential mode (derived from workers=1, prefetch=0)

Values are persisted via ``ConfigManager`` under ``AppConfig.parallel`` so they
can be reused by TUI workflows such as Organization Preview.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from file_organizer.config.manager import ConfigManager

_DEFAULT_PREFETCH_DEPTH = 2
_MAX_WORKERS_CAP = max(1, os.cpu_count() or 1)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParallelRuntimeSettings:
    """Persisted runtime controls used by TUI organize/preview flows."""

    max_workers: int | None
    prefetch_depth: int

    @property
    def sequential(self) -> bool:
        """Return True when settings imply sequential execution."""
        return self.max_workers == 1 and self.prefetch_depth == 0


def _coerce_positive_int(value: Any, *, max_value: int | None = None) -> int | None:
    """Coerce value to a positive integer, optionally clamped to *max_value*."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    if max_value is not None:
        parsed = min(parsed, max_value)
    return parsed


def _coerce_non_negative_int(value: Any, *, default: int) -> int:
    """Coerce value to a non-negative integer with a safe default fallback."""
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def load_parallel_runtime_settings(
    *,
    profile: str = "default",
    manager: ConfigManager | None = None,
) -> ParallelRuntimeSettings:
    """Load persistent parallel runtime controls from configuration."""
    resolved_manager = manager or ConfigManager()
    config = resolved_manager.load(profile=profile)
    parallel = config.parallel or {}

    max_workers = _coerce_positive_int(parallel.get("max_workers"), max_value=_MAX_WORKERS_CAP)
    prefetch_depth = _coerce_non_negative_int(
        parallel.get("prefetch_depth"),
        default=_DEFAULT_PREFETCH_DEPTH,
    )
    return ParallelRuntimeSettings(
        max_workers=max_workers,
        prefetch_depth=prefetch_depth,
    )


def save_parallel_runtime_settings(
    settings: ParallelRuntimeSettings,
    *,
    profile: str = "default",
    manager: ConfigManager | None = None,
) -> None:
    """Persist parallel runtime settings to configuration."""
    resolved_manager = manager or ConfigManager()
    config = resolved_manager.load(profile=profile)

    parallel = dict(config.parallel or {})
    if settings.max_workers is None:
        parallel.pop("max_workers", None)
    else:
        normalized_workers = _coerce_positive_int(
            settings.max_workers,
            max_value=_MAX_WORKERS_CAP,
        )
        if normalized_workers is None:
            parallel.pop("max_workers", None)
        else:
            parallel["max_workers"] = normalized_workers

    if settings.prefetch_depth == _DEFAULT_PREFETCH_DEPTH:
        parallel.pop("prefetch_depth", None)
    else:
        parallel["prefetch_depth"] = settings.prefetch_depth

    config.parallel = parallel or None
    resolved_manager.save(config, profile=profile)


class SettingsView(Vertical):
    """Interactive TUI settings panel for runtime parallel controls."""

    DEFAULT_CSS = """
    SettingsView {
        width: 1fr;
        height: 1fr;
    }

    #settings-body {
        background: $surface;
        height: auto;
        margin: 1 0;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("up", "workers_up", "Workers +", show=True),
        Binding("down", "workers_down", "Workers -", show=True),
        Binding("right", "prefetch_up", "Prefetch +", show=True),
        Binding("left", "prefetch_down", "Prefetch -", show=True),
        Binding("s", "toggle_sequential", "Sequential", show=True),
        Binding("a", "toggle_auto_workers", "Auto Workers", show=True),
        Binding("enter", "save_settings", "Save", show=True),
        Binding("r", "reload_settings", "Reload", show=True),
    ]

    def __init__(
        self,
        *,
        profile: str = "default",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Create the settings view with profile-backed persisted state."""
        super().__init__(name=name, id=id, classes=classes)
        self._profile = profile
        self._max_workers: int | None = None
        self._prefetch_depth: int = _DEFAULT_PREFETCH_DEPTH
        self._last_non_sequential_workers: int | None = None
        self._last_non_sequential_prefetch_depth: int = _DEFAULT_PREFETCH_DEPTH

    def compose(self) -> ComposeResult:
        """Render settings panel content."""
        yield Static(self._render_text(), id="settings-body")

    def on_mount(self) -> None:
        """Load persisted settings when mounted."""
        self.action_reload_settings()

    def action_workers_up(self) -> None:
        """Increase worker count unless sequential mode is active."""
        if self._is_sequential:
            self._set_status("Disable sequential mode before changing workers.")
            return
        current = self._max_workers or 1
        if current >= _MAX_WORKERS_CAP:
            self._set_status(f"Max workers capped at {_MAX_WORKERS_CAP} for this machine.")
            self._refresh_panel()
            return
        self._max_workers = current + 1
        self._record_non_sequential_snapshot()
        self._refresh_panel()

    def action_workers_down(self) -> None:
        """Decrease worker count, falling back to auto workers at minimum."""
        if self._is_sequential:
            self._set_status("Disable sequential mode before changing workers.")
            return
        if self._max_workers is None:
            self._refresh_panel()
            return
        self._max_workers = self._max_workers - 1 if self._max_workers > 1 else None
        self._record_non_sequential_snapshot()
        self._refresh_panel()

    def action_prefetch_up(self) -> None:
        """Increase prefetch depth unless sequential mode is active."""
        if self._is_sequential:
            self._set_status("Disable sequential mode before changing prefetch depth.")
            return
        self._prefetch_depth += 1
        self._record_non_sequential_snapshot()
        self._refresh_panel()

    def action_prefetch_down(self) -> None:
        """Decrease prefetch depth to a non-negative value."""
        if self._is_sequential:
            self._set_status("Disable sequential mode before changing prefetch depth.")
            return
        self._prefetch_depth = max(0, self._prefetch_depth - 1)
        self._record_non_sequential_snapshot()
        self._refresh_panel()

    def action_toggle_auto_workers(self) -> None:
        """Toggle max workers between auto and explicit 1 worker."""
        if self._is_sequential:
            self._set_status("Disable sequential mode before toggling auto workers.")
            return
        self._max_workers = 1 if self._max_workers is None else None
        self._record_non_sequential_snapshot()
        self._refresh_panel()

    def action_toggle_sequential(self) -> None:
        """Toggle sequential mode (workers=1, prefetch=0)."""
        if self._is_sequential:
            self._max_workers = self._last_non_sequential_workers
            self._prefetch_depth = self._last_non_sequential_prefetch_depth
            self._set_status("Sequential mode disabled.")
        else:
            self._record_non_sequential_snapshot()
            self._max_workers = 1
            self._prefetch_depth = 0
            self._set_status("Sequential mode enabled.")
        self._refresh_panel()

    def action_reload_settings(self) -> None:
        """Reload persisted settings from configuration."""
        try:
            loaded = load_parallel_runtime_settings(profile=self._profile)
        except Exception as exc:
            self._set_status(f"Failed to load settings: {exc}")
        else:
            self._max_workers = loaded.max_workers
            self._prefetch_depth = loaded.prefetch_depth
            if not loaded.sequential:
                self._record_non_sequential_snapshot()
            self._set_status("Settings loaded.")
        self._refresh_panel()

    def action_save_settings(self) -> None:
        """Persist current settings to configuration."""
        try:
            save_parallel_runtime_settings(
                ParallelRuntimeSettings(
                    max_workers=self._max_workers,
                    prefetch_depth=self._prefetch_depth,
                ),
                profile=self._profile,
            )
        except Exception as exc:
            self._set_status(f"Failed to save settings: {exc}")
        else:
            self._set_status("Settings saved.")
        self._refresh_panel()

    @property
    def _is_sequential(self) -> bool:
        return self._max_workers == 1 and self._prefetch_depth == 0

    def _record_non_sequential_snapshot(self) -> None:
        """Keep restore point for leaving sequential mode."""
        if not self._is_sequential:
            self._last_non_sequential_workers = self._max_workers
            self._last_non_sequential_prefetch_depth = self._prefetch_depth

    def _refresh_panel(self) -> None:
        body = self.query_one("#settings-body", Static)
        body.update(self._render_text())

    def _render_text(self) -> str:
        workers_text = "auto" if self._max_workers is None else str(self._max_workers)
        sequential_text = "on" if self._is_sequential else "off"
        return (
            "[b]Settings[/b]\n\n"
            "[b]Persistent Runtime Controls[/b]\n"
            f"  max_workers   : {workers_text}\n"
            f"  prefetch_depth: {self._prefetch_depth}\n"
            f"  sequential    : {sequential_text}\n\n"
            "[dim]Use arrows to adjust values.[/dim]\n"
            "[dim]s: toggle sequential, a: toggle auto workers, Enter: save, r: reload[/dim]"
        )

    def _set_status(self, message: str) -> None:
        """Update status bar when available."""
        try:
            from file_organizer.tui.app import StatusBar

            self.app.query_one(StatusBar).set_status(message)
        except Exception:
            logger.debug("Failed to set status message on StatusBar.", exc_info=True)
