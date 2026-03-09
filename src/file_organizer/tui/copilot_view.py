"""TUI copilot view — chat panel inside the Textual application.

Renders a scrollable message log and an input widget at the bottom.
Messages are dispatched to the ``CopilotEngine`` in a worker thread
so the UI stays responsive.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Static

from file_organizer.services.copilot.models import MessageRole

if TYPE_CHECKING:
    from file_organizer.services.copilot.engine import CopilotEngine


class CopilotMessageLog(VerticalScroll):
    """Scrollable log of copilot messages."""

    DEFAULT_CSS = """
    CopilotMessageLog {
        height: 1fr;
        padding: 1 2;
        scrollbar-size: 1 1;
    }
    """

    def add_message(self, role: MessageRole, text: str) -> None:
        """Append a message to the log.

        Args:
            role: Who sent the message.
            text: The message content.
        """
        if role == MessageRole.USER:
            markup = f"[bold blue]You>[/bold blue] {_escape(text)}"
        elif role == MessageRole.ASSISTANT:
            markup = f"[bold green]Copilot>[/bold green] {_escape(text)}"
        else:
            markup = f"[dim]{_escape(text)}[/dim]"

        widget = Static(markup)
        self.mount(widget)
        widget.scroll_visible()

    def add_system_note(self, text: str) -> None:
        """Append a system/info note.

        Args:
            text: The note text.
        """
        self.mount(Static(f"[dim italic]{_escape(text)}[/dim italic]"))


class CopilotInput(Input):
    """Input widget for the copilot chat."""

    DEFAULT_CSS = """
    CopilotInput {
        dock: bottom;
        margin: 0 1;
    }
    """


class CopilotView(Vertical):
    """Copilot chat panel mounted as ``#view`` in the TUI.

    Bindings:
        escape - Clear the input field
    """

    DEFAULT_CSS = """
    CopilotView {
        width: 1fr;
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("escape", "clear_input", "Clear", show=False),
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the copilot view with the given Textual widget parameters."""
        super().__init__(name=name, id=id, classes=classes)
        self._engine: CopilotEngine | None = None

    def compose(self) -> ComposeResult:
        """Build the copilot view layout."""
        yield Static(
            "[b]Copilot[/b]  [dim]Ask me to organise, find, move, rename, or undo.[/dim]\n",
            id="copilot-header",
        )
        yield CopilotMessageLog()
        yield CopilotInput(placeholder="Type a message...")

    def on_mount(self) -> None:
        """Focus the input widget and show welcome."""
        log = self.query_one(CopilotMessageLog)
        log.add_system_note(
            "Welcome! Type a request like 'organise ~/Downloads' or 'find report.pdf'."
        )
        self.query_one(CopilotInput).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user pressing Enter in the input."""
        text = event.value.strip()
        if not text:
            return

        # Clear input
        inp = self.query_one(CopilotInput)
        inp.value = ""

        # Show user message immediately
        log = self.query_one(CopilotMessageLog)
        log.add_message(MessageRole.USER, text)

        # Process in background
        self._process_message(text)

    def action_clear_input(self) -> None:
        """Clear the input field."""
        self.query_one(CopilotInput).value = ""

    @work(thread=True)
    def _process_message(self, text: str) -> None:
        """Send message to copilot engine in a worker thread.

        Args:
            text: User message text.
        """
        try:
            engine = self._get_engine()
            response = engine.chat(text)
            self.app.call_from_thread(
                self.query_one(CopilotMessageLog).add_message,
                MessageRole.ASSISTANT,
                response,
            )
        except Exception as exc:
            self.app.call_from_thread(
                self.query_one(CopilotMessageLog).add_system_note,
                f"Error: {exc}",
            )

        # Update status bar
        self.app.call_from_thread(self._set_status, "Copilot: ready")

    def _get_engine(self) -> CopilotEngine:
        """Lazily initialise the copilot engine.

        Returns:
            The ``CopilotEngine`` instance.
        """
        if self._engine is None:
            from file_organizer.services.copilot.engine import CopilotEngine

            self._engine = CopilotEngine()
        return self._engine

    def _set_status(self, message: str) -> None:
        """Update the app status bar if available."""
        try:
            from file_organizer.tui.app import StatusBar

            self.app.query_one(StatusBar).set_status(message)
        except Exception:
            pass


def _escape(text: str) -> str:
    """Escape Rich markup characters in user text.

    Args:
        text: Raw text.

    Returns:
        Escaped text safe for Rich rendering.
    """
    return text.replace("[", "\\[")
