"""Configuration management CLI sub-app."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

console = Console()

config_app = typer.Typer(help="Configuration management.")


@config_app.command(name="show")
def config_show(
    profile: str = typer.Option("default", help="Profile name."),
) -> None:
    """Show current configuration."""
    from file_organizer.config import ConfigManager

    mgr = ConfigManager()
    cfg = mgr.load(profile=profile)
    console.print(f"[bold]Profile:[/bold] {cfg.profile_name}")
    console.print(f"[bold]Methodology:[/bold] {cfg.default_methodology}")
    console.print(f"[bold]Text model:[/bold] {cfg.models.text_model}")
    console.print(f"[bold]Vision model:[/bold] {cfg.models.vision_model}")
    console.print(f"[bold]Temperature:[/bold] {cfg.models.temperature}")
    console.print(f"[bold]Device:[/bold] {cfg.models.device}")
    console.print(
        f"[bold]Update checks:[/bold] {'enabled' if cfg.updates.check_on_startup else 'disabled'}"
    )
    console.print(f"[bold]Update interval (hrs):[/bold] {cfg.updates.interval_hours}")
    console.print(f"[bold]Update repo:[/bold] {cfg.updates.repo}")
    console.print(f"[bold]Include prereleases:[/bold] {cfg.updates.include_prereleases}")


@config_app.command(name="list")
def config_list() -> None:
    """List available configuration profiles."""
    from file_organizer.config import ConfigManager

    mgr = ConfigManager()
    profiles = mgr.list_profiles()
    if not profiles:
        console.print("No profiles found. Run [bold]config edit[/bold] to create one.")
        return
    for name in profiles:
        console.print(f"  {name}")


@config_app.command(name="edit")
def config_edit(
    profile: str = typer.Option("default", help="Profile name to edit."),
    text_model: Optional[str] = typer.Option(None, help="Set text model name."),
    vision_model: Optional[str] = typer.Option(None, help="Set vision model name."),
    temperature: Optional[float] = typer.Option(None, help="Set temperature (0.0-1.0)."),
    device: Optional[str] = typer.Option(
        None, help="Set device (auto, cpu, cuda, mps, metal)."
    ),
    methodology: Optional[str] = typer.Option(
        None, help="Set default methodology (none, para, jd)."
    ),
) -> None:
    """Edit a configuration profile."""
    from file_organizer.config import ConfigManager

    _VALID_DEVICES = {"auto", "cpu", "cuda", "mps", "metal"}
    _VALID_METHODOLOGIES = {"none", "para", "jd"}

    # Validate constrained inputs before touching the config file.
    if temperature is not None and not (0.0 <= temperature <= 1.0):
        console.print(
            f"[red]Error: temperature must be between 0.0 and 1.0 (got {temperature}).[/red]"
        )
        raise typer.Exit(code=1)
    if device is not None and device not in _VALID_DEVICES:
        console.print(
            f"[red]Error: device must be one of {sorted(_VALID_DEVICES)} (got '{device}').[/red]"
        )
        raise typer.Exit(code=1)
    if methodology is not None and methodology not in _VALID_METHODOLOGIES:
        console.print(
            f"[red]Error: methodology must be one of "
            f"{sorted(_VALID_METHODOLOGIES)} (got '{methodology}').[/red]"
        )
        raise typer.Exit(code=1)

    mgr = ConfigManager()
    cfg = mgr.load(profile=profile)

    if text_model is not None:
        cfg.models.text_model = text_model
    if vision_model is not None:
        cfg.models.vision_model = vision_model
    if temperature is not None:
        cfg.models.temperature = temperature
    if device is not None:
        cfg.models.device = device
    if methodology is not None:
        cfg.default_methodology = methodology

    mgr.save(cfg, profile=profile)
    console.print(f"[green]Saved profile '{profile}'[/green]")
