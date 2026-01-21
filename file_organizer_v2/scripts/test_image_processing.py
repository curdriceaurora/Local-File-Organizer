#!/usr/bin/env python3
"""Test image processing with sample images."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from file_organizer.services import VisionProcessor
from loguru import logger
from rich.console import Console

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")

console = Console()


def test_image_processing():
    """Test processing a sample image."""
    image_path = Path("demo_images/mountain_landscape.jpg")

    if not image_path.exists():
        console.print(f"[red]Error: {image_path} not found![/red]")
        console.print("[yellow]Run: python3 scripts/create_sample_images.py[/yellow]")
        return False

    try:
        console.print("\n[bold blue]Testing Image Processing[/bold blue]\n")
        console.print(f"Image: {image_path}\n")

        # Initialize processor
        console.print("1. Initializing VisionProcessor...")
        processor = VisionProcessor()
        processor.initialize()
        console.print("   [green]✓[/green] Initialized\n")

        # Process image
        console.print("2. Processing image...")
        result = processor.process_file(image_path)

        # Show results
        console.print("\n[bold green]Results:[/bold green]")
        console.print(f"  Folder: [cyan]{result.folder_name}[/cyan]")
        console.print(f"  Filename: [cyan]{result.filename}[/cyan]")
        console.print(f"  Description: {result.description[:200]}...")
        if result.has_text:
            console.print(f"  Extracted Text: {result.extracted_text[:100]}...")
        console.print(f"  Processing Time: {result.processing_time:.2f}s")

        if result.error:
            console.print(f"  [red]Error: {result.error}[/red]")

        # Cleanup
        processor.cleanup()

        console.print("\n[bold green]✓ Test completed successfully![/bold green]\n")
        return True

    except Exception as e:
        console.print(f"\n[red]✗ Test failed: {e}[/red]")
        logger.exception("Test failed")
        return False


if __name__ == "__main__":
    success = test_image_processing()
    sys.exit(0 if success else 1)
