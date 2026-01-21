#!/usr/bin/env python3
"""
Demo script for ComparisonViewer.

This script demonstrates the terminal-based UI for reviewing duplicate images.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from file_organizer.services.deduplication.viewer import ComparisonViewer
from rich.console import Console


def demo_single_comparison():
    """Demo showing comparison of a few duplicate images."""
    console = Console()
    viewer = ComparisonViewer(console=console)

    console.print("\n[bold cyan]Demo: Single Group Comparison[/bold cyan]\n")
    console.print("This would display a group of duplicate images for review.")
    console.print("Features:")
    console.print("  • ASCII art preview of images")
    console.print("  • Metadata display (dimensions, size, format, date)")
    console.print("  • Interactive selection (keep/delete/skip)")
    console.print("  • Automatic best quality selection")
    console.print()

    # In a real scenario, you would have actual image paths:
    # images = [
    #     Path("/path/to/photo1.jpg"),
    #     Path("/path/to/photo1_resized.jpg"),
    #     Path("/path/to/photo1_copy.jpg"),
    # ]
    # review = viewer.show_comparison(images, similarity_score=95.5)
    #
    # Then process the results:
    # for path in review.files_to_delete:
    #     print(f"Would delete: {path}")


def demo_batch_review():
    """Demo showing batch review of multiple duplicate groups."""
    console = Console()
    viewer = ComparisonViewer(console=console)

    console.print("\n[bold cyan]Demo: Batch Review[/bold cyan]\n")
    console.print("This would review multiple groups of duplicates in sequence.")
    console.print("Features:")
    console.print("  • Review all duplicate groups one by one")
    console.print("  • Auto-select best quality option")
    console.print("  • Summary with space savings calculation")
    console.print("  • Skip or quit at any time")
    console.print()

    # In a real scenario:
    # duplicate_groups = {
    #     "hash1": [Path("img1.jpg"), Path("img1_copy.jpg")],
    #     "hash2": [Path("img2.png"), Path("img2_resized.png")],
    #     "hash3": [Path("img3.gif"), Path("img3_converted.gif")],
    # }
    # decisions = viewer.batch_review(duplicate_groups, auto_select_best=False)
    #
    # Then execute the decisions:
    # for path, action in decisions.items():
    #     if action == "delete":
    #         print(f"Would delete: {path}")


def demo_metadata_display():
    """Demo showing single image metadata display."""
    console = Console()
    viewer = ComparisonViewer(console=console)

    console.print("\n[bold cyan]Demo: Metadata Display[/bold cyan]\n")
    console.print("This would display detailed metadata for a single image.")
    console.print("Includes:")
    console.print("  • File name and path")
    console.print("  • Dimensions and resolution")
    console.print("  • Format and color mode")
    console.print("  • File size")
    console.print("  • Modification date")
    console.print("  • ASCII art preview")
    console.print()

    # In a real scenario:
    # image_path = Path("/path/to/image.jpg")
    # viewer.display_metadata(image_path)


def demo_interactive_select():
    """Demo showing interactive multi-select interface."""
    console = Console()
    viewer = ComparisonViewer(console=console)

    console.print("\n[bold cyan]Demo: Interactive Selection[/bold cyan]\n")
    console.print("This would let you select multiple images to keep from a list.")
    console.print("Features:")
    console.print("  • Display all images with numbers")
    console.print("  • Comma-separated selection (e.g., '1,3,5')")
    console.print("  • 'all' to keep all images")
    console.print("  • 'none' to keep no images")
    console.print()

    # In a real scenario:
    # images = [Path(f"photo{i}.jpg") for i in range(1, 6)]
    # selected = viewer.interactive_select(images, prompt="Select photos to keep")
    # print(f"You selected: {selected}")


def demo_quality_scoring():
    """Demo explaining the quality scoring algorithm."""
    console = Console()

    console.print("\n[bold cyan]Demo: Quality Scoring Algorithm[/bold cyan]\n")
    console.print("When auto-selecting the best quality image, the viewer uses:")
    console.print()
    console.print("[yellow]Score = (Resolution × 0.7 + FileSize × 0.2) × FormatWeight[/yellow]")
    console.print()
    console.print("Where:")
    console.print("  • Resolution = width × height (in pixels)")
    console.print("  • FileSize = size in MB × 1000 (normalized)")
    console.print("  • FormatWeight = format preference multiplier")
    console.print()
    console.print("Format Preferences (higher is better):")
    console.print("  • PNG:  1.2 (lossless, high quality)")
    console.print("  • TIFF: 1.1 (lossless, professional)")
    console.print("  • JPEG: 1.0 (standard, widely supported)")
    console.print("  • WebP: 0.9 (modern, efficient)")
    console.print("  • GIF:  0.8 (limited colors)")
    console.print("  • BMP:  0.7 (uncompressed, large)")
    console.print()


def main():
    """Run all demos."""
    console = Console()

    console.print("[bold green]ComparisonViewer Demo[/bold green]")
    console.print("=" * 60)

    demos = [
        ("Single Comparison", demo_single_comparison),
        ("Batch Review", demo_batch_review),
        ("Metadata Display", demo_metadata_display),
        ("Interactive Selection", demo_interactive_select),
        ("Quality Scoring", demo_quality_scoring),
    ]

    for i, (name, demo_func) in enumerate(demos, 1):
        console.print(f"\n[bold]Demo {i}/{len(demos)}: {name}[/bold]")
        demo_func()

    console.print("\n" + "=" * 60)
    console.print("[bold green]All demos completed![/bold green]")
    console.print("\n[yellow]To use with real images:[/yellow]")
    console.print("1. Run image deduplication to find duplicates")
    console.print("2. Pass the duplicate groups to viewer.batch_review()")
    console.print("3. Review each group interactively")
    console.print("4. Execute the deletion decisions")


if __name__ == "__main__":
    main()
