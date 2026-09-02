"""Utility CLI commands: search and analyze."""

from __future__ import annotations

import json as json_mod
import os
import time
import warnings
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from file_organizer.cli.path_validation import resolve_cli_path
from file_organizer.cli.state import _get_state
from file_organizer.core.path_guard import safe_walk

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

    gen = safe_walk(search_dir, recursive=recursive)
    for entry in gen:
        if len(documents) >= max_docs:
            break
        rel_entry = entry.relative_to(search_dir)
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
        candidates = safe_walk(search_dir, pattern=query, recursive=recursive)
    else:
        candidates = safe_walk(search_dir, recursive=recursive)

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
    query: Annotated[str, typer.Argument(help="Search query (glob pattern or keyword).")],
    directory: Annotated[Path, typer.Argument(help="Directory to search in.")] = Path("."),
    type_filter: Annotated[
        str | None,
        typer.Option(
            "--type",
            "-t",
            help="Filter by type: text, image, video, audio, archive.",
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results to show.")] = 50,
    recursive: Annotated[bool, typer.Option(help="Search subdirectories.")] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output as JSON array.")] = False,
    semantic: Annotated[
        bool,
        typer.Option(
            "--semantic",
            help="Use hybrid BM25+vector semantic search instead of filename matching.",
        ),
    ] = False,
) -> None:
    """Search for files by name pattern with optional type filtering."""
    directory = resolve_cli_path(directory, must_exist=True, must_be_dir=True)
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
    file_path: Annotated[Path, typer.Argument(help="File to analyze.")],
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show additional details.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Analyze a file using AI and show description, category, and confidence."""
    # A.cli: `resolve_cli_path(must_be_dir=False)` accepts any existing
    # path (file, dir, socket, fifo). Keep the explicit is_file() guard so
    # directories and special files get a clear "not a regular file"
    # error rather than a later decode failure.
    file_path = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    if not file_path.is_file():
        console.print(f"[red]Error: File '{file_path}' is not a regular file.[/red]")
        raise typer.Exit(code=1)

    if _normalized_extension(file_path) in TYPE_EXTENSIONS["image"]:
        _analyze_image_file(file_path, verbose=verbose, json_output=json_output)
        raise typer.Exit(code=0)

    _analyze_text_file(file_path, verbose=verbose, json_output=json_output)
    raise typer.Exit(code=0)


def _analyze_image_file(file_path: Path, *, verbose: bool, json_output: bool) -> None:
    """Analyze a single image with the configured vision model."""
    processor: Any | None = None
    try:
        from file_organizer.config.provider_env import get_model_configs
        from file_organizer.services.vision_processor import VisionProcessor

        _, vision_config = get_model_configs()
        processor = VisionProcessor(config=vision_config)
        processor.initialize()
    except ImportError as exc:
        _cleanup_vision_processor(processor, json_output=json_output)
        console.print(
            "[red]Error: Vision analysis dependencies are not available. "
            "Install the required vision extras and model backend.[/red]"
        )
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _cleanup_vision_processor(processor, json_output=json_output)
        console.print(f"[red]Error: Could not initialize vision analysis: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    start = time.monotonic()
    try:
        result = processor.process_file(file_path)
    except Exception as exc:
        console.print(f"[red]Error: AI analysis failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        _cleanup_vision_processor(processor, json_output=json_output)

    elapsed = time.monotonic() - start
    warning = None
    if result.error:
        warning = f"Vision analysis degraded ({result.source}): {result.error}"

    _emit_analysis_result(
        description=result.description,
        category=result.folder_name,
        confidence=result.confidence,
        json_output=json_output,
        verbose=verbose,
        json_extra={
            "filename": result.filename,
            "has_text": result.has_text,
            "extracted_text": result.extracted_text,
            "source": result.source,
            "error": result.error,
        },
        verbose_rows=[
            ("Model", vision_config.name),
            ("Processing time", f"{elapsed:.2f}s"),
            *(
                [("Extracted text", result.extracted_text)]
                if result.has_text and result.extracted_text
                else []
            ),
        ],
        warning=warning,
    )


def _cleanup_vision_processor(processor: Any | None, *, json_output: bool) -> None:
    """Best-effort cleanup that never masks the primary analysis result."""
    if processor is None:
        return
    try:
        processor.cleanup()
    except Exception as exc:
        message = f"Warning: Vision cleanup failed: {exc}"
        if json_output or _get_state().json_output:
            typer.echo(message, err=True)
        else:
            console.print(f"[yellow]{message}[/yellow]")


def _analyze_text_file(file_path: Path, *, verbose: bool, json_output: bool) -> None:
    """Analyze a single text file with the configured text model."""
    from file_organizer.services.analyzer import (
        calculate_confidence,
        generate_category,
        generate_description,
        truncate_content,
    )

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

    _emit_analysis_result(
        description=description,
        category=category,
        confidence=confidence,
        json_output=json_output,
        verbose=verbose,
        verbose_rows=[
            ("Model", config.name),
            ("Processing time", f"{elapsed:.2f}s"),
            ("Content length", f"{content_length} chars"),
        ],
    )


def _emit_analysis_result(
    *,
    description: str,
    category: str,
    confidence: float,
    json_output: bool,
    verbose: bool,
    json_extra: dict[str, object] | None = None,
    verbose_rows: list[tuple[str, object]] | None = None,
    warning: str | None = None,
) -> None:
    """Render shared analyze output for text and image paths."""
    payload: dict[str, object] = {
        "description": description,
        "category": category,
        "confidence": confidence,
    }
    if json_extra:
        payload.update(json_extra)

    if json_output or _get_state().json_output:
        typer.echo(json_mod.dumps(payload, indent=2))
        return

    if warning:
        console.print(f"[yellow]Warning: {warning}[/yellow]")
    console.print(f"[bold]Category:[/bold] {category}")
    console.print(f"[bold]Description:[/bold] {description}")
    console.print(f"[bold]Confidence:[/bold] {confidence:.0%}")

    if verbose or _get_state().verbose:
        for label, value in verbose_rows or []:
            console.print(f"[bold]{label}:[/bold] {value}")
