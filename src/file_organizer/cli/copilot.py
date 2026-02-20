"""CLI sub-command for the copilot chat interface.

Provides both an interactive REPL and a single-shot mode for sending
commands to the copilot engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

copilot_app = typer.Typer(
    name="copilot",
    help="AI copilot for interactive file organisation.",
)

console = Console()


@copilot_app.command(name="chat")
def copilot_chat(
    message: Optional[str] = typer.Argument(  # noqa: UP045
        None,
        help="Single message to send (omit for interactive REPL).",
    ),
    directory: Optional[str] = typer.Option(  # noqa: UP045
        None,
        "--dir",
        "-d",
        help="Working directory for file operations.",
    ),
) -> None:
    """Chat with the file-organisation copilot.

    Without a *message* argument an interactive REPL is launched.
    With a message argument the copilot responds once and exits.
    """
    from file_organizer.services.copilot.engine import CopilotEngine

    work_dir = directory or str(Path.cwd())
    engine = CopilotEngine(working_directory=work_dir)

    if message:
        # Single-shot mode
        response = engine.chat(message)
        console.print(response)
        return

    # Interactive REPL
    console.print(
        Panel(
            "[bold]File Organizer Copilot[/bold]\n"
            "Type your request or 'quit' to exit.\n"
            "Examples: 'organise ~/Downloads', 'find report.pdf', 'undo'",
            border_style="blue",
        )
    )

    while True:
        try:
            user_input = console.input("[bold blue]You>[/bold blue] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break

        stripped = user_input.strip()
        if not stripped:
            continue
        if stripped.lower() in ("quit", "exit", "q"):
            console.print("Goodbye!")
            break

        response = engine.chat(stripped)
        console.print(f"[bold green]Copilot>[/bold green] {escape(response)}")


@copilot_app.command(name="status")
def copilot_status() -> None:
    """Show copilot engine status."""
    console.print("[bold]Copilot Status[/bold]")

    # Check if text model is reachable
    try:
        import ollama as _ollama

        client = _ollama.Client()
        models = client.list()
        model_names = [m.get("name", "?") for m in models.get("models", [])]
        console.print(f"  Ollama models: {len(model_names)}")
        for name in model_names[:5]:
            console.print(f"    - {name}")
    except Exception as exc:
        console.print(f"  [yellow]Ollama unavailable: {exc}[/yellow]")

    console.print("  Copilot: [green]ready[/green]")
