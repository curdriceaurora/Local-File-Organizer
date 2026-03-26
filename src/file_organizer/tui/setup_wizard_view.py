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
from enum import Enum

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

logger = logging.getLogger(__name__)


class WizardScreen(str, Enum):
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
        Binding("1", "select_quick_start", "Quick Start", show=True),
        Binding("2", "select_power_user", "Power User", show=True),
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

    def compose(self) -> ComposeResult:
        """Render wizard content."""
        yield Static(self._render_screen(), id="wizard-body")

    def on_mount(self) -> None:
        """Initialize wizard on mount."""
        self._set_status("Welcome to File Organizer! Press 1 for Quick Start, 2 for Power User.")

    def action_select_quick_start(self) -> None:
        """Select Quick Start mode and advance to next screen."""
        if self._current_screen != WizardScreen.MODE_SELECT:
            if self._current_screen == WizardScreen.WELCOME:
                self._current_screen = WizardScreen.MODE_SELECT
                self._refresh_screen()
            return

        self._selected_mode = "quick_start"
        self._set_status("Quick Start mode selected. Hardware detection will begin...")
        logger.info("User selected Quick Start mode")
        self._current_screen = WizardScreen.HARDWARE_DETECT
        self._refresh_screen()

    def action_select_power_user(self) -> None:
        """Select Power User mode and advance to next screen."""
        if self._current_screen != WizardScreen.MODE_SELECT:
            if self._current_screen == WizardScreen.WELCOME:
                self._current_screen = WizardScreen.MODE_SELECT
                self._refresh_screen()
            return

        self._selected_mode = "power_user"
        self._set_status("Power User mode selected. Full configuration options available.")
        logger.info("User selected Power User mode")
        self._current_screen = WizardScreen.HARDWARE_DETECT
        self._refresh_screen()

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

    def action_go_back(self) -> None:
        """Return to previous screen in the wizard flow."""
        if self._current_screen == WizardScreen.MODE_SELECT:
            self._current_screen = WizardScreen.WELCOME
            self._set_status("Welcome screen. Press Enter to continue.")
        elif self._current_screen == WizardScreen.HARDWARE_DETECT:
            self._current_screen = WizardScreen.MODE_SELECT
            self._selected_mode = None
            self._set_status("Mode selection. Press 1 or 2 to choose.")
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

    def _render_hardware_detect_screen(self) -> str:
        """Render the hardware detection screen (placeholder for subtask-3-2)."""
        mode_text = "Quick Start" if self._selected_mode == "quick_start" else "Power User"
        return (
            f"[b]Hardware Detection[/b] ([dim]{mode_text} mode[/dim])\n\n"
            "[yellow]Detecting system capabilities...[/yellow]\n\n"
            "This screen will be implemented in subtask-3-2:\n"
            "  • GPU detection and VRAM availability\n"
            "  • System RAM and CPU information\n"
            "  • Ollama installation status\n"
            "  • Available models\n"
            "  • Recommended configuration\n\n"
            "[dim]Press Esc to go back[/dim]"
        )

    def _render_model_select_screen(self) -> str:
        """Render the model selection screen (placeholder for subtask-3-3)."""
        return (
            "[b]Model Selection & Download[/b]\n\n"
            "[yellow]Model configuration...[/yellow]\n\n"
            "This screen will be implemented in subtask-3-3:\n"
            "  • Available models list\n"
            "  • Model size and requirements\n"
            "  • Download progress bars\n"
            "  • Installation status\n\n"
            "[dim]Press Esc to go back[/dim]"
        )

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
