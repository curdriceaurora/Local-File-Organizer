"""Utility CLI commands: search and analyze."""

from __future__ import annotations

import json as json_mod
import time
from pathlib import Path

import typer
from rich.console import Console

import file_organizer.cli._globals as _g
from file_organizer.utils import is_hidden

console = Console()


def search(
    query: str = typer.Argument(..., help="Search query (glob pattern or keyword)."),
    directory: Path = typer.Argument(".", help="Directory to search in.", exists=False),
    type_filter: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by type: text, image, video, audio, archive.",
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results to show."),
    recursive: bool = typer.Option(True, help="Search subdirectories."),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON array."),
    semantic: bool = typer.Option(
        False,
        "--semantic",
        help="Use hybrid BM25+vector semantic search instead of filename matching.",
    ),
) -> None:
    """Search for files by name pattern with optional type filtering."""
    from datetime import UTC, datetime

    # File type extension mappings
    type_extensions: dict[str, set[str]] = {
        "text": {
            ".txt",
            ".md",
            ".pdf",
            ".docx",
            ".doc",
            ".csv",
            ".xlsx",
            ".xls",
            ".ppt",
            ".pptx",
            ".epub",
            ".py",
            ".js",
            ".ts",
            ".html",
            ".css",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".rst",
            ".tex",
            ".log",
            ".cfg",
            ".ini",
            ".toml",
        },
        "image": {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".tiff",
            ".tif",
            ".webp",
            ".svg",
            ".ico",
        },
        "video": {
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
        },
        "audio": {
            ".mp3",
            ".wav",
            ".flac",
            ".m4a",
            ".ogg",
            ".aac",
            ".wma",
        },
        "archive": {
            ".zip",
            ".7z",
            ".tar",
            ".tar.gz",
            ".tgz",
            ".tar.bz2",
            ".rar",
            ".gz",
            ".bz2",
        },
    }

    # Validate limit
    if limit <= 0:
        if json_out:
            typer.echo("[]")
        else:
            console.print("[dim]No files found matching the query.[/dim]")
        raise typer.Exit(code=0)

    # Validate directory exists
    search_dir = directory.resolve()
    if not search_dir.is_dir():
        console.print(f"[red]Error: Directory '{directory}' does not exist.[/red]")
        raise typer.Exit(code=1)

    # Validate type filter
    if type_filter is not None and type_filter not in type_extensions:
        console.print(
            f"[red]Error: Unknown type '{type_filter}'. "
            f"Choose from: {', '.join(sorted(type_extensions))}[/red]"
        )
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Semantic path — hybrid BM25 + vector retrieval
    # ------------------------------------------------------------------
    if semantic:
        try:
            from file_organizer.services.search.hybrid_retriever import (
                HybridRetriever,
                read_text_safe,
            )
        except ImportError as exc:
            console.print(f"[red]Error: Semantic search unavailable: {exc}[/red]")
            raise typer.Exit(code=1) from exc

        documents: list[str] = []
        sem_paths: list[Path] = []
        max_docs = max(limit * 10, 200)  # cap corpus; retrieve extras for type-filter headroom

        gen = search_dir.rglob("*") if recursive else search_dir.glob("*")
        for entry in gen:
            if len(documents) >= max_docs:
                break
            rel_entry = entry.relative_to(search_dir)
            if entry.is_symlink() or not entry.is_file() or is_hidden(rel_entry):
                continue
            text = read_text_safe(entry)
            doc = f"{entry.stem} {' '.join(rel_entry.parts)} {text}".strip()
            documents.append(doc)
            sem_paths.append(entry)

        if not sem_paths:
            if json_out:
                typer.echo("[]")
            else:
                console.print("[dim]No files found for semantic indexing.[/dim]")
            raise typer.Exit(code=0)

        retriever = HybridRetriever()
        try:
            retriever.index(documents, sem_paths)
        except (ValueError, RuntimeError, ImportError) as exc:
            console.print(f"[red]Error: Failed to build semantic index: {exc}[/red]")
            raise typer.Exit(code=1) from exc

        # Fetch a larger candidate set so type filtering doesn't under-deliver
        candidate_k = limit * 4 if type_filter is not None else limit
        raw_results = retriever.retrieve(query, top_k=candidate_k)

        # Apply type filter, then cap at the requested limit
        if type_filter is not None:
            type_exts = type_extensions.get(type_filter, set())
            raw_results = [(p, s) for p, s in raw_results if p.suffix.lower() in type_exts]
        raw_results = raw_results[:limit]

        if not raw_results:
            if json_out:
                typer.echo("[]")
            else:
                console.print("[dim]No files found matching the query.[/dim]")
            raise typer.Exit(code=0)

        if json_out:
            records = []
            for p, score in raw_results[:limit]:
                stat = p.stat()
                records.append(
                    {
                        "path": str(p),
                        "score": round(score, 6),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    }
                )
            typer.echo(json_mod.dumps(records, indent=2))
        else:
            typer.echo(f"Found {len(raw_results)} file(s) [semantic]:")
            for p, score in raw_results[:limit]:
                stat = p.stat()
                size = stat.st_size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                typer.echo(
                    f"  {p}  {size_str}  {mtime.strftime('%Y-%m-%dT%H:%M:%SZ')}  score={score:.4f}"
                )
        raise typer.Exit(code=0)

    # ------------------------------------------------------------------
    # Default path — glob pattern or filename keyword matching
    # ------------------------------------------------------------------

    # Determine if query is a glob pattern or keyword
    is_glob = any(c in query for c in ("*", "?", "["))

    # Collect matching files
    matches: list[Path] = []

    if is_glob:
        # Use the glob pattern directly
        if recursive:
            candidates = search_dir.rglob(query)
        else:
            candidates = search_dir.glob(query)
    else:
        # For keyword search, enumerate all files and filter by name
        # This ensures case-insensitive matching across all platforms
        if recursive:
            candidates = search_dir.rglob("*")
        else:
            candidates = search_dir.glob("*")

    query_lower = query.lower()

    for path in candidates:
        if not path.is_file():
            continue

        # Case-insensitive substring matching for non-glob keyword queries
        if not is_glob:
            if query_lower not in path.name.lower():
                continue

        # Apply type filter
        if type_filter is not None:
            suffix = path.suffix.lower()
            # Handle compound extensions like .tar.gz
            if suffix == ".gz" and path.stem.endswith(".tar"):
                suffix = ".tar.gz"
            elif suffix == ".bz2" and path.stem.endswith(".tar"):
                suffix = ".tar.bz2"
            if suffix not in type_extensions[type_filter]:
                continue

        matches.append(path)
        if len(matches) >= limit:
            break

    # Output results
    if not matches:
        if json_out:
            typer.echo("[]")
        else:
            console.print("[dim]No files found matching the query.[/dim]")
        raise typer.Exit(code=0)

    if json_out:
        records = []
        for p in matches:
            stat = p.stat()
            records.append(
                {
                    "path": str(p),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                }
            )
        typer.echo(json_mod.dumps(records, indent=2))
    else:
        typer.echo(f"Found {len(matches)} file(s):")
        for p in matches:
            stat = p.stat()
            size = stat.st_size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"

            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            typer.echo(f"  {p}  {size_str}  {mtime.strftime('%Y-%m-%dT%H:%M:%SZ')}")


def analyze(
    file_path: Path = typer.Argument(..., help="File to analyze."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show additional details."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Analyze a file using AI and show description, category, and confidence."""
    from file_organizer.services.analyzer import (
        calculate_confidence,
        generate_category,
        generate_description,
        truncate_content,
    )

    # Check file exists and is a regular file
    if not file_path.is_file():
        console.print(f"[red]Error: File '{file_path}' not found.[/red]")
        raise typer.Exit(code=1)

    # Detect binary files before reading as text
    _BINARY_PEEK = 8192
    try:
        _header = file_path.read_bytes()[:_BINARY_PEEK]
    except OSError as exc:
        console.print(f"[red]Error: Could not read '{file_path}': {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if b"\x00" in _header:
        console.print(
            f"[yellow]Warning: '{file_path}' appears to be a binary file "
            "and cannot be analyzed as text.[/yellow]"
        )
        raise typer.Exit(code=1)

    # Read full text content (binary check passed)
    try:
        content = file_path.read_text(errors="ignore")
    except OSError as exc:
        console.print(f"[red]Error: Could not read '{file_path}': {exc}[/red]")
        raise typer.Exit(code=1) from exc

    content_length = len(content)
    content = truncate_content(content)

    # Initialize model
    try:
        from file_organizer.models.text_model import TextModel

        config = TextModel.get_default_config()
        model = TextModel(config)
        model.initialize()
    except ImportError as exc:
        console.print(
            "[red]Error: Ollama is not available. Please install Ollama to use AI analysis.[/red]"
        )
        raise typer.Exit(code=1) from exc

    # Run analysis
    start = time.monotonic()
    try:
        category = generate_category(model, content)
        description = generate_description(model, content)
        confidence = calculate_confidence(content, description)
    except RuntimeError as exc:
        console.print(f"[red]Error: AI analysis failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    elapsed = time.monotonic() - start

    # Output
    if json_output or _g.json_output:
        typer.echo(
            json_mod.dumps(
                {
                    "description": description,
                    "category": category,
                    "confidence": confidence,
                },
                indent=2,
            )
        )
    else:
        console.print(f"[bold]Category:[/bold] {category}")
        console.print(f"[bold]Description:[/bold] {description}")
        console.print(f"[bold]Confidence:[/bold] {confidence:.0%}")

        if verbose or _g.verbose:
            console.print(f"[bold]Model:[/bold] {config.name}")
            console.print(f"[bold]Processing time:[/bold] {elapsed:.2f}s")
            console.print(f"[bold]Content length:[/bold] {content_length} chars")
