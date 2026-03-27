"""Doctor command for detecting file types and recommending optional dependencies.

This module provides functionality to scan directories for file types and recommend
which optional dependency groups should be installed based on detected file types.
"""

import importlib.util
import subprocess
from pathlib import Path
from typing import Dict, List, Set

import typer
from rich.console import Console
from rich.table import Table

import file_organizer.cli._globals as _g
from file_organizer.cli.interactive import confirm_action
from file_organizer.utils import is_hidden

console = Console()

# Extension-to-group registry mapping file extensions to optional dependency groups
EXTENSION_REGISTRY: Dict[str, str] = {
    # Audio files
    ".mp3": "audio",
    ".wav": "audio",
    ".flac": "audio",
    ".ogg": "audio",
    ".m4a": "audio",
    ".wma": "audio",
    ".aac": "audio",
    ".opus": "audio",
    # Video files
    ".mp4": "video",
    ".avi": "video",
    ".mkv": "video",
    ".mov": "video",
    ".wmv": "video",
    ".webm": "video",
    # Document parsers
    ".pdf": "parsers",
    ".docx": "parsers",
    ".xlsx": "parsers",
    ".pptx": "parsers",
    ".epub": "parsers",
    ".html": "parsers",
    # Archive files
    ".7z": "archive",
    ".rar": "archive",
    # Scientific data files
    ".hdf5": "scientific",
    ".h5": "scientific",
    ".nc": "scientific",
    ".mat": "scientific",
    # CAD files
    ".dxf": "cad",
    ".dwg": "cad",
}

# Dependency check packages - maps groups to representative packages to check
DEPENDENCY_CHECK_PACKAGES: Dict[str, str] = {
    "audio": "faster_whisper",
    "video": "cv2",
    "parsers": "fitz",
    "archive": "py7zr",
    "scientific": "h5py",
    "cad": "ezdxf",
    "dedup": "imagededup",
}

# System prerequisites for optional groups
SYSTEM_PREREQUISITES: Dict[str, List[str]] = {
    "audio": ["FFmpeg (required)", "CUDA GPU (optional, for acceleration)"],
    "archive": ["unrar tool (required for RAR files)"],
}


def is_group_installed(group: str) -> bool:
    """Check if an optional dependency group is installed.

    Uses importlib.util.find_spec() for non-destructive checking.

    Args:
        group: The name of the optional dependency group

    Returns:
        True if the group's representative package is installed, False otherwise
    """
    package_name = DEPENDENCY_CHECK_PACKAGES.get(group)
    if not package_name:
        return False

    spec = importlib.util.find_spec(package_name)
    return spec is not None


def get_groups_for_extensions(extensions: Set[str]) -> Set[str]:
    """Get the set of dependency groups needed for the given file extensions.

    Args:
        extensions: Set of file extensions (with leading dot, e.g., '.mp3')

    Returns:
        Set of dependency group names
    """
    groups = set()
    for ext in extensions:
        # Normalize extension to lowercase
        ext_lower = ext.lower()
        if ext_lower in EXTENSION_REGISTRY:
            groups.add(EXTENSION_REGISTRY[ext_lower])
    return groups


def get_missing_groups(detected_groups: Set[str]) -> Set[str]:
    """Filter detected groups to only those not already installed.

    Args:
        detected_groups: Set of detected dependency group names

    Returns:
        Set of group names that are not installed
    """
    return {group for group in detected_groups if not is_group_installed(group)}


def _normalized_extension(path: Path) -> str:
    """Return a normalized extension, preserving supported compound archives.

    Args:
        path: File path

    Returns:
        Normalized extension with leading dot, or empty string if no extension
    """
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if len(suffixes) >= 2:
        compound = "".join(suffixes[-2:])
        if compound in {".tar.gz", ".tar.bz2"}:
            return compound
    return suffixes[-1] if suffixes else ""


def scan_directory(directory: Path) -> Dict[str, int]:
    """Scan a directory and count files by extension.

    Args:
        directory: Path to directory to scan

    Returns:
        Dictionary mapping file extensions to counts
    """
    extension_counts: Dict[str, int] = {}

    # Recursively iterate through all files
    for item in directory.rglob("*"):
        # Skip hidden files and directories
        if is_hidden(item):
            continue

        # Only count files, not directories
        if item.is_file():
            ext = _normalized_extension(item)
            # Count files with extensions and those without
            if ext:
                extension_counts[ext] = extension_counts.get(ext, 0) + 1
            else:
                # Track files without extensions
                extension_counts[""] = extension_counts.get("", 0) + 1

    return extension_counts


def display_recommendations(
    extension_counts: Dict[str, int],
    detected_groups: Set[str],
) -> None:
    """Display recommendations for optional dependencies using Rich tables.

    Args:
        extension_counts: Dictionary mapping extensions to file counts
        detected_groups: Set of detected dependency groups
    """
    # Calculate file counts per group
    group_file_counts: Dict[str, int] = {}
    for ext, count in extension_counts.items():
        if ext in EXTENSION_REGISTRY:
            group = EXTENSION_REGISTRY[ext]
            group_file_counts[group] = group_file_counts.get(group, 0) + count

    # Create and configure the table
    table = Table(title="Optional Dependency Recommendations")
    table.add_column("Group", style="cyan", no_wrap=True)
    table.add_column("Files Found", justify="right")
    table.add_column("Install Command", no_wrap=True)
    table.add_column("Prerequisites")

    # Add rows for each detected group, sorted by name for consistency
    for group in sorted(detected_groups):
        file_count = group_file_counts.get(group, 0)
        # Escape square brackets for Rich markup
        install_cmd = f"pip install file-organizer\\[{group}]"
        prerequisites = ", ".join(SYSTEM_PREREQUISITES.get(group, ["-"]))

        # Check if group is already installed
        is_installed = is_group_installed(group)

        # Color code based on installation status
        if is_installed:
            # Green for installed
            group_name = f"[green]{group} ✓[/green]"
            status_style = "dim"
        else:
            # Yellow for recommended (not installed)
            group_name = f"[yellow]{group}[/yellow]"
            status_style = ""

        table.add_row(
            group_name,
            f"{file_count}" if not is_installed else f"[dim]{file_count}[/dim]",
            f"[{status_style}]{install_cmd}[/{status_style}]" if status_style else install_cmd,
            f"[{status_style}]{prerequisites}[/{status_style}]" if status_style else prerequisites,
        )

    console.print(table)


def install_groups(groups: Set[str]) -> None:
    """Interactively install optional dependency groups using pip.

    Prompts the user for confirmation before installing each group.
    Respects the --dry-run flag to skip actual installation.
    Handles subprocess failures gracefully and continues with remaining groups.

    Args:
        groups: Set of dependency group names to install
    """
    if not groups:
        console.print("[yellow]No groups to install.[/yellow]")
        return

    # Display groups to be installed
    groups_list = sorted(groups)
    console.print(f"\n[bold]Recommended groups to install:[/bold] {', '.join(groups_list)}")

    # Show system prerequisites if any
    has_prerequisites = False
    for group in groups_list:
        if group in SYSTEM_PREREQUISITES:
            if not has_prerequisites:
                console.print("\n[bold yellow]System Prerequisites:[/bold yellow]")
                has_prerequisites = True
            prereqs = ", ".join(SYSTEM_PREREQUISITES[group])
            console.print(f"  • {group}: {prereqs}")

    if has_prerequisites:
        console.print()

    # Ask for confirmation
    if not confirm_action(
        f"Install {len(groups_list)} optional dependency group(s)?",
        default=False,
    ):
        console.print("[yellow]Installation cancelled.[/yellow]")
        return

    # Dry-run mode: skip actual installation
    if _g.dry_run:
        console.print("[yellow]Dry-run mode: skipping actual installation.[/yellow]")
        for group in groups_list:
            console.print(f"  [dim]Would install: file-organizer[{group}][/dim]")
        return

    # Install each group
    failed_groups: List[str] = []
    for group in groups_list:
        install_cmd = ["pip", "install", f"file-organizer[{group}]"]
        console.print(f"\n[bold]Installing {group}...[/bold]")

        try:
            result = subprocess.run(
                install_cmd,
                check=False,
                capture_output=False,
                text=True,
            )

            if result.returncode == 0:
                console.print(f"[green]✓ Successfully installed {group}[/green]")
            else:
                console.print(f"[red]✗ Failed to install {group} (exit code {result.returncode})[/red]")
                failed_groups.append(group)

        except Exception as exc:
            console.print(f"[red]✗ Error installing {group}: {exc}[/red]")
            failed_groups.append(group)

    # Summary
    console.print()
    if failed_groups:
        console.print(
            f"[yellow]Installation completed with errors. "
            f"Failed groups: {', '.join(failed_groups)}[/yellow]"
        )
        console.print("\n[dim]You can retry failed installations manually:[/dim]")
        for group in failed_groups:
            console.print(f"  [dim]pip install file-organizer[{group}][/dim]")
    else:
        console.print(f"[green]✓ All {len(groups_list)} group(s) installed successfully![/green]")


def doctor(
    path: Path = typer.Argument(
        ...,
        help="Directory path to scan for file types.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    install: bool = typer.Option(
        False,
        "--install",
        help="Automatically install recommended dependency groups.",
    ),
) -> None:
    """Scan directory for file types and recommend optional dependencies.

    Detects file types in the specified directory and recommends which optional
    dependency groups should be installed to support those file types.
    """
    console.print(f"\n[bold]Scanning directory:[/bold] {path}")

    # Scan the directory
    extension_counts = scan_directory(path)

    if not extension_counts:
        console.print("[yellow]No files found in directory.[/yellow]")
        raise typer.Exit(code=0)

    # Get the set of extensions
    extensions = set(extension_counts.keys())

    # Determine which groups are needed
    detected_groups = get_groups_for_extensions(extensions)

    if not detected_groups:
        console.print(
            "\n[green]No optional dependencies needed for detected file types.[/green]"
        )
        raise typer.Exit(code=0)

    # Display recommendations
    console.print()
    display_recommendations(extension_counts, detected_groups)

    # Check which groups are missing
    missing_groups = get_missing_groups(detected_groups)

    if not missing_groups:
        console.print(
            "\n[green]✓ All recommended dependency groups are already installed![/green]"
        )
        raise typer.Exit(code=0)

    # Install if requested
    if install:
        install_groups(missing_groups)
    else:
        # Show summary of what's missing
        console.print(
            f"\n[yellow]Found {len(missing_groups)} missing dependency group(s).[/yellow]"
        )
        console.print(
            "[dim]Run with --install flag to install them automatically.[/dim]"
        )
