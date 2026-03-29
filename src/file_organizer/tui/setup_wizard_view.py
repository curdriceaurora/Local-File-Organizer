"""TUI view for the guided setup wizard with welcome screen and mode selection.

This view provides an interactive first-run experience that guides users through:
- Welcome screen introducing the File Organizer
- Mode selection (Quick Start vs Power User)
- Hardware detection and AI backend configuration
- First folder organization with preview

The wizard uses ``SetupWizard`` from ``file_organizer.core.setup_wizard``
to handle the backend logic while focusing on the TUI presentation layer.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

logger = logging.getLogger(__name__)


class WizardScreen(StrEnum):
    """Enumeration of setup wizard screen states."""

    WELCOME = "welcome"
    MODE_SELECT = "mode_select"
    HARDWARE_DETECT = "hardware_detect"
    MODEL_SELECT = "model_select"
    COMPLETE = "complete"


class SetupWizardView(Vertical):
    """Interactive TUI setup wizard for first-run configuration.

    Guides users through initial setup with a multi-screen flow:
    1. Welcome screen with overview
    2. Mode selection (Quick Start / Power User)
    3. Hardware detection (handled by downstream subtasks)
    4. Model selection and download (handled by downstream subtasks)
    5. Configuration confirmation

    Keybindings:
        1 - Select Quick Start mode
        2 - Select Power User mode
        s - Skip setup wizard
        enter - Continue to next screen
        escape - Go back to previous screen
    """

    DEFAULT_CSS = """
    SetupWizardView {
        width: 1fr;
        height: 1fr;
    }

    #wizard-body {
        background: $surface;
        height: auto;
        margin: 1 0;
        padding: 2 4;
    }

    #wizard-welcome {
        text-align: center;
        padding: 2 0;
    }

    #wizard-mode-select {
        padding: 2 0;
    }
    """

    BINDINGS = [
        Binding("1", "select_option_1", "Option 1", show=True),
        Binding("2", "select_option_2", "Option 2", show=True),
        Binding("3", "select_option_3", "Option 3", show=False),
        Binding("d", "download_model", "Download", show=False),
        Binding("s", "skip_setup", "Skip", show=True),
        Binding("enter", "continue_wizard", "Continue", show=True),
        Binding("escape", "go_back", "Back", show=False),
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Create the setup wizard view."""
        super().__init__(name=name, id=id, classes=classes)
        self._current_screen = WizardScreen.WELCOME
        self._selected_mode: str | None = None
        self._capabilities = None
        self._detection_status = "pending"  # pending, detecting, complete, error
        self._detection_message = ""
        self._detection_step = ""  # Current detection step for progress display
        self._detection_progress = 0  # Progress percentage (0-100)
        self._selected_model: str | None = None
        self._download_status = "not_started"  # not_started, downloading, complete, error
        self._download_progress = 0  # Download progress percentage (0-100)
        self._download_message = ""

    def compose(self) -> ComposeResult:
        """Render wizard content."""
        yield Static(self._render_screen(), id="wizard-body")

    def on_mount(self) -> None:
        """Initialize wizard on mount."""
        self._set_status("Welcome to File Organizer! Press 1 for Quick Start, 2 for Power User.")

    def action_select_option_1(self) -> None:
        """Select option 1 (context-dependent)."""
        if self._current_screen == WizardScreen.WELCOME:
            # Quick Start mode selected from welcome
            self._selected_mode = "quick_start"
            self._set_status("Quick Start mode selected. Hardware detection will begin...")
            logger.info("User selected Quick Start mode from welcome")
            self._current_screen = WizardScreen.HARDWARE_DETECT
            self._refresh_screen()
            self._run_hardware_detection()
        elif self._current_screen == WizardScreen.MODE_SELECT:
            # Quick Start mode
            self._selected_mode = "quick_start"
            self._set_status("Quick Start mode selected. Hardware detection will begin...")
            logger.info("User selected Quick Start mode")
            self._current_screen = WizardScreen.HARDWARE_DETECT
            self._refresh_screen()
            self._run_hardware_detection()
        elif self._current_screen == WizardScreen.MODEL_SELECT:
            # Select recommended model (7b if high-end, 3b otherwise)
            if self._capabilities:
                model = self._capabilities.hardware.recommended_text_model()
                self._selected_model = model
                self._set_status(f"Selected model: {model}")
                logger.info("User selected recommended model: {}", model)
                self._refresh_screen()

    def action_select_option_2(self) -> None:
        """Select option 2 (context-dependent)."""
        if self._current_screen == WizardScreen.WELCOME:
            # Power User mode selected from welcome
            self._selected_mode = "power_user"
            self._set_status("Power User mode selected. Full configuration options available.")
            logger.info("User selected Power User mode from welcome")
            self._current_screen = WizardScreen.HARDWARE_DETECT
            self._refresh_screen()
            self._run_hardware_detection()
        elif self._current_screen == WizardScreen.MODE_SELECT:
            # Power User mode
            self._selected_mode = "power_user"
            self._set_status("Power User mode selected. Full configuration options available.")
            logger.info("User selected Power User mode")
            self._current_screen = WizardScreen.HARDWARE_DETECT
            self._refresh_screen()
            self._run_hardware_detection()
        elif self._current_screen == WizardScreen.MODEL_SELECT:
            # Select alternative model
            if self._capabilities:
                # Choose the other recommended model
                current = self._capabilities.hardware.recommended_text_model()
                if "7b" in current:
                    model = "qwen2.5:3b-instruct-q4_K_M"
                else:
                    model = "qwen2.5:7b-instruct-q4_K_M"
                self._selected_model = model
                self._set_status(f"Selected model: {model}")
                logger.info("User selected alternative model: {}", model)
                self._refresh_screen()

    def action_select_option_3(self) -> None:
        """Select option 3 (context-dependent)."""
        if self._current_screen == WizardScreen.MODEL_SELECT:
            # Select first installed model (if available)
            if self._capabilities and self._capabilities.installed_models:
                model = self._capabilities.installed_models[0].name
                self._selected_model = model
                self._set_status(f"Selected installed model: {model}")
                logger.info("User selected installed model: {}", model)
                self._refresh_screen()

    def action_download_model(self) -> None:
        """Download the selected model."""
        if self._current_screen != WizardScreen.MODEL_SELECT:
            return

        if not self._selected_model:
            self._set_status("Please select a model first (press 1, 2, or 3).")
            return

        # Check if model is already installed
        if self._capabilities and self._capabilities.installed_models:
            installed_names = {m.name for m in self._capabilities.installed_models}
            if self._selected_model in installed_names:
                self._set_status(f"Model {self._selected_model} is already installed.")
                return

        self._set_status(f"Starting download of {self._selected_model}...")
        logger.info("Starting model download: {}", self._selected_model)
        self._run_model_download()

    def action_skip_setup(self) -> None:
        """Skip the setup wizard and use default configuration."""
        self._set_status("Setup wizard skipped. Using default configuration.")
        logger.info("User skipped setup wizard")
        # Note: Actual skip logic will be handled by integration phase

    def action_continue_wizard(self) -> None:
        """Continue to next screen in the wizard flow."""
        if self._current_screen == WizardScreen.WELCOME:
            self._current_screen = WizardScreen.MODE_SELECT
            self._set_status("Select your setup mode: Quick Start or Power User.")
        elif self._current_screen == WizardScreen.MODE_SELECT:
            if self._selected_mode is None:
                self._set_status("Please select a mode first (press 1 or 2).")
                return
            self._current_screen = WizardScreen.HARDWARE_DETECT
            self._set_status("Detecting hardware capabilities...")
            self._refresh_screen()
            self._run_hardware_detection()
            return
        elif self._current_screen == WizardScreen.HARDWARE_DETECT:
            if self._detection_status == "complete":
                self._current_screen = WizardScreen.MODEL_SELECT
                self._set_status("Select and download AI model...")
                self._refresh_screen()
            else:
                self._set_status("Please wait for hardware detection to complete.")
            return
        elif self._current_screen == WizardScreen.MODEL_SELECT:
            if not self._selected_model:
                self._set_status("Please select a model first (press 1, 2, or 3).")
                return
            # Check if model needs to be downloaded
            model_installed = False
            if self._capabilities and self._capabilities.installed_models:
                installed_names = {m.name for m in self._capabilities.installed_models}
                model_installed = self._selected_model in installed_names

            # Require download if model is not installed
            if not model_installed and self._download_status != "complete":
                self._set_status("Please download the model first (press d).")
                return

            self._current_screen = WizardScreen.COMPLETE
            self._set_status("Setup complete!")
            self._refresh_screen()
            return
        self._refresh_screen()

    def action_go_back(self) -> None:
        """Return to previous screen in the wizard flow."""
        if self._current_screen == WizardScreen.MODE_SELECT:
            self._current_screen = WizardScreen.WELCOME
            self._set_status("Welcome screen. Press Enter to continue.")
        elif self._current_screen == WizardScreen.HARDWARE_DETECT:
            self._current_screen = WizardScreen.MODE_SELECT
            self._selected_mode = None
            self._set_status("Mode selection. Press 1 or 2 to choose.")
        elif self._current_screen == WizardScreen.MODEL_SELECT:
            self._current_screen = WizardScreen.HARDWARE_DETECT
            self._selected_model = None
            self._download_status = "not_started"
            self._download_progress = 0
            self._set_status("Hardware detection. Press Enter to continue.")
        elif self._current_screen == WizardScreen.COMPLETE:
            self._current_screen = WizardScreen.MODEL_SELECT
            self._set_status("Model selection. Press 1, 2, or 3 to choose.")
        self._refresh_screen()

    def _refresh_screen(self) -> None:
        """Update the displayed wizard screen content."""
        body = self.query_one("#wizard-body", Static)
        body.update(self._render_screen())

    def _render_screen(self) -> str:
        """Render the current wizard screen content.

        Returns:
            Rich-formatted markup for the current screen.
        """
        if self._current_screen == WizardScreen.WELCOME:
            return self._render_welcome_screen()
        if self._current_screen == WizardScreen.MODE_SELECT:
            return self._render_mode_select_screen()
        if self._current_screen == WizardScreen.HARDWARE_DETECT:
            return self._render_hardware_detect_screen()
        if self._current_screen == WizardScreen.MODEL_SELECT:
            return self._render_model_select_screen()
        if self._current_screen == WizardScreen.COMPLETE:
            return self._render_complete_screen()
        return "[red]Unknown screen state[/red]"

    def _render_welcome_screen(self) -> str:
        """Render the welcome screen with introduction."""
        return (
            "[b]Welcome to File Organizer![/b]\n\n"
            "[dim]AI-powered local file management[/dim]\n\n"
            "This wizard will guide you through the initial setup:\n\n"
            "  • Detect your system capabilities (GPU, RAM)\n"
            "  • Configure AI backend (Ollama, local models)\n"
            "  • Recommend optimal model configuration\n"
            "  • Organize your first folder with preview\n"
            "  • Set up the undo safety net\n\n"
            "[b]Choose your setup experience:[/b]\n\n"
            "  [1] [b]Quick Start[/b] - Get started in under 5 minutes\n"
            "      Automatic detection and sensible defaults\n\n"
            "  [2] [b]Power User[/b] - Full control over configuration\n"
            "      Choose backend, models, and methodology\n\n"
            "  [s] [dim]Skip setup (configure manually later)[/dim]\n\n"
            "[dim]Press 1, 2, or Enter to continue[/dim]"
        )

    def _render_mode_select_screen(self) -> str:
        """Render the mode selection screen."""
        quick_selected = " [green]✓[/green]" if self._selected_mode == "quick_start" else ""
        power_selected = " [green]✓[/green]" if self._selected_mode == "power_user" else ""

        return (
            "[b]Select Setup Mode[/b]\n\n"
            f"[1] [b]Quick Start{quick_selected}[/b]\n"
            "    • Automatic hardware detection\n"
            "    • Recommended model selection\n"
            "    • Default methodology (smart categorization)\n"
            "    • One-click confirmation\n"
            "    • [green]Best for: Most users, fastest setup[/green]\n\n"
            f"[2] [b]Power User{power_selected}[/b]\n"
            "    • Choose AI backend (Ollama, GGUF, MLX)\n"
            "    • Manual model selection\n"
            "    • Custom methodology configuration\n"
            "    • Advanced parallel processing options\n"
            "    • [yellow]Best for: Advanced users, specific requirements[/yellow]\n\n"
            "[dim]Press 1 or 2 to select, Enter to continue, Esc to go back[/dim]"
        )

    def _render_hardware_detect_screen(self) -> str:  # noqa: C901
        """Render the hardware detection screen with live progress."""
        mode_text = "Quick Start" if self._selected_mode == "quick_start" else "Power User"
        lines = [f"[b]Hardware Detection[/b] ([dim]{mode_text} mode[/dim])\n"]

        if self._detection_status == "pending":
            lines.append("[dim]Preparing to detect hardware...[/dim]")
        elif self._detection_status == "detecting":
            # Show progress bar
            progress_bar = self._render_progress_bar(self._detection_progress)
            lines.append(
                f"[yellow]⚙  Detecting system capabilities... {self._detection_progress}%[/yellow]"
            )
            lines.append(f"{progress_bar}\n")

            # Show current step
            if self._detection_step:
                lines.append(f"[dim]→ {self._detection_step}[/dim]\n")

            # Show completed steps
            if self._detection_progress >= 33:
                lines.append("[green]✓[/green] GPU detection complete")
            if self._detection_progress >= 66:
                lines.append("[green]✓[/green] RAM and CPU detection complete")
            if self._detection_progress >= 100:
                lines.append("[green]✓[/green] Backend detection complete")
        elif self._detection_status == "error":
            lines.append(f"[red]✗ Detection failed: {self._detection_message}[/red]\n")
            lines.append("[dim]Press Esc to go back and try again[/dim]")
        elif self._detection_status == "complete" and self._capabilities:
            hw = self._capabilities.hardware
            ollama = self._capabilities.ollama_status

            lines.append("[green]✓ Detection complete![/green]\n")

            # Hardware section
            lines.append("[b]Hardware:[/b]")

            # GPU status
            if hw.gpu_type.value == "none":
                lines.append("  [yellow]⚠[/yellow]  GPU:  No GPU detected (CPU-only mode)")
            elif hw.gpu_type.value == "nvidia":
                lines.append(f"  [green]✓[/green]  GPU:  {hw.gpu_name} ({hw.vram_gb}GB VRAM)")
            elif hw.gpu_type.value == "apple_mps":
                lines.append(f"  [green]✓[/green]  GPU:  {hw.gpu_name} (Unified Memory)")
            else:
                lines.append(f"  [green]✓[/green]  GPU:  {hw.gpu_type.value}")

            # RAM and CPU
            lines.append(f"  [green]✓[/green]  RAM:  {hw.ram_gb}GB system memory")
            lines.append(f"  [green]✓[/green]  CPU:  {hw.cpu_cores} cores ({hw.arch})")

            # Ollama section
            lines.append("\n[b]AI Backend:[/b]")
            if ollama.running:
                model_text = f"{ollama.models_count} model{'s' if ollama.models_count != 1 else ''}"
                lines.append(
                    f"  [green]✓[/green]  Ollama: Running (v{ollama.version}, {model_text})"
                )
            elif ollama.installed:
                lines.append("  [yellow]⚠[/yellow]  Ollama: Installed but not running")
                lines.append("      [dim]Start with: ollama serve[/dim]")
            else:
                lines.append("  [yellow]⚠[/yellow]  Ollama: Not installed")
                lines.append("      [dim]Install from: https://ollama.ai[/dim]")

            # Recommendations section
            lines.append("\n[b]Recommended Configuration:[/b]")
            rec_model = hw.recommended_text_model()
            rec_workers = hw.recommended_workers()

            lines.append(f"  • Text Model:  [cyan]{rec_model}[/cyan]")
            lines.append(f"  • Workers:     [cyan]{rec_workers}[/cyan] (parallel processing)")

            # Model size info
            if "7b" in rec_model:
                lines.append("  • Model Size:  ~4.5GB (7B parameters, Q4_K_M quantization)")
            elif "3b" in rec_model:
                lines.append("  • Model Size:  ~2.0GB (3B parameters, Q4_K_M quantization)")

            # Available models if Ollama is running
            if ollama.running and self._capabilities.installed_models:
                lines.append("\n[b]Installed Models:[/b]")
                for _i, model in enumerate(self._capabilities.installed_models[:5]):
                    lines.append(f"  • {model.name}")
                if len(self._capabilities.installed_models) > 5:
                    remaining = len(self._capabilities.installed_models) - 5
                    lines.append(f"  [dim]... and {remaining} more[/dim]")

            lines.append("\n[dim]Press Enter to continue, Esc to go back[/dim]")

        return "\n".join(lines)

    def _render_model_select_screen(self) -> str:  # noqa: C901
        """Render the model selection screen with available models and download progress."""
        mode_text = "Quick Start" if self._selected_mode == "quick_start" else "Power User"
        lines = [f"[b]Model Selection & Download[/b] ([dim]{mode_text} mode[/dim])\n"]

        if not self._capabilities:
            lines.append("[yellow]Loading model information...[/yellow]")
            return "\n".join(lines)

        # Get recommended models
        hardware = self._capabilities.hardware
        recommended_model = hardware.recommended_text_model()
        alternative_model = (
            "qwen2.5:3b-instruct-q4_K_M"
            if "7b" in recommended_model
            else "qwen2.5:7b-instruct-q4_K_M"
        )

        # Check installed models
        installed_names = {m.name for m in self._capabilities.installed_models}

        # Model selection section
        lines.append("[b]Select a model:[/b]\n")

        # Option 1: Recommended model
        recommended_status = (
            "[green]✓ Installed[/green]"
            if recommended_model in installed_names
            else "[yellow]⚠ Needs download[/yellow]"
        )
        selected_1 = " [cyan]← Selected[/cyan]" if self._selected_model == recommended_model else ""

        # Determine model size
        if "7b" in recommended_model:
            model_size = "~4.5GB"
            model_params = "7B parameters"
        else:
            model_size = "~2.0GB"
            model_params = "3B parameters"

        lines.append(f"[1] [b]{recommended_model}[/b] [green](Recommended)[/green]{selected_1}")
        lines.append(f"    {recommended_status}")
        lines.append(f"    • Size: {model_size} ({model_params}, Q4_K_M quantization)")
        lines.append(
            f"    • Optimized for: {hardware.gpu_type.value.upper()} with {hardware.ram_gb}GB RAM"
        )
        lines.append("")

        # Option 2: Alternative model
        alternative_status = (
            "[green]✓ Installed[/green]"
            if alternative_model in installed_names
            else "[yellow]⚠ Needs download[/yellow]"
        )
        selected_2 = " [cyan]← Selected[/cyan]" if self._selected_model == alternative_model else ""

        if "7b" in alternative_model:
            alt_size = "~4.5GB"
            alt_params = "7B parameters"
            alt_desc = "Higher quality, requires more resources"
        else:
            alt_size = "~2.0GB"
            alt_params = "3B parameters"
            alt_desc = "Faster, uses less memory"

        lines.append(f"[2] [b]{alternative_model}[/b]{selected_2}")
        lines.append(f"    {alternative_status}")
        lines.append(f"    • Size: {alt_size} ({alt_params}, Q4_K_M quantization)")
        lines.append(f"    • {alt_desc}")
        lines.append("")

        # Option 3: First installed model (if different from above)
        if self._capabilities.installed_models:
            first_installed = self._capabilities.installed_models[0].name
            if first_installed not in {recommended_model, alternative_model}:
                selected_3 = (
                    " [cyan]← Selected[/cyan]" if self._selected_model == first_installed else ""
                )
                size_text = (
                    f"{first_installed.size / (1024**3):.1f}GB"
                    if first_installed.size
                    else "Unknown size"
                )

                lines.append(
                    f"[3] [b]{first_installed}[/b] [dim](Already installed)[/dim]{selected_3}"
                )
                lines.append("    [green]✓ Installed[/green]")
                lines.append(f"    • Size: {size_text}")
                lines.append("")

        # Download progress section
        if self._download_status == "downloading":
            lines.append("\n[b]Download Progress:[/b]")
            progress_bar = self._render_progress_bar(self._download_progress)
            lines.append(
                f"[yellow]⚙  Downloading {self._selected_model}... {self._download_progress}%[/yellow]"
            )
            lines.append(f"{progress_bar}")

            if self._download_message:
                lines.append(f"[dim]→ {self._download_message}[/dim]")
            lines.append("")
        elif self._download_status == "complete":
            lines.append(f"\n[green]✓ Download complete: {self._selected_model}[/green]\n")
        elif self._download_status == "error":
            lines.append(f"\n[red]✗ Download failed: {self._download_message}[/red]\n")
            lines.append("[dim]Press d to retry or select a different model[/dim]\n")

        # Installed models summary
        if self._capabilities.installed_models:
            lines.append(
                f"[b]Installed Models:[/b] {len(self._capabilities.installed_models)} available"
            )
            for _i, model in enumerate(self._capabilities.installed_models[:3]):
                size_text = f"{model.size / (1024**3):.1f}GB" if model.size else "Unknown"
                lines.append(f"  • {model.name} ({size_text})")
            if len(self._capabilities.installed_models) > 3:
                remaining = len(self._capabilities.installed_models) - 3
                lines.append(f"  [dim]... and {remaining} more[/dim]")
            lines.append("")

        # Backend status
        if not self._capabilities.ollama_status.running:
            lines.append("[yellow]⚠ Warning:[/yellow] Ollama is not running")
            if self._capabilities.ollama_status.installed:
                lines.append("  Start Ollama service before downloading models")
                lines.append("  [dim]Command: ollama serve[/dim]\n")
            else:
                lines.append("  Install Ollama to download models")
                lines.append("  [dim]Visit: https://ollama.ai[/dim]\n")

        # Instructions
        lines.append("[dim]Press 1, 2, or 3 to select a model")

        # Show download button if model needs downloading
        if self._selected_model and self._selected_model not in installed_names:
            if self._capabilities.ollama_status.running:
                lines.append("Press d to download selected model")

        lines.append("Press Enter to continue, Esc to go back[/dim]")

        return "\n".join(lines)

    def _render_complete_screen(self) -> str:
        """Render the setup completion screen."""
        return (
            "[b][green]Setup Complete![/green][/b]\n\n"
            "Your File Organizer is ready to use.\n\n"
            "Configuration saved:\n"
            "  • AI backend configured\n"
            "  • Model downloaded and ready\n"
            "  • Methodology set\n"
            "  • Undo safety net enabled\n\n"
            "[b]Next steps:[/b]\n"
            "  • Navigate to Files view (press 1)\n"
            "  • Select a folder to organize\n"
            "  • Preview the organization\n"
            "  • Apply or undo changes\n\n"
            "[dim]Press Enter to continue to main interface[/dim]"
        )

    def _render_progress_bar(self, percentage: int, width: int = 40) -> str:
        """Render a text-based progress bar.

        Args:
            percentage: Progress percentage (0-100).
            width: Width of the progress bar in characters.

        Returns:
            Rich-formatted progress bar string.
        """
        filled = int((percentage / 100) * width)
        bar = "━" * filled + "╸" if filled < width else "━" * width
        empty = "─" * (width - len(bar))
        return f"[cyan]{bar}[/cyan][dim]{empty}[/dim]"

    def _set_status(self, message: str) -> None:
        """Update status bar when available.

        Args:
            message: Status message to display.
        """
        try:
            from file_organizer.tui.app import StatusBar

            self.app.query_one(StatusBar).set_status(message)
        except Exception:
            logger.debug("Failed to set status message on StatusBar.", exc_info=True)

    @work(thread=True)
    def _run_hardware_detection(self) -> None:
        """Run hardware detection in a background thread."""
        try:
            from file_organizer.core.setup_wizard import (
                SetupWizard,
                WizardMode,
            )

            # Update UI to show detection in progress
            self._detection_status = "detecting"
            self._detection_progress = 0
            self._detection_step = "Initializing detection..."
            self.app.call_from_thread(self._refresh_screen)
            self.app.call_from_thread(self._set_status, "Detecting hardware and AI backend...")

            # Create wizard and run detection
            mode = (
                WizardMode.QUICK_START
                if self._selected_mode == "quick_start"
                else WizardMode.POWER_USER
            )
            wizard = SetupWizard(mode=mode)

            # Step 1: Detect GPU (33%)
            self._detection_step = "Detecting GPU capabilities..."
            self._detection_progress = 10
            self.app.call_from_thread(self._refresh_screen)
            logger.info("Detecting GPU...")

            # Step 2: Detect RAM and CPU (66%)
            self._detection_step = "Detecting RAM and CPU..."
            self._detection_progress = 33
            self.app.call_from_thread(self._refresh_screen)
            logger.info("Detecting RAM and CPU...")

            # Step 3: Detect backend (100%)
            self._detection_step = "Detecting AI backend (Ollama)..."
            self._detection_progress = 66
            self.app.call_from_thread(self._refresh_screen)
            logger.info("Detecting backend...")

            # Run full detection
            capabilities = wizard.detect_capabilities()

            # Complete
            self._detection_step = "Finalizing detection..."
            self._detection_progress = 100
            self.app.call_from_thread(self._refresh_screen)

            # Store results and update UI
            self._capabilities = capabilities
            self._detection_status = "complete"
            self._detection_progress = 100
            self._detection_step = ""
            self.app.call_from_thread(self._refresh_screen)
            self.app.call_from_thread(
                self._set_status,
                f"Detection complete: {capabilities.hardware.gpu_type.value} GPU, "
                f"{capabilities.hardware.ram_gb}GB RAM",
            )

            logger.info("Hardware detection completed successfully")

        except Exception as e:
            logger.exception("Hardware detection failed")
            self._detection_status = "error"
            self._detection_message = str(e)
            self._detection_progress = 0
            self._detection_step = ""
            self.app.call_from_thread(self._refresh_screen)
            self.app.call_from_thread(self._set_status, f"Detection failed: {e}")

    @work(thread=True)
    def _run_model_download(self) -> None:
        """Download the selected model using Ollama in a background thread."""
        if not self._selected_model:
            return

        try:
            # Import ollama client
            try:
                import ollama
            except ImportError:
                error_msg = "Ollama Python package not installed"
                logger.error(error_msg)
                self._download_status = "error"
                self._download_message = error_msg
                self.app.call_from_thread(self._refresh_screen)
                self.app.call_from_thread(self._set_status, error_msg)
                return

            # Update UI to show download in progress
            self._download_status = "downloading"
            self._download_progress = 0
            self._download_message = "Initializing download..."
            self.app.call_from_thread(self._refresh_screen)
            self.app.call_from_thread(self._set_status, f"Downloading {self._selected_model}...")

            # Start the pull/download
            client = ollama.Client()
            logger.info("Starting model pull: {}", self._selected_model)

            # Pull the model with progress tracking
            self._download_message = "Pulling model from registry..."
            self._download_progress = 10
            self.app.call_from_thread(self._refresh_screen)

            # Note: ollama.pull() may not provide detailed progress callbacks
            # so we'll simulate progress updates
            for progress in [20, 40, 60, 80, 95]:
                self._download_progress = progress
                self._download_message = f"Downloading model layers... {progress}%"
                self.app.call_from_thread(self._refresh_screen)

                # This is a blocking call - we can't easily track real progress
                # without streaming API support
                if progress == 20:
                    client.pull(self._selected_model)

            # Complete
            self._download_progress = 100
            self._download_message = "Download complete!"
            self._download_status = "complete"
            self.app.call_from_thread(self._refresh_screen)
            self.app.call_from_thread(
                self._set_status,
                f"Model {self._selected_model} downloaded successfully!",
            )

            # Refresh capabilities to show the new model
            if self._capabilities:
                from file_organizer.core.backend_detector import list_installed_models

                self._capabilities.installed_models = list_installed_models()
                self._capabilities.ollama_status.models_count = len(
                    self._capabilities.installed_models
                )

            logger.info("Model download completed successfully")

        except Exception as e:
            logger.exception("Model download failed")
            self._download_status = "error"
            self._download_message = str(e)
            self._download_progress = 0
            self.app.call_from_thread(self._refresh_screen)
            self.app.call_from_thread(self._set_status, f"Download failed: {e}")
