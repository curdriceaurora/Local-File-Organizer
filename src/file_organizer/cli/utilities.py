"""Utility CLI commands: search and analyze."""

from __future__ import annotations

import json as json_mod
import os
import time
import warnings
from pathlib import Path

import typer
from rich.console import Console

import file_organizer.cli._globals as _g
from file_organizer.utils import is_hidden

console = Console()

# File type extension mappings
TYPE_EXTENSIONS: dict[str, set[str]] = {
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


def _normalized_extension(path: Path) -> str:
    """Return a normalized extension, preserving supported compound archives."""
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if len(suffixes) >= 2:
        compound = "".join(suffixes[-2:])
        if compound in {".tar.gz", ".tar.bz2"}:
            return compound
    return suffixes[-1] if suffixes else ""


def _validate_search_params(
    limit: int,
    directory: Path,
    type_filter: str | None,
) -> tuple[Path, bool]:
    """Validate search parameters and return resolved directory.

    Args:
        limit: Maximum number of results
        directory: Directory to search
        type_filter: Optional type filter

    Returns:
        Tuple of (resolved directory, should_exit)

    Raises:
        typer.Exit: If validation fails
    """
    search_dir = directory.resolve()
    if not search_dir.is_dir():
        console.print(f"[red]Error: Directory '{directory}' does not exist.[/red]")
        raise typer.Exit(code=1)

    if type_filter is not None and type_filter not in TYPE_EXTENSIONS:
        console.print(
            f"[red]Error: Unknown type '{type_filter}'. "
            f"Choose from: {', '.join(sorted(TYPE_EXTENSIONS))}[/red]"
        )
        raise typer.Exit(code=1)

    if limit <= 0:
        return search_dir, True

    return search_dir, False


def _format_file_size(size: int) -> str:
    """Format file size in human-readable format.

    Args:
        size: Size in bytes

    Returns:
        Formatted size string
    """
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _build_json_record(path: Path, score: float | None = None) -> dict[str, object] | None:
    """Build a JSON record for a file path.

    Args:
        path: File path
        score: Optional semantic search score

    Returns:
        Dictionary with file metadata, or None if the file can no longer be stat'ed.
    """
    from datetime import UTC, datetime

    try:
        stat = path.stat()
    except OSError as exc:
        warnings.warn(f"Skipping {path}: {exc}", RuntimeWarning, stacklevel=2)
        return None
    record: dict[str, object] = {
        "path": str(path),
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if score is not None:
        record["score"] = round(score, 6)
    return record


def _output_search_results(
    results: list[tuple[Path, float | None]],
    json_out: bool,
    search_type: str = "",
) -> None:
    """Output search results in JSON or text format.

    Args:
        results: List of (path, optional_score) tuples
        json_out: Whether to output as JSON
        search_type: Optional search type label for text output
    """
    from datetime import UTC, datetime

    if not results:
        if json_out:
            typer.echo("[]")
        else:
            console.print("[dim]No files found matching the query.[/dim]")
        return

    if json_out:
        records = [
            record
            for path, score in results
            if (record := _build_json_record(path, score)) is not None
        ]
        typer.echo(json_mod.dumps(records, indent=2))
    else:
        label = f" [{search_type}]" if search_type else ""
        rendered_results: list[tuple[Path, float | None, os.stat_result]] = []
        for path, score in results:
            try:
                stat = path.stat()
            except OSError as exc:
                warnings.warn(f"Skipping {path}: {exc}", RuntimeWarning, stacklevel=2)
                continue
            rendered_results.append((path, score, stat))

        typer.echo(f"Found {len(rendered_results)} file(s){label}:")
        for path, score, stat in rendered_results:
            size_str = _format_file_size(stat.st_size)
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            score_str = f"  score={score:.4f}" if score is not None else ""
            typer.echo(f"  {path}  {size_str}  {mtime.strftime('%Y-%m-%dT%H:%M:%SZ')}{score_str}")


def _do_semantic_search(
    query: str,
    search_dir: Path,
    type_filter: str | None,
    limit: int,
    recursive: bool,
) -> list[tuple[Path, float]]:
    """Perform semantic search using hybrid BM25+vector retrieval.

    Args:
        query: Search query
        search_dir: Directory to search
        type_filter: Optional file type filter
        limit: Maximum results
        recursive: Whether to search recursively

    Returns:
        List of (path, score) tuples

    Raises:
        typer.Exit: On import or indexing errors
    """
    try:
        from file_organizer.services.search.hybrid_retriever import HybridRetriever, read_text_safe
    except ImportError as exc:
        console.print(f"[red]Error: Semantic search unavailable: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    documents: list[str] = []
    sem_paths: list[Path] = []
    max_docs = max(limit * 10, 200)
    type_exts = TYPE_EXTENSIONS.get(type_filter) if type_filter is not None else None

    gen = search_dir.rglob("*") if recursive else search_dir.glob("*")
    for entry in gen:
        if len(documents) >= max_docs:
            break
        rel_entry = entry.relative_to(search_dir)
        if entry.is_symlink() or not entry.is_file() or is_hidden(rel_entry):
            continue
        if type_exts is not None and _normalized_extension(entry) not in type_exts:
            continue
        text = read_text_safe(entry)
        doc = f"{entry.stem} {' '.join(rel_entry.parts)} {text}".strip()
        documents.append(doc)
        sem_paths.append(entry)

    if not sem_paths:
        return []

    retriever = HybridRetriever()
    try:
        retriever.index(documents, sem_paths)
    except (ValueError, RuntimeError, ImportError) as exc:
        console.print(f"[red]Error: Failed to build semantic index: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    return retriever.retrieve(query, top_k=limit)


def _do_default_search(
    query: str,
    search_dir: Path,
    type_filter: str | None,
    limit: int,
    recursive: bool,
) -> list[Path]:
    """Perform default glob/keyword-based file search.

    Args:
        query: Search query (glob pattern or keyword)
        search_dir: Directory to search
        type_filter: Optional file type filter
        limit: Maximum results
        recursive: Whether to search recursively

    Returns:
        List of matching file paths
    """
    is_glob = any(c in query for c in ("*", "?", "["))

    if is_glob:
        candidates = search_dir.rglob(query) if recursive else search_dir.glob(query)
    else:
        candidates = search_dir.rglob("*") if recursive else search_dir.glob("*")

    query_lower = query.lower()
    matches: list[Path] = []

    for path in candidates:
        if not path.is_file():
            continue

        if not is_glob and query_lower not in path.name.lower():
            continue

        if type_filter is not None:
            suffix = _normalized_extension(path)
            if suffix not in TYPE_EXTENSIONS[type_filter]:
                continue

        matches.append(path)
        if len(matches) >= limit:
            break

    return matches


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
    search_dir, should_exit = _validate_search_params(limit, directory, type_filter)
    if should_exit:
        _output_search_results([], json_out)
        raise typer.Exit(code=0)

    if semantic:
        results = _do_semantic_search(query, search_dir, type_filter, limit, recursive)
        _output_search_results([(p, s) for p, s in results], json_out, "semantic")
        raise typer.Exit(code=0)

    matches = _do_default_search(query, search_dir, type_filter, limit, recursive)
    _output_search_results([(p, None) for p in matches], json_out)
    raise typer.Exit(code=0)


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
