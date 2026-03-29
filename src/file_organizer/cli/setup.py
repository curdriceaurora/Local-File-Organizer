"""Setup wizard CLI sub-app."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from file_organizer.cli.interactive import confirm_action, console, prompt_choice
from file_organizer.core.setup_wizard import SetupWizard, WizardMode

setup_app = typer.Typer(help="Interactive setup wizard for first-run configuration.")


@setup_app.command(name="run")
def setup_run(  # noqa: C901
    mode: str = typer.Option(
        "quick-start",
        "--mode",
        "-m",
        help="Setup mode: quick-start or power-user.",
    ),
    profile: str = typer.Option("default", "--profile", "-p", help="Profile name."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without saving."),
) -> None:
    """Run the setup wizard to configure File Organizer.

    Quick-start mode: Automatic configuration with sensible defaults.
    Power-user mode: Full control over all configuration options.
    """
    # Validate mode
    mode = mode.lower().replace("_", "-")
    if mode not in ["quick-start", "power-user"]:
        console.print(
            f"[red]Error: mode must be 'quick-start' or 'power-user' (got '{mode}')[/red]"
        )
        raise typer.Exit(code=1)

    # Convert to enum
    wizard_mode = WizardMode.QUICK_START if mode == "quick-start" else WizardMode.POWER_USER

    # Display welcome message
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]File Organizer Setup Wizard[/bold cyan]\n\n"
            f"Mode: [bold]{mode}[/bold]\n"
            f"Profile: [bold]{profile}[/bold]",
            border_style="cyan",
        )
    )
    console.print()

    # Initialize wizard
    wizard = SetupWizard(mode=wizard_mode)

    # Detect capabilities
    console.print("[bold]Step 1:[/bold] Detecting system capabilities...")
    capabilities = wizard.detect_capabilities()

    # Display hardware info
    hw_table = Table(title="Hardware Profile", show_header=False, box=None)
    hw_table.add_column("Key", style="bold")
    hw_table.add_column("Value")

    hw_table.add_row("GPU Type", capabilities.hardware.gpu_type.value)
    if capabilities.hardware.gpu_name:
        hw_table.add_row("GPU Name", capabilities.hardware.gpu_name)
    hw_table.add_row("VRAM", f"{capabilities.hardware.vram_gb} GB")
    hw_table.add_row("System RAM", f"{capabilities.hardware.ram_gb} GB")
    hw_table.add_row("CPU Cores", str(capabilities.hardware.cpu_cores))
    hw_table.add_row("OS", capabilities.hardware.os_name)

    console.print(hw_table)
    console.print()

    # Display Ollama status
    if capabilities.ollama_status.running:
        console.print(
            f"[green]\u2713[/green] Ollama is running (v{capabilities.ollama_status.version})"
        )
        console.print(
            f"[green]\u2713[/green] Found {capabilities.ollama_status.models_count} installed models"
        )

        if capabilities.installed_models:
            model_table = Table(title="Available Models", box=None)
            model_table.add_column("Model Name", style="cyan")
            model_table.add_column("Size", justify="right")

            for model in capabilities.installed_models[:5]:  # Show first 5
                model_table.add_row(model.name, model.size or "N/A")

            console.print(model_table)
    elif capabilities.ollama_status.installed:
        console.print("[yellow]\u26a0[/yellow] Ollama is installed but not running")
        console.print("  Start it with: [bold]ollama serve[/bold]")
    else:
        console.print("[yellow]\u26a0[/yellow] Ollama is not installed")
        console.print("  Install from: [bold]https://ollama.ai[/bold]")

    console.print()

    # Generate configuration
    custom_settings: dict[str, str | int | float] | None = None

    if wizard_mode == WizardMode.QUICK_START:
        console.print("[bold]Step 2:[/bold] Auto-configuring with recommended settings...")
        console.print()

        # Build automatic configuration
        custom_settings = {}

        # Automatically select recommended model
        recommended = capabilities.hardware.recommended_text_model()

        if capabilities.installed_models:
            model_choices = [m.name for m in capabilities.installed_models]

            # Use recommended model if available, otherwise first available
            if recommended in model_choices:
                selected_model = recommended
                custom_settings["text_model"] = selected_model
                console.print(
                    f"[green]\u2713[/green] Selected recommended model: [bold]{selected_model}[/bold]"
                )
            else:
                selected_model = model_choices[0]
                custom_settings["text_model"] = selected_model
                console.print(
                    f"[yellow]\u26a0[/yellow] Recommended model '{recommended}' not found, using: [bold]{selected_model}[/bold]"
                )
        else:
            # No models installed - use recommended anyway
            custom_settings["text_model"] = recommended
            console.print(
                f"[yellow]\u26a0[/yellow] No models installed, will use: [bold]{recommended}[/bold]"
            )

        # Use sensible defaults
        custom_settings["methodology"] = "none"
        custom_settings["temperature"] = 0.5
        custom_settings["profile_name"] = profile

        console.print("[green]\u2713[/green] Using default methodology: [bold]none[/bold]")
        console.print("[green]\u2713[/green] Using default temperature: [bold]0.5[/bold]")
        console.print()

    elif wizard_mode == WizardMode.POWER_USER:
        console.print("[bold]Step 2:[/bold] Configuring options...")
        console.print()

        # Get user preferences
        custom_settings = {}

        # Backend/Framework selection
        framework = prompt_choice(
            "Select AI backend framework",
            ["ollama", "llama_cpp", "mlx"],
            default="ollama",
        )
        custom_settings["framework"] = framework

        # Model selection
        if capabilities.installed_models:
            model_choices = [m.name for m in capabilities.installed_models]
            recommended = capabilities.hardware.recommended_text_model()

            # Find default model
            default_model = None
            if recommended in model_choices:
                default_model = recommended
            elif model_choices:
                default_model = model_choices[0]

            selected_model = prompt_choice(
                "Select text model",
                model_choices,
                default=default_model,
            )
            custom_settings["text_model"] = selected_model

        # Methodology selection
        methodology = prompt_choice(
            "Select default organization methodology",
            ["none", "para", "jd"],
            default="none",
        )
        custom_settings["methodology"] = methodology

        # Temperature
        temp_input = typer.prompt(
            "Model temperature (0.0-1.0, default 0.5)",
            default="0.5",
        )
        try:
            custom_settings["temperature"] = float(temp_input)
        except ValueError:
            console.print("[yellow]Invalid temperature, using default 0.5[/yellow]")
            custom_settings["temperature"] = 0.5

        custom_settings["profile_name"] = profile

    console.print("[bold]Step 3:[/bold] Generating configuration...")
    config = wizard.generate_config(capabilities, custom_settings)

    # Display configuration preview
    console.print()
    config_table = Table(title="Configuration Preview", show_header=False, box=None)
    config_table.add_column("Setting", style="bold")
    config_table.add_column("Value")

    config_table.add_row("Profile", config.profile_name)
    config_table.add_row("Methodology", config.default_methodology)
    config_table.add_row("Text Model", config.models.text_model)
    config_table.add_row("Vision Model", config.models.vision_model or "N/A")
    config_table.add_row("Temperature", f"{config.models.temperature}")
    config_table.add_row("Framework", config.models.framework)
    config_table.add_row("Device", config.models.device)

    console.print(config_table)
    console.print()

    # Validate
    console.print("[bold]Step 4:[/bold] Validating configuration...")
    is_valid, errors = wizard.validate_config(config)

    if not is_valid:
        console.print("[red]Configuration validation failed:[/red]")
        for error in errors:
            console.print(f"  [red]\u2717[/red] {error}")
        raise typer.Exit(code=1)

    console.print("[green]\u2713[/green] Configuration is valid")
    console.print()

    # Save configuration
    if dry_run:
        console.print("[yellow]Dry run mode - configuration not saved[/yellow]")
    else:
        if confirm_action("Save this configuration?", default=True):
            wizard.save_config(config, profile)
            console.print(f"[green]\u2713[/green] Configuration saved to profile '{profile}'")
            console.print()
            console.print(
                Panel.fit(
                    "[bold green]Setup Complete![/bold green]\n\n"
                    "You can now organize files with:\n"
                    "  [bold]file-organizer organize <directory>[/bold]",
                    border_style="green",
                )
            )
        else:
            console.print("[yellow]Configuration not saved[/yellow]")


@setup_app.callback(invoke_without_command=True)
def setup_callback(ctx: typer.Context) -> None:
    """Default callback - run setup if no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(setup_run)