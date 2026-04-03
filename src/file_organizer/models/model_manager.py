# pyre-ignore-all-errors
"""Model manager - list, pull, inspect, and hot-swap AI models.

Wraps the Ollama CLI and the model registry to provide user-facing
model operations, including atomic model swapping with drain and
rollback semantics.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from collections.abc import Callable

from rich.console import Console
from rich.table import Table

from file_organizer.models.registry import (
    ModelInfo,
    get_all_models,
    get_audio_models,
    get_text_models,
    get_vision_models,
)

logger = logging.getLogger(__name__)


class ModelManager:
    """Manage AI models for File Organizer.

    Combines the static model registry with live ``ollama list`` data
    to show installed status, and delegates to ``ollama pull`` for
    downloading new models.  Supports atomic model hot-swapping with
    drain/pre-warm/rollback semantics.
    """

    def __init__(self, console: Console | None = None) -> None:
        """Initialize ModelManager with optional Rich console."""
        self._console = console or Console()
        self._swap_lock = threading.Lock()
        self._active_models: dict[str, object] = {}  # model_type -> live model instance
        self._active_model_ids: dict[str, str] = {}  # model_type -> selected model id

    # ------------------------------------------------------------------
    # Installed model detection
    # ------------------------------------------------------------------

    def check_installed(self) -> set[str]:
        """Query Ollama for locally installed model names.

        Returns:
            Set of installed model name strings.
        """
        try:
            result = subprocess.run(
                ["ollama", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                # Fallback: parse human-readable output
                return self._parse_ollama_list_text()

            data = json.loads(result.stdout)
            if isinstance(data, dict) and "models" in data:
                return {m.get("name", "") for m in data["models"]}
            if isinstance(data, list):
                return {m.get("name", "") for m in data}
            return set()
        except FileNotFoundError:
            logger.warning("Ollama CLI not found. Install from https://ollama.ai")
            return set()
        except Exception:
            logger.debug("Failed to query Ollama", exc_info=True)
            return self._parse_ollama_list_text()

    def _parse_ollama_list_text(self) -> set[str]:
        """Fallback: parse ``ollama list`` plain text output."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            names: set[str] = set()
            for line in result.stdout.strip().splitlines()[1:]:  # skip header
                parts = line.split()
                if parts:
                    names.add(parts[0])
            return names
        except Exception:
            return set()

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_models(self, type_filter: str | None = None) -> list[ModelInfo]:
        """Return available models with live installed status.

        Args:
            type_filter: Restrict to a model type (text, vision, audio).

        Returns:
            List of ModelInfo with ``installed`` populated.
        """
        installed = self.check_installed()

        if type_filter == "text":
            models = get_text_models()
        elif type_filter == "vision":
            models = get_vision_models()
        elif type_filter == "audio":
            models = get_audio_models()
        elif type_filter is None:
            models = get_all_models()
        else:
            models = [m for m in get_all_models() if m.model_type == type_filter]

        for m in models:
            m.installed = self._is_installed(m.name, installed)
        return models

    def display_models(self, type_filter: str | None = None) -> None:
        """Print a Rich table of available models.

        Args:
            type_filter: Restrict to a model type.
        """
        models = self.list_models(type_filter)
        table = Table(title="Available Models", show_lines=True)
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Size", justify="right")
        table.add_column("Quant")
        table.add_column("Installed", justify="center")
        table.add_column("Description")

        for m in models:
            status = "[green]Yes[/green]" if m.installed else "[dim]No[/dim]"
            table.add_row(m.name, m.model_type, m.size, m.quantization, status, m.description)

        self._console.print(table)

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------

    def pull_model(self, name: str) -> bool:
        """Download a model via ``ollama pull``.

        Args:
            name: Ollama model tag to pull.

        Returns:
            True on success, False on failure.
        """
        self._console.print(f"[bold]Pulling model:[/bold] {name}")
        try:
            proc = subprocess.run(
                ["ollama", "pull", name],
                timeout=600,
            )
            if proc.returncode == 0:
                self._console.print(f"[green]Model '{name}' pulled successfully.[/green]")
                return True
            self._console.print(f"[red]Pull failed (exit code {proc.returncode}).[/red]")
            return False
        except FileNotFoundError:
            self._console.print("[red]Ollama CLI not found. Install from https://ollama.ai[/red]")
            return False
        except subprocess.TimeoutExpired:
            self._console.print("[red]Pull timed out.[/red]")
            return False

    # ------------------------------------------------------------------
    # Hot-swap
    # ------------------------------------------------------------------

    def swap_model(
        self,
        model_type: str,
        new_model_id: str,
        *,
        model_factory: Callable[[], object] | None = None,
    ) -> bool:
        """Atomically swap the active model for *model_type*.

        Swap sequence (under lock):

        1. Pre-warm the new model synchronously via *model_factory*.
        2. Atomic reference swap (old -> new) so callers immediately see
           the new model; no drain window where the old model is visible
           but already shutting down.
        3. Drain the old model via ``safe_cleanup()`` (if supported).

        On failure at step 1, the old model remains active (rollback).
        On drain failure at step 3, the swap is already committed; the
        drain error is logged but does not affect the return value.

        Args:
            model_type: ``"text"``, ``"vision"``, or ``"audio"``.
            new_model_id: Model identifier to swap to.
            model_factory: Optional factory callable that returns a new
                model instance.  When *None*, the swap is recorded in
                the registry but no live model is loaded.

        Returns:
            ``True`` on success, ``False`` on rollback.
        """
        if not self._swap_lock.acquire(blocking=False):
            logger.warning("Swap already in progress for %s", model_type)
            return False

        try:
            old_model = self._active_models.get(model_type)
            # Step 1: Pre-warm new model
            new_model: object | None = None
            if model_factory is not None:
                try:
                    new_model = model_factory()
                    if hasattr(new_model, "initialize"):
                        new_model.initialize()
                except Exception:
                    logger.exception(
                        "Failed to pre-warm new model %s for %s",
                        new_model_id,
                        model_type,
                    )
                    # Clean up partially initialized model
                    if new_model is not None and hasattr(new_model, "cleanup"):
                        try:
                            new_model.cleanup()
                        except Exception:
                            logger.debug("Cleanup of partial model failed", exc_info=True)
                    return False

            # Step 2: Atomic swap — callers see new model before old is drained
            self._active_model_ids[model_type] = new_model_id
            if new_model is not None:
                self._active_models[model_type] = new_model
            else:
                self._active_models.pop(model_type, None)

            logger.info("Swapped %s model to %s", model_type, new_model_id)

            # Step 3: Drain old model (best-effort; swap already committed)
            if old_model is not None and hasattr(old_model, "safe_cleanup"):
                try:
                    old_model.safe_cleanup()
                except Exception:
                    logger.exception("Drain failed for old %s model (swap committed)", model_type)

            return True

        finally:
            self._swap_lock.release()

    def get_active_model(self, model_type: str) -> object | None:
        """Return the currently loaded model instance for *model_type*.

        Returns:
            The loaded model instance, or ``None`` if no model is loaded.
        """
        return self._active_models.get(model_type)

    def get_active_model_id(self, model_type: str) -> str | None:
        """Return the selected model ID for *model_type*, whether loaded or not.

        Returns:
            The model ID string most recently swapped to, or ``None`` if
            no swap has been performed for *model_type*.
        """
        return self._active_model_ids.get(model_type)

    # ------------------------------------------------------------------
    # Cache info
    # ------------------------------------------------------------------

    def cache_info(self) -> dict[str, object]:
        """Return model cache statistics.

        Delegates to the optimization module's ModelCache if available.

        Returns:
            Dict with cache stats or an empty dict if unavailable.
        """
        try:
            from file_organizer.optimization.model_cache import ModelCache

            cache = ModelCache()
            stats = cache.stats()
            return {
                "hits": stats.hits,
                "misses": stats.misses,
                "evictions": stats.evictions,
                "current_size": stats.current_size,
                "max_size": stats.max_size,
                "memory_usage_bytes": stats.memory_usage_bytes,
            }
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _is_installed(model_name: str, installed_names: set[str]) -> bool:
        """Check whether *model_name* matches any installed model.

        Handles partial tag matching (e.g. ``qwen2.5:3b`` matches
        ``qwen2.5:3b-instruct-q4_K_M``).
        """
        if model_name in installed_names:
            return True
        # Check prefix match (ollama may store with or without tag details)
        base = model_name.split(":")[0] if ":" in model_name else model_name
        return any(n.startswith(base) for n in installed_names)
