#!/usr/bin/env python3
"""Demo script to launch the setup wizard for manual testing."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from textual.app import App, ComposeResult  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.widgets import Footer, Header  # noqa: E402

from file_organizer.tui.setup_wizard_view import SetupWizardView  # noqa: E402


class WizardDemoApp(App[None]):
    """Simple app to demo the setup wizard."""

    TITLE = "File Organizer - Setup Wizard Demo"
    SUB_TITLE = "Testing Hardware Detection Screen"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
    ]

    CSS = """
    Screen {
        background: $background;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the demo app layout."""
        yield Header()
        yield SetupWizardView(id="wizard")
        yield Footer()


def main():
    """Run the wizard demo app."""
    print("=" * 60)
    print("Setup Wizard Demo - Hardware Detection Screen")
    print("=" * 60)
    print("\nInstructions:")
    print("  1. Press Enter or '1' to start Quick Start mode")
    print("  2. Watch the hardware detection screen with progress")
    print("  3. Verify GPU, RAM, and recommended models are shown")
    print("  4. Press 'q' to quit")
    print("=" * 60)
    print()

    app = WizardDemoApp()
    app.run()


if __name__ == "__main__":
    main()
