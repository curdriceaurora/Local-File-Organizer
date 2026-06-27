"""AI model management CLI sub-app."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()

model_app = typer.Typer(help="AI model management.")


@model_app.command(name="list")
def model_list(
    type_filter: str | None = typer.Option(
        None, "--type", help="Filter by model type (text, vision, audio)."
    ),
) -> None:
    """List available AI models with install status."""
    from file_organizer.models.model_manager import ModelManager

    mgr = ModelManager(console=console)
    mgr.display_models(type_filter=type_filter)


@model_app.command(name="pull")
def model_pull(
    name: str = typer.Argument(
        ..., help="Model name to download (e.g. qwen2.5:3b-instruct-q4_K_M)."
    ),
) -> None:
    """Download an AI model via Ollama."""
    from file_organizer.models.model_manager import ModelManager

    mgr = ModelManager(console=console)
    success = mgr.pull_model(name=name)
    if not success:
        raise typer.Exit(code=1)


@model_app.command(name="cache")
def model_cache() -> None:
    """Show model cache statistics."""
    from file_organizer.models.model_manager import ModelManager

    mgr = ModelManager(console=console)
    info = mgr.cache_info()
    if not info:
        console.print("[dim]No cache data available.[/dim]")
        return
    for key, value in info.items():
        console.print(f"[bold]{key}:[/bold] {value}")
