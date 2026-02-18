"""Model manager — list, pull, and inspect AI models.

Wraps the Ollama CLI and the static model registry to provide
user-facing model operations.
"""

from __future__ import annotations

import json
import logging
import subprocess

from rich.console import Console
from rich.table import Table

from file_organizer.models.registry import AVAILABLE_MODELS, ModelInfo

logger = logging.getLogger(__name__)


class ModelManager:
    """Manage AI models for File Organizer.

    Combines the static :data:`AVAILABLE_MODELS` registry with live
    ``ollama list`` data to show installed status, and delegates to
    ``ollama pull`` for downloading new models.
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

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
        models = []
        for m in AVAILABLE_MODELS:
            if type_filter and m.model_type != type_filter:
                continue
            m.installed = self._is_installed(m.name, installed)
            models.append(m)
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
