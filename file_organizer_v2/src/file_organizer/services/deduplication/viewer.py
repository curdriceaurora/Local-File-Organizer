"""
Interactive comparison viewer for reviewing duplicate images.

Provides a terminal-based UI for reviewing duplicate images with:
- Side-by-side image preview
- Metadata display (dimensions, size, format, modification date)
- Interactive selection (keep/delete/skip)
- Batch review operations
- User decision recording
"""

import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from PIL import Image
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.layout import Layout
from rich import box


class UserAction(Enum):
    """User actions for duplicate handling."""
    KEEP = "keep"
    DELETE = "delete"
    SKIP = "skip"
    KEEP_ALL = "keep_all"
    DELETE_ALL = "delete_all"
    AUTO_SELECT = "auto"
    QUIT = "quit"


@dataclass
class ImageMetadata:
    """Metadata for an image file."""
    path: Path
    width: int
    height: int
    format: str
    file_size: int
    modified_time: datetime
    mode: str  # Color mode (RGB, RGBA, L, etc.)

    @property
    def resolution(self) -> int:
        """Total pixel count."""
        return self.width * self.height

    @property
    def dimensions(self) -> str:
        """Formatted dimensions string."""
        return f"{self.width}x{self.height}"

    @property
    def size_mb(self) -> float:
        """File size in MB."""
        return self.file_size / (1024 * 1024)

    @property
    def modified_str(self) -> str:
        """Formatted modification time."""
        return self.modified_time.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class DuplicateReview:
    """Result of reviewing a duplicate group."""
    files_to_keep: List[Path]
    files_to_delete: List[Path]
    skipped: bool = False


class ComparisonViewer:
    """
    Terminal-based UI for reviewing duplicate images.

    Provides interactive comparison with image previews, metadata display,
    and user decision recording.
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        preview_width: int = 40,
        preview_height: int = 20
    ):
        """
        Initialize the ComparisonViewer.

        Args:
            console: Rich console instance (creates new if None)
            preview_width: Width of ASCII preview in characters
            preview_height: Height of ASCII preview in characters
        """
        self.console = console or Console()
        self.preview_width = preview_width
        self.preview_height = preview_height
        self._terminal_width = shutil.get_terminal_size().columns

    def show_comparison(
        self,
        images: List[Path],
        similarity_score: Optional[float] = None
    ) -> DuplicateReview:
        """
        Show comparison for a group of duplicate images.

        Displays side-by-side comparison and prompts user for action.

        Args:
            images: List of duplicate image paths
            similarity_score: Similarity score if available

        Returns:
            DuplicateReview with user decisions
        """
        if not images:
            return DuplicateReview([], [], skipped=True)

        # Load metadata for all images
        metadata_list = []
        for img_path in images:
            try:
                metadata = self._get_image_metadata(img_path)
                metadata_list.append(metadata)
            except Exception as e:
                self.console.print(f"[yellow]Warning: Could not load {img_path}: {e}[/yellow]")

        if not metadata_list:
            return DuplicateReview([], [], skipped=True)

        # Display comparison
        self._display_comparison_header(len(metadata_list), similarity_score)
        self._display_images_side_by_side(metadata_list)

        # Get user action
        action = self._prompt_user_action(len(metadata_list))

        # Process action
        return self._process_user_action(action, metadata_list)

    def batch_review(
        self,
        duplicate_groups: Dict[str, List[Path]],
        auto_select_best: bool = False
    ) -> Dict[Path, str]:
        """
        Review multiple groups of duplicates in batch.

        Args:
            duplicate_groups: Dictionary mapping group IDs to lists of duplicate images
            auto_select_best: If True, automatically keep best quality

        Returns:
            Dictionary mapping file paths to actions ("keep" or "delete")
        """
        decisions: Dict[Path, str] = {}
        total_groups = len(duplicate_groups)

        self.console.print(f"\n[bold cyan]Starting batch review of {total_groups} duplicate groups[/bold cyan]\n")

        for idx, (group_id, images) in enumerate(duplicate_groups.items(), 1):
            self.console.print(f"\n[bold]Group {idx}/{total_groups}[/bold] (ID: {group_id[:8]}...)")
            self.console.rule()

            if auto_select_best:
                # Automatic selection of best quality
                review = self._auto_select_best(images)
            else:
                # Manual review
                review = self.show_comparison(images)

            # Record decisions
            for path in review.files_to_keep:
                decisions[path] = "keep"

            for path in review.files_to_delete:
                decisions[path] = "delete"

            # Check if user wants to quit
            if review.skipped and idx < total_groups:
                if not Confirm.ask("[yellow]Continue to next group?[/yellow]", default=True):
                    break

        # Display summary
        self._display_review_summary(decisions)

        return decisions

    def _get_image_metadata(self, image_path: Path) -> ImageMetadata:
        """
        Extract metadata from an image file.

        Args:
            image_path: Path to image file

        Returns:
            ImageMetadata object

        Raises:
            Exception: If image cannot be loaded
        """
        with Image.open(image_path) as img:
            width, height = img.size
            img_format = img.format or "UNKNOWN"
            mode = img.mode

        stat = image_path.stat()

        return ImageMetadata(
            path=image_path,
            width=width,
            height=height,
            format=img_format,
            file_size=stat.st_size,
            modified_time=datetime.fromtimestamp(stat.st_mtime),
            mode=mode
        )

    def _display_comparison_header(
        self,
        image_count: int,
        similarity_score: Optional[float] = None
    ) -> None:
        """Display header for comparison."""
        header_text = f"Comparing {image_count} duplicate images"
        if similarity_score is not None:
            header_text += f" (Similarity: {similarity_score:.1f}%)"

        self.console.print(Panel(
            header_text,
            style="bold cyan",
            box=box.DOUBLE
        ))

    def _display_images_side_by_side(
        self,
        metadata_list: List[ImageMetadata]
    ) -> None:
        """
        Display images side by side with metadata.

        Args:
            metadata_list: List of ImageMetadata objects
        """
        # Create tables for each image
        tables = []

        for idx, metadata in enumerate(metadata_list, 1):
            table = self._create_image_info_table(idx, metadata)
            tables.append(table)

        # Display in columns if terminal is wide enough
        if self._terminal_width >= 120 and len(metadata_list) <= 2:
            self.console.print(Columns(tables, equal=True, expand=True))
        else:
            # Stack vertically for narrow terminals or many images
            for table in tables:
                self.console.print(table)
                self.console.print()

    def _create_image_info_table(
        self,
        index: int,
        metadata: ImageMetadata
    ) -> Table:
        """
        Create a table displaying image information.

        Args:
            index: Image number in comparison
            metadata: ImageMetadata object

        Returns:
            Rich Table with image info
        """
        table = Table(
            title=f"[bold]Image {index}[/bold]",
            box=box.ROUNDED,
            show_header=False,
            title_style="bold cyan"
        )

        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        # Add metadata rows
        table.add_row("File Name", metadata.path.name)
        table.add_row("Dimensions", metadata.dimensions)
        table.add_row("Resolution", f"{metadata.resolution:,} pixels")
        table.add_row("Format", metadata.format)
        table.add_row("Color Mode", metadata.mode)
        table.add_row("File Size", f"{metadata.size_mb:.2f} MB ({metadata.file_size:,} bytes)")
        table.add_row("Modified", metadata.modified_str)
        table.add_row("Full Path", str(metadata.path))

        # Add ASCII preview if terminal supports it
        preview = self._generate_ascii_preview(metadata.path)
        if preview:
            table.add_row("Preview", preview)

        return table

    def _generate_ascii_preview(
        self,
        image_path: Path,
        max_width: int = 40,
        max_height: int = 15
    ) -> Optional[str]:
        """
        Generate ASCII art preview of image.

        Args:
            image_path: Path to image
            max_width: Maximum width in characters
            max_height: Maximum height in characters

        Returns:
            ASCII art string or None if preview fails
        """
        try:
            with Image.open(image_path) as img:
                # Convert to grayscale
                img = img.convert('L')

                # Calculate aspect ratio preserving dimensions
                aspect_ratio = img.width / img.height
                if aspect_ratio > 1:
                    new_width = max_width
                    new_height = int(max_width / aspect_ratio / 2)  # /2 for character aspect ratio
                else:
                    new_height = max_height
                    new_width = int(max_height * aspect_ratio * 2)

                # Resize
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Convert to ASCII
                ascii_chars = ' .:-=+*#%@'
                pixels = img.getdata()

                ascii_lines = []
                for i in range(0, len(pixels), new_width):
                    row = pixels[i:i + new_width]
                    ascii_row = ''.join(ascii_chars[min(p * len(ascii_chars) // 256, len(ascii_chars) - 1)] for p in row)
                    ascii_lines.append(ascii_row)

                return '\n'.join(ascii_lines)

        except Exception:
            return None

    def _prompt_user_action(self, image_count: int) -> UserAction:
        """
        Prompt user for action on duplicate group.

        Args:
            image_count: Number of images in group

        Returns:
            UserAction enum value
        """
        self.console.print("\n[bold yellow]Choose an action:[/bold yellow]")
        self.console.print("  [1-9] - Keep image number N (delete others)")
        self.console.print("  [a]   - Auto-select best quality")
        self.console.print("  [s]   - Skip this group")
        self.console.print("  [k]   - Keep all images")
        self.console.print("  [d]   - Delete all images")
        self.console.print("  [q]   - Quit review")

        while True:
            choice = Prompt.ask(
                "\nYour choice",
                default="a"
            ).lower().strip()

            # Parse choice
            if choice == 'a':
                return UserAction.AUTO_SELECT
            elif choice == 's':
                return UserAction.SKIP
            elif choice == 'k':
                return UserAction.KEEP_ALL
            elif choice == 'd':
                return UserAction.DELETE_ALL
            elif choice == 'q':
                return UserAction.QUIT
            elif choice.isdigit():
                image_num = int(choice)
                if 1 <= image_num <= image_count:
                    # Store image number in the action (using value)
                    return UserAction.KEEP  # Will handle index separately
                else:
                    self.console.print(f"[red]Invalid image number. Choose 1-{image_count}[/red]")
            else:
                self.console.print("[red]Invalid choice. Please try again.[/red]")

    def _process_user_action(
        self,
        action: UserAction,
        metadata_list: List[ImageMetadata]
    ) -> DuplicateReview:
        """
        Process user action and return review result.

        Args:
            action: UserAction enum value
            metadata_list: List of ImageMetadata

        Returns:
            DuplicateReview with decisions
        """
        all_paths = [m.path for m in metadata_list]

        if action == UserAction.SKIP or action == UserAction.QUIT:
            return DuplicateReview([], [], skipped=True)

        elif action == UserAction.KEEP_ALL:
            return DuplicateReview(all_paths, [])

        elif action == UserAction.DELETE_ALL:
            if Confirm.ask("[bold red]Are you sure you want to delete ALL images?[/bold red]", default=False):
                return DuplicateReview([], all_paths)
            else:
                return DuplicateReview([], [], skipped=True)

        elif action == UserAction.AUTO_SELECT:
            return self._auto_select_best([m.path for m in metadata_list])

        elif action == UserAction.KEEP:
            # Prompt for which image to keep
            choice = Prompt.ask(
                "Which image to keep? (1-" + str(len(metadata_list)) + ")",
                default="1"
            )

            try:
                keep_idx = int(choice) - 1
                if 0 <= keep_idx < len(metadata_list):
                    keep_path = metadata_list[keep_idx].path
                    delete_paths = [m.path for m in metadata_list if m.path != keep_path]
                    return DuplicateReview([keep_path], delete_paths)
            except ValueError:
                pass

            # Invalid choice, skip
            self.console.print("[red]Invalid choice, skipping group[/red]")
            return DuplicateReview([], [], skipped=True)

        return DuplicateReview([], [], skipped=True)

    def _auto_select_best(self, images: List[Path]) -> DuplicateReview:
        """
        Automatically select the best quality image.

        Chooses based on:
        1. Highest resolution
        2. Largest file size (if resolution is same)
        3. Preferred format (PNG > JPEG > others)

        Args:
            images: List of image paths

        Returns:
            DuplicateReview with best image kept, others marked for deletion
        """
        try:
            metadata_list = [self._get_image_metadata(img) for img in images]
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not auto-select: {e}[/yellow]")
            return DuplicateReview([], [], skipped=True)

        # Score each image
        scored = []
        for metadata in metadata_list:
            score = self._calculate_quality_score(metadata)
            scored.append((score, metadata))

        # Sort by score (highest first)
        scored.sort(key=lambda x: x[0], reverse=True)

        # Best image
        best_metadata = scored[0][1]

        # Display selection
        self.console.print(f"\n[green]Auto-selected best quality:[/green] {best_metadata.path.name}")
        self.console.print(f"  Resolution: {best_metadata.dimensions}, Size: {best_metadata.size_mb:.2f} MB")

        # Keep best, delete others
        keep_path = best_metadata.path
        delete_paths = [m.path for _, m in scored if m.path != keep_path]

        return DuplicateReview([keep_path], delete_paths)

    def _calculate_quality_score(self, metadata: ImageMetadata) -> float:
        """
        Calculate quality score for an image.

        Args:
            metadata: ImageMetadata object

        Returns:
            Quality score (higher is better)
        """
        # Resolution score (primary factor)
        resolution_score = metadata.resolution

        # File size score (normalized to MB, secondary factor)
        size_score = metadata.size_mb * 1000  # Scale to be comparable to resolution

        # Format preference score
        format_scores = {
            'PNG': 1.2,
            'TIFF': 1.1,
            'JPEG': 1.0,
            'JPG': 1.0,
            'WEBP': 0.9,
            'GIF': 0.8,
            'BMP': 0.7
        }
        format_score = format_scores.get(metadata.format.upper(), 0.5)

        # Combined score
        total_score = (resolution_score * 0.7 + size_score * 0.2) * format_score

        return total_score

    def _display_review_summary(self, decisions: Dict[Path, str]) -> None:
        """
        Display summary of review decisions.

        Args:
            decisions: Dictionary mapping paths to actions
        """
        keep_count = sum(1 for action in decisions.values() if action == "keep")
        delete_count = sum(1 for action in decisions.values() if action == "delete")

        table = Table(title="[bold cyan]Review Summary[/bold cyan]", box=box.ROUNDED)
        table.add_column("Action", style="cyan", no_wrap=True)
        table.add_column("Count", style="white", justify="right")

        table.add_row("Files to Keep", str(keep_count))
        table.add_row("Files to Delete", str(delete_count))
        table.add_row("Total Reviewed", str(len(decisions)))

        self.console.print("\n")
        self.console.print(table)

        # Calculate space savings
        delete_size = sum(
            path.stat().st_size
            for path, action in decisions.items()
            if action == "delete" and path.exists()
        )

        if delete_size > 0:
            delete_size_mb = delete_size / (1024 * 1024)
            self.console.print(f"\n[green]Potential space savings: {delete_size_mb:.2f} MB[/green]")

    def display_metadata(self, image_path: Path) -> None:
        """
        Display metadata for a single image.

        Args:
            image_path: Path to image file
        """
        try:
            metadata = self._get_image_metadata(image_path)
            table = self._create_image_info_table(1, metadata)
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]Error loading image metadata: {e}[/red]")

    def interactive_select(
        self,
        images: List[Path],
        prompt: str = "Select images to keep"
    ) -> List[Path]:
        """
        Interactive selection of images from a list.

        Args:
            images: List of image paths
            prompt: Prompt text for selection

        Returns:
            List of selected image paths
        """
        if not images:
            return []

        self.console.print(f"\n[bold cyan]{prompt}[/bold cyan]")

        # Display all images with numbers
        for idx, img_path in enumerate(images, 1):
            try:
                metadata = self._get_image_metadata(img_path)
                self.console.print(
                    f"  [{idx}] {metadata.path.name} "
                    f"({metadata.dimensions}, {metadata.size_mb:.2f} MB)"
                )
            except Exception:
                self.console.print(f"  [{idx}] {img_path.name} (could not load)")

        # Get selection
        self.console.print("\n[yellow]Enter image numbers to keep (comma-separated, e.g., '1,3,5'):[/yellow]")
        self.console.print("[yellow]Or 'all' to keep all, 'none' to keep none[/yellow]")

        choice = Prompt.ask("Your selection", default="all").lower().strip()

        if choice == 'all':
            return images
        elif choice == 'none':
            return []
        else:
            selected = []
            for num_str in choice.split(','):
                try:
                    num = int(num_str.strip())
                    if 1 <= num <= len(images):
                        selected.append(images[num - 1])
                except ValueError:
                    continue

            return selected
