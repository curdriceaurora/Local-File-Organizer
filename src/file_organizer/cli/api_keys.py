"""CLI commands for managing API keys locally."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

api_keys_app = typer.Typer(
    help="Manage API keys locally.",
    no_args_is_help=True,
)
console = Console()


@api_keys_app.command("generate")
def generate_key(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Path to safely store the generated API key.",
            show_default=False,
        ),
    ],
    prefix: Annotated[
        str,
        typer.Option(
            "--prefix",
            help="API key prefix.",
        ),
    ] = "fo",
) -> None:
    """Generate a secure API key and print its bcrypt hash."""
    from file_organizer.api.api_keys import _write_key, generate_api_key, hash_api_key
    from file_organizer.cli.path_validation import resolve_cli_path

    # Resolve output path
    resolved_output = resolve_cli_path(output, must_exist=False, must_be_dir=False)
    api_key = generate_api_key(prefix=prefix)
    _write_key(resolved_output, api_key)

    console.print(f"API key saved to: {resolved_output}")
    console.print(f"Bcrypt hash: {hash_api_key(api_key)}")
