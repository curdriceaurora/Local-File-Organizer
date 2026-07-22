# pyre-ignore-all-errors
"""TUI Settings view: the single place to configure an organize run.

Beyond the runtime parallelism controls (max workers, prefetch depth,
sequential mode), this view consolidates the most-used run knobs so Settings
is a one-stop configuration surface:

- default input/output directories (pre-filled for organize runs)
- organization methodology (none, PARA, Johnny Decimal)
- text model choice (cycles through curated Ollama presets)
- update / privacy toggles (check-on-startup, include pre-releases)

Every value is persisted through :class:`ConfigManager` onto the canonical
:class:`~file_organizer.config.schema.AppConfig` so the same configuration is
reused by the CLI, web UI, and other TUI workflows such as Organization
Preview.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, Static

from file_organizer.config.defaults import DEFAULT_TEXT_MODEL, DEFAULT_TEXT_MODEL_LARGE
from file_organizer.config.manager import ConfigManager
from file_organizer.config.methodology import LABELS as _METHODOLOGY_LABELS
from file_organizer.config.methodology import ORDER as _METHODOLOGY_ORDER
from file_organizer.config.methodology import normalize as _normalize_methodology
from file_organizer.tui.status import StatusMixin

if TYPE_CHECKING:
    from file_organizer.tui.workspace import TUIWorkspace

_DEFAULT_PREFETCH_DEPTH = 2
_MAX_WORKERS_CAP = max(1, os.cpu_count() or 1)
logger = logging.getLogger(__name__)

# Curated text-model presets cycled through with the "t" binding. A value
# persisted outside this list is preserved and prepended so cycling never
# silently discards a hand-picked model.
_TEXT_MODEL_PRESETS = (
    DEFAULT_TEXT_MODEL,
    DEFAULT_TEXT_MODEL_LARGE,
    "llama3.2:3b-instruct-q4_K_M",
    "gemma2:2b-instruct-q4_K_M",
)


@dataclass(frozen=True)
class ParallelRuntimeSettings:
    """Persisted runtime controls used by TUI organize/preview flows."""

    max_workers: int | None
    prefetch_depth: int

    @property
    def sequential(self) -> bool:
        """Return True when settings imply sequential execution."""
        return self.max_workers == 1 and self.prefetch_depth == 0


@dataclass(frozen=True)
class WorkflowSettings:
    """Persisted run-configuration knobs surfaced in the Settings view."""

    default_input_dir: str
    default_output_dir: str
    methodology: str
    text_model: str
    check_updates_on_startup: bool
    include_prereleases: bool


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


def load_workflow_settings(
    *,
    profile: str = "default",
    manager: ConfigManager | None = None,
) -> WorkflowSettings:
    """Load persistent run-configuration knobs from configuration."""
    resolved_manager = manager or ConfigManager()
    config = resolved_manager.load(profile=profile)

    text_model = config.models.text_model.strip() or DEFAULT_TEXT_MODEL
    return WorkflowSettings(
        default_input_dir=config.default_input_dir or "",
        default_output_dir=config.default_output_dir or "",
        methodology=_normalize_methodology(config.default_methodology),
        text_model=text_model,
        check_updates_on_startup=bool(config.updates.check_on_startup),
        include_prereleases=bool(config.updates.include_prereleases),
    )


def save_workflow_settings(
    settings: WorkflowSettings,
    *,
    profile: str = "default",
    manager: ConfigManager | None = None,
) -> None:
    """Persist run-configuration knobs to configuration."""
    resolved_manager = manager or ConfigManager()
    config = resolved_manager.load(profile=profile)

    config.default_input_dir = settings.default_input_dir.strip()
    config.default_output_dir = settings.default_output_dir.strip()
    config.default_methodology = _normalize_methodology(settings.methodology)
    config.models.text_model = settings.text_model.strip() or DEFAULT_TEXT_MODEL
    config.updates.check_on_startup = bool(settings.check_updates_on_startup)
    config.updates.include_prereleases = bool(settings.include_prereleases)

    resolved_manager.save(config, profile=profile)


class SettingsView(StatusMixin, Vertical):
    """Interactive TUI settings panel for run configuration."""

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

    SettingsView Input {
        margin: 0 0 1 0;
    }
    """

    BINDINGS = [
        Binding("up", "workers_up", "Workers +", show=True),
        Binding("down", "workers_down", "Workers -", show=True),
        Binding("right", "prefetch_up", "Prefetch +", show=True),
        Binding("left", "prefetch_down", "Prefetch -", show=True),
        Binding("s", "toggle_sequential", "Sequential", show=True),
        Binding("a", "toggle_auto_workers", "Auto Workers", show=True),
        Binding("m", "cycle_methodology", "Methodology", show=True),
        Binding("t", "cycle_text_model", "Model", show=True),
        Binding("u", "toggle_update_check", "Updates", show=True),
        Binding("p", "toggle_prereleases", "Pre-releases", show=True),
        Binding("c", "toggle_recursive", "Recursive", show=False),
        Binding("h", "toggle_hidden", "Hidden", show=False),
        Binding("x", "toggle_transfer", "Transfer", show=False),
        Binding("k", "toggle_skip_existing", "Collisions", show=False),
        Binding("v", "toggle_vision", "Vision", show=False),
        Binding("d", "toggle_transcription", "Transcription", show=False),
        Binding("enter", "save_settings", "Save", show=True),
        Binding("r", "reload_settings", "Reload", show=True),
    ]

    def __init__(
        self,
        *,
        profile: str = "default",
        workspace: TUIWorkspace | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Create the settings view with profile-backed persisted state."""
        super().__init__(name=name, id=id, classes=classes)
        self._profile = profile
        self._workspace = workspace
        # Parallelism controls
        self._max_workers: int | None = None
        self._prefetch_depth: int = _DEFAULT_PREFETCH_DEPTH
        self._last_non_sequential_workers: int | None = None
        self._last_non_sequential_prefetch_depth: int = _DEFAULT_PREFETCH_DEPTH
        # Workflow controls
        self._input_dir: str = ""
        self._output_dir: str = ""
        self._methodology: str = "none"
        self._text_model: str = DEFAULT_TEXT_MODEL
        self._check_updates: bool = True
        self._include_prereleases: bool = False
        options = workspace.options if workspace is not None else None
        self._recursive = options.recursive if options is not None else True
        self._include_hidden = options.include_hidden if options is not None else False
        self._skip_existing = options.skip_existing if options is not None else True
        self._transfer_mode = (
            options.effective_transfer_mode.value if options is not None else "hardlink"
        )
        self._enable_vision = options.enable_vision if options is not None else True
        self._transcribe_audio = options.transcribe_audio if options is not None else False
        if workspace is not None:
            self._input_dir = str(workspace.active_root or "")
            self._output_dir = str(workspace.output_root or "")
            self._methodology = workspace.options.effective_methodology.value
            self._text_model = workspace.options.text_model or DEFAULT_TEXT_MODEL
            self._max_workers = workspace.options.parallel_workers
            self._prefetch_depth = workspace.options.prefetch_depth

    def compose(self) -> ComposeResult:
        """Render settings panel content."""
        yield Static(self._render_text(), id="settings-body")
        yield Input(placeholder="Default input directory", id="settings-input-dir")
        yield Input(placeholder="Default output directory", id="settings-output-dir")

    def on_mount(self) -> None:
        """Load persisted settings when mounted."""
        if self._workspace is None:
            self.action_reload_settings()
        else:
            self._sync_dir_inputs()
            self._refresh_panel()

    # ------------------------------------------------------------------
    # Parallelism actions
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------

    def action_cycle_methodology(self) -> None:
        """Cycle the default organization methodology."""
        current = _normalize_methodology(self._methodology)
        index = _METHODOLOGY_ORDER.index(current)
        self._methodology = _METHODOLOGY_ORDER[(index + 1) % len(_METHODOLOGY_ORDER)]
        self._set_status(f"Methodology: {_METHODOLOGY_LABELS[self._methodology]}")
        self._refresh_panel()

    def action_cycle_text_model(self) -> None:
        """Cycle the text model through curated presets (preserving custom values)."""
        options = self._text_model_options()
        try:
            index = options.index(self._text_model)
        except ValueError:
            index = -1
        self._text_model = options[(index + 1) % len(options)]
        self._set_status(f"Text model: {self._text_model}")
        self._refresh_panel()

    def action_toggle_update_check(self) -> None:
        """Toggle checking for updates on startup."""
        self._check_updates = not self._check_updates
        state = "on" if self._check_updates else "off"
        self._set_status(f"Update check on startup: {state}")
        self._refresh_panel()

    def action_toggle_prereleases(self) -> None:
        """Toggle whether update checks include pre-releases."""
        self._include_prereleases = not self._include_prereleases
        state = "on" if self._include_prereleases else "off"
        self._set_status(f"Include pre-releases: {state}")
        self._refresh_panel()

    def action_toggle_recursive(self) -> None:
        """Toggle recursive traversal for this TUI session."""
        self._recursive = not self._recursive
        self._refresh_panel()

    def action_toggle_hidden(self) -> None:
        """Toggle hidden-file inclusion for this TUI session."""
        self._include_hidden = not self._include_hidden
        self._refresh_panel()

    def action_toggle_transfer(self) -> None:
        """Toggle between canonical hardlink and copy transfer modes."""
        self._transfer_mode = "copy" if self._transfer_mode == "hardlink" else "hardlink"
        self._refresh_panel()

    def action_toggle_skip_existing(self) -> None:
        """Toggle collision behavior between skip and counter rename."""
        self._skip_existing = not self._skip_existing
        self._refresh_panel()

    def action_toggle_vision(self) -> None:
        """Toggle vision-backed analysis for this TUI session."""
        self._enable_vision = not self._enable_vision
        self._refresh_panel()

    def action_toggle_transcription(self) -> None:
        """Toggle optional transcription-backed audio analysis."""
        self._transcribe_audio = not self._transcribe_audio
        self._refresh_panel()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Track directory inputs as the user edits them."""
        if event.input.id == "settings-input-dir":
            self._input_dir = event.value
        elif event.input.id == "settings-output-dir":
            self._output_dir = event.value

    # ------------------------------------------------------------------
    # Persistence actions
    # ------------------------------------------------------------------

    def action_reload_settings(self) -> None:
        """Reload persisted settings from configuration."""
        self._reload_parallel_settings()
        self._reload_workflow_settings()
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
            save_workflow_settings(
                self._current_workflow_settings(),
                profile=self._profile,
            )
        except Exception as exc:
            self._set_status(f"Failed to save settings: {exc}")
        else:
            self._sync_workspace()
            self._set_status("Settings saved.")
        self._refresh_panel()

    def _reload_parallel_settings(self) -> None:
        """Reload parallel controls, surfacing any load failure."""
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

    def _reload_workflow_settings(self) -> None:
        """Reload workflow controls, surfacing any load failure."""
        try:
            loaded = load_workflow_settings(profile=self._profile)
        except Exception as exc:
            self._set_status(f"Failed to load settings: {exc}")
            return
        self._input_dir = loaded.default_input_dir
        self._output_dir = loaded.default_output_dir
        self._methodology = loaded.methodology
        self._text_model = loaded.text_model
        self._check_updates = loaded.check_updates_on_startup
        self._include_prereleases = loaded.include_prereleases
        self._sync_dir_inputs()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_workflow_settings(self) -> WorkflowSettings:
        """Snapshot the in-memory workflow controls."""
        return WorkflowSettings(
            default_input_dir=self._input_dir,
            default_output_dir=self._output_dir,
            methodology=self._methodology,
            text_model=self._text_model,
            check_updates_on_startup=self._check_updates,
            include_prereleases=self._include_prereleases,
        )

    def _sync_workspace(self) -> None:
        """Apply the displayed settings to the shared canonical session state."""
        if self._workspace is None:
            return
        self._workspace.set_roots(self._input_dir, self._output_dir)
        self._workspace.set_options(
            recursive=self._recursive,
            include_hidden=self._include_hidden,
            skip_existing=self._skip_existing,
            transfer_mode=self._transfer_mode,
            methodology=self._methodology,
            enable_vision=self._enable_vision,
            transcribe_audio=self._transcribe_audio,
            parallel_workers=self._max_workers,
            prefetch_depth=self._prefetch_depth,
            text_model=self._text_model,
        )

    def _text_model_options(self) -> list[str]:
        """Return cycle options, prepending any persisted custom model."""
        if self._text_model in _TEXT_MODEL_PRESETS:
            return list(_TEXT_MODEL_PRESETS)
        return [self._text_model, *_TEXT_MODEL_PRESETS]

    def _sync_dir_inputs(self) -> None:
        """Push loaded directory values into the Input widgets when mounted."""
        try:
            self.query_one("#settings-input-dir", Input).value = self._input_dir
            self.query_one("#settings-output-dir", Input).value = self._output_dir
        except Exception:
            logger.debug("Directory inputs not mounted; skipping sync.", exc_info=True)

    @property
    def _is_sequential(self) -> bool:
        """Property indicating if sequential execution mode is enabled."""
        return self._max_workers == 1 and self._prefetch_depth == 0

    def _record_non_sequential_snapshot(self) -> None:
        """Keep restore point for leaving sequential mode."""
        if not self._is_sequential:
            self._last_non_sequential_workers = self._max_workers
            self._last_non_sequential_prefetch_depth = self._prefetch_depth

    def _refresh_panel(self) -> None:
        """Refresh the settings panel with current values."""
        body = self.query_one("#settings-body", Static)
        body.update(self._render_text())

    def _render_text(self) -> str:
        """Render formatted text content for the settings display."""
        workers_text = "auto" if self._max_workers is None else str(self._max_workers)
        sequential_text = "on" if self._is_sequential else "off"
        input_text = self._input_dir or "[dim](unset)[/dim]"
        output_text = self._output_dir or "[dim](unset)[/dim]"
        update_text = "on" if self._check_updates else "off"
        prerelease_text = "on" if self._include_prereleases else "off"
        recursive_text = "on" if self._recursive else "off"
        hidden_text = "include" if self._include_hidden else "exclude"
        collision_text = "skip existing" if self._skip_existing else "rename with counter"
        vision_text = "on" if self._enable_vision else "off"
        transcription_text = "on" if self._transcribe_audio else "off"
        return (
            "[b]Settings[/b]\n\n"
            "[b]Workflow[/b]\n"
            f"  input dir     : {input_text}\n"
            f"  output dir    : {output_text}\n"
            f"  methodology   : {_METHODOLOGY_LABELS[self._methodology]}\n"
            f"  text model    : {self._text_model}\n"
            f"  recursive     : {recursive_text}\n"
            f"  hidden files  : {hidden_text}\n"
            f"  transfer mode : {self._transfer_mode}\n"
            f"  collisions    : {collision_text}\n"
            f"  vision        : {vision_text}\n"
            f"  transcription : {transcription_text}\n"
            f"  update check  : {update_text}\n"
            f"  pre-releases  : {prerelease_text}\n\n"
            "[b]Persistent Runtime Controls[/b]\n"
            f"  max_workers   : {workers_text}\n"
            f"  prefetch_depth: {self._prefetch_depth}\n"
            f"  sequential    : {sequential_text}\n\n"
            "[dim]Arrows: workers/prefetch · s: sequential · a: auto workers[/dim]\n"
            "[dim]m: methodology · t: model · u: update check · p: pre-releases[/dim]\n"
            "[dim]c: recursive · h: hidden · x: transfer · k: collisions · "
            "v: vision · d: transcription[/dim]\n"
            "[dim]Type in the fields below to set directories · Enter: save · r: reload[/dim]"
        )
