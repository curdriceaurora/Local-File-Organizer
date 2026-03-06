"""Main file organizer orchestrator."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from loguru import logger
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from file_organizer.history.models import OperationType
from file_organizer.models import TextModel, VisionModel
from file_organizer.models.base import ModelConfig
from file_organizer.parallel.config import ExecutorType, ParallelConfig
from file_organizer.parallel.processor import ParallelProcessor
from file_organizer.services import ProcessedFile, ProcessedImage, TextProcessor, VisionProcessor
from file_organizer.services.audio.classifier import AudioClassifier
from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor
from file_organizer.services.audio.organizer import AudioOrganizer
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor
from file_organizer.services.video.organizer import VideoOrganizer
from file_organizer.undo import UndoManager


@dataclass
class OrganizationResult:
    """Result of organizing files."""

    total_files: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    processing_time: float = 0.0
    organized_structure: dict[str, list[str]] = field(default_factory=dict)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (file, error)


class FileOrganizer:
    """Main file organizer that orchestrates the entire process.

    This class:
    - Scans directories for files
    - Processes text-based files (PDF, DOCX, TXT, etc.)
    - Organizes files into folder structure
    - Handles errors gracefully
    - Provides progress feedback
    """

    # Supported file extensions
    TEXT_EXTENSIONS: ClassVar[set[str]] = {
        ".txt",
        ".md",
        ".docx",
        ".doc",
        ".pdf",
        ".csv",
        ".xlsx",
        ".xls",
        ".ppt",
        ".pptx",
        ".epub",
    }
    IMAGE_EXTENSIONS: ClassVar[set[str]] = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}
    VIDEO_EXTENSIONS: ClassVar[set[str]] = {".mp4", ".avi", ".mkv", ".mov", ".wmv"}
    AUDIO_EXTENSIONS: ClassVar[set[str]] = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
    CAD_EXTENSIONS: ClassVar[set[str]] = {".dwg", ".dxf", ".step", ".stp", ".iges", ".igs"}

    def __init__(
        self,
        text_model_config: ModelConfig | None = None,
        vision_model_config: ModelConfig | None = None,
        dry_run: bool = True,
        use_hardlinks: bool = True,
        parallel_workers: int | None = None,
    ) -> None:
        """Initialize file organizer.

        Args:
            text_model_config: Configuration for text model (optional)
            vision_model_config: Configuration for vision model (optional)
            dry_run: If True, only simulate operations
            use_hardlinks: If True, create hardlinks instead of copying
            parallel_workers: Number of parallel workers (default: None = auto)
        """
        self.text_model_config = text_model_config or TextModel.get_default_config()
        self.vision_model_config = vision_model_config or VisionModel.get_default_config()
        self.dry_run = dry_run
        self.use_hardlinks = use_hardlinks
        self.console = Console()
        self.text_processor: TextProcessor | None = None
        self.vision_processor: VisionProcessor | None = None

        # Initialize parallel processor
        self.parallel_config = ParallelConfig(
            max_workers=parallel_workers,
            executor_type=ExecutorType.THREAD,  # IO-bound (Ollama HTTP calls)
            timeout_per_file=60.0,
            retry_count=1,
        )
        self.parallel_processor = ParallelProcessor(self.parallel_config)

        # Undo/redo support (lazy-initialized on first non-dry-run organize call)
        self._undo_manager: UndoManager | None = None
        self._last_transaction_id: str | None = None
        self._last_output_path: Path | None = None

        logger.info(f"FileOrganizer initialized (dry_run={dry_run}, parallel={parallel_workers})")

    def organize(
        self,
        input_path: str | Path,
        output_path: str | Path,
        skip_existing: bool = True,
    ) -> OrganizationResult:
        """Organize files from input directory to output directory.

        Args:
            input_path: Path to directory with files to organize
            output_path: Path to output directory
            skip_existing: Skip files that already exist in output

        Returns:
            OrganizationResult with statistics and structure
        """
        import time

        start_time = time.time()
        input_path = Path(input_path)
        output_path = Path(output_path)

        # Validate paths
        if not input_path.exists():
            raise ValueError(f"Input path does not exist: {input_path}")

        # Collect files
        self.console.print(f"\n[bold blue]Scanning:[/bold blue] {input_path}")
        files = self._collect_files(input_path)

        result = OrganizationResult(total_files=len(files))

        if not files:
            self.console.print("[yellow]No files found to organize[/yellow]")
            return result

        # Categorize files by type
        text_files = [f for f in files if f.suffix.lower() in self.TEXT_EXTENSIONS]
        image_files = [f for f in files if f.suffix.lower() in self.IMAGE_EXTENSIONS]
        video_files = [f for f in files if f.suffix.lower() in self.VIDEO_EXTENSIONS]
        audio_files = [f for f in files if f.suffix.lower() in self.AUDIO_EXTENSIONS]
        cad_files = [f for f in files if f.suffix.lower() in self.CAD_EXTENSIONS]
        other_files = [
            f
            for f in files
            if f not in text_files + image_files + video_files + audio_files + cad_files
        ]

        # Show file type breakdown
        self._show_file_breakdown(
            text_files, image_files, video_files, audio_files, cad_files, other_files
        )

        # Initialize models
        self.console.print("\n[bold blue]Initializing AI models...[/bold blue]")

        # Initialize text processor for text and CAD files
        if text_files or cad_files:
            self.text_processor = TextProcessor(config=self.text_model_config)
            self.text_processor.initialize()
            self.console.print("[green]✓[/green] Text model ready")

        # Initialize vision processor for image files only (video uses metadata now)
        if image_files:
            self.vision_processor = VisionProcessor(config=self.vision_model_config)
            self.vision_processor.initialize()
            self.console.print("[green]✓[/green] Vision model ready")

        # Process text files
        all_processed = []
        if text_files:
            self.console.print(
                f"\n[bold blue]Processing {len(text_files)} text files...[/bold blue]"
            )
            processed_text = self._process_text_files(text_files)
            all_processed.extend(processed_text)

        # Process CAD files (treat as text files - extract metadata)
        if cad_files:
            self.console.print(f"\n[bold blue]Processing {len(cad_files)} CAD files...[/bold blue]")
            processed_cad = self._process_text_files(cad_files)
            all_processed.extend(processed_cad)

        # Process image files
        if image_files:
            self.console.print(f"\n[bold blue]Processing {len(image_files)} images...[/bold blue]")
            processed_images = self._process_image_files(image_files)
            all_processed.extend(processed_images)

        # Process audio files via metadata pipeline (no AI model required)
        if audio_files:
            self.console.print(
                f"\n[bold blue]Processing {len(audio_files)} audio files...[/bold blue]"
            )
            processed_audio = self._process_audio_files(audio_files)
            all_processed.extend(processed_audio)

        # Process video files via metadata pipeline (no AI model required)
        if video_files:
            self.console.print(f"\n[bold blue]Processing {len(video_files)} videos...[/bold blue]")
            processed_videos = self._process_video_files(video_files)
            all_processed.extend(processed_videos)

        # Organize all files
        if all_processed:
            # Calculate statistics
            failed_cnt = len([p for p in all_processed if p.error])
            success_cnt = len(all_processed) - failed_cnt
            result.processed_files = success_cnt
            result.failed_files = failed_cnt

            if not self.dry_run:
                self.console.print("\n[bold blue]Organizing files...[/bold blue]")
                # Initialize undo manager and start a transaction for this organize session
                if self._undo_manager is None:
                    self._undo_manager = UndoManager()
                self._last_transaction_id = self._undo_manager.history.start_transaction(
                    metadata={"input_path": str(input_path), "output_path": str(output_path)}
                )
                self._last_output_path = output_path

                try:
                    organized = self._organize_files(all_processed, output_path, skip_existing)
                except Exception:
                    logger.exception(
                        "Error while organizing files; leaving transaction {} uncommitted",
                        self._last_transaction_id,
                    )
                    raise
                else:
                    # Commit the transaction so it's undoable
                    self._undo_manager.history.commit_transaction(self._last_transaction_id)
                    result.organized_structure = organized
            else:
                self.console.print(
                    "\n[bold yellow]DRY RUN - Simulating organization...[/bold yellow]"
                )
                simulated = self._simulate_organization(all_processed, output_path)
                result.organized_structure = simulated

        # Handle unsupported files (audio and video are now processed above)
        if other_files:
            result.skipped_files = len(other_files)
            self.console.print("\n[bold yellow]Skipped Files:[/bold yellow]")
            for f in other_files:
                self.console.print(f"  [yellow]•[/yellow] {f.name} (unsupported type)")
            self.console.print("\n  [dim]These file types are not yet supported[/dim]")

        # Cleanup
        if self.text_processor:
            self.text_processor.cleanup()
        if self.vision_processor:
            self.vision_processor.cleanup()
        if self.parallel_processor:
            self.parallel_processor.shutdown()

        # Final statistics
        result.processing_time = time.time() - start_time
        self._show_summary(result, output_path)

        return result

    def _collect_files(self, path: Path) -> list[Path]:
        """Collect all files from path.

        Args:
            path: Directory to scan

        Returns:
            List of file paths
        """
        files = []
        if path.is_file():
            files.append(path)
        else:
            for root, _, filenames in os.walk(path):
                for filename in filenames:
                    if not filename.startswith("."):  # Skip hidden files
                        files.append(Path(root) / filename)

        self.console.print(f"[green]✓[/green] Found {len(files)} files")
        return files

    def _show_file_breakdown(
        self,
        text_files: list[Path],
        image_files: list[Path],
        video_files: list[Path],
        audio_files: list[Path],
        cad_files: list[Path],
        other_files: list[Path],
    ) -> None:
        """Show breakdown of file types."""
        table = Table(title="File Type Breakdown", show_header=True)
        table.add_column("Type", style="cyan")
        table.add_column("Count", justify="right", style="green")
        table.add_column("Status", style="yellow")

        table.add_row("Text files", str(len(text_files)), "✓ Will process")
        table.add_row("Images", str(len(image_files)), "✓ Will process")
        table.add_row("Videos", str(len(video_files)), "✓ Will process (metadata)")
        table.add_row("Audio", str(len(audio_files)), "✓ Will process (metadata)")
        table.add_row("CAD files", str(len(cad_files)), "✓ Will process")
        table.add_row("Other", str(len(other_files)), "⊘ Skip (unsupported)")

        self.console.print(table)

    def _process_text_files(self, files: list[Path]) -> list[ProcessedFile]:
        """Process text files with AI.

        Args:
            files: List of text file paths

        Returns:
            List of processed file results
        """
        processed = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task("Processing files...", total=len(files))

            # Helper for pickling
            def _process_one(path: Path) -> ProcessedFile:
                # self.text_processor is initialized before this call
                assert self.text_processor is not None
                return self.text_processor.process_file(path)

            for file_result in self.parallel_processor.process_batch_iter(files, _process_one):
                if file_result.success:
                    result = file_result.result
                    processed.append(result)

                    if not result.error:
                        progress.update(
                            task, advance=1, description=f"[green]✓[/green] {file_result.path.name}"
                        )
                    else:
                        progress.update(
                            task,
                            advance=1,
                            description=f"[red]✗[/red] {file_result.path.name} (Error)",
                        )
                else:
                    # Infrastructure failure (timeout, etc)
                    error_msg = file_result.error or "Unknown error"
                    logger.error(f"Failed to process {file_result.path}: {error_msg}")
                    processed.append(
                        ProcessedFile(
                            file_path=file_result.path,
                            description="",
                            folder_name="errors",
                            filename=file_result.path.stem,
                            error=error_msg,
                        )
                    )
                    progress.update(
                        task,
                        advance=1,
                        description=f"[red]✗[/red] {file_result.path.name} (Failed)",
                    )

        return processed

    def _process_image_files(self, files: list[Path]) -> list[ProcessedImage]:
        """Process image files with AI.

        Args:
            files: List of image file paths

        Returns:
            List of processed image results
        """
        processed = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task("Processing images...", total=len(files))

            # Helper for pickling
            def _process_one_image(path: Path) -> ProcessedImage:
                # self.vision_processor is initialized before this call
                assert self.vision_processor is not None
                return self.vision_processor.process_file(path)

            for file_result in self.parallel_processor.process_batch_iter(
                files, _process_one_image
            ):
                if file_result.success:
                    result = file_result.result
                    processed.append(result)

                    if not result.error:
                        progress.update(
                            task, advance=1, description=f"[green]✓[/green] {file_result.path.name}"
                        )
                    else:
                        progress.update(
                            task,
                            advance=1,
                            description=f"[red]✗[/red] {file_result.path.name} (Error)",
                        )
                else:
                    # Infrastructure failure
                    error_msg = file_result.error or "Unknown error"
                    logger.error(f"Failed to process {file_result.path}: {error_msg}")
                    processed.append(
                        ProcessedImage(
                            file_path=file_result.path,
                            description="",
                            folder_name="errors",
                            filename=file_result.path.stem,
                            error=error_msg,
                        )
                    )
                    progress.update(
                        task,
                        advance=1,
                        description=f"[red]✗[/red] {file_result.path.name} (Failed)",
                    )

        return processed

    def _process_audio_files(self, files: list[Path]) -> list[ProcessedFile]:
        """Process audio files using metadata pipeline (no AI model required).

        Args:
            files: List of audio file paths

        Returns:
            List of processed file results
        """
        extractor = AudioMetadataExtractor()
        classifier = AudioClassifier()
        organizer = AudioOrganizer()
        processed = []

        for audio_path in files:
            try:
                metadata = extractor.extract(audio_path)
                classification = classifier.classify(metadata)
                dest_path = organizer.generate_path(classification.audio_type, metadata)

                # dest_path includes the extension (e.g. "Music/Artist/Album/01 - Track.mp3")
                # Split into folder_name and filename stem for ProcessedFile compatibility
                folder_name = dest_path.parent.as_posix()
                filename_stem = dest_path.stem

                # Build human-readable description
                parts = [classification.audio_type.value.capitalize()]
                if metadata.artist:
                    parts.append(metadata.artist)
                if metadata.title:
                    parts.append(metadata.title)
                description = (
                    ": ".join(parts[:1]) + " " + " - ".join(parts[1:])
                    if len(parts) > 1
                    else parts[0]
                )

                processed.append(
                    ProcessedFile(
                        file_path=audio_path,
                        description=description,
                        folder_name=folder_name,
                        filename=filename_stem,
                        error=None,
                    )
                )
                logger.debug(f"Audio processed: {audio_path.name} → {folder_name}/{filename_stem}")

            except Exception as exc:
                logger.warning(f"Audio metadata extraction failed for {audio_path.name}: {exc}")
                processed.append(
                    ProcessedFile(
                        file_path=audio_path,
                        description="",
                        folder_name="Audio/Unsorted",
                        filename=audio_path.stem,
                        error=str(exc),
                    )
                )

        return processed

    def _process_video_files(self, files: list[Path]) -> list[ProcessedFile]:
        """Process video files using metadata pipeline (no AI model required).

        Args:
            files: List of video file paths

        Returns:
            List of processed file results
        """
        extractor = VideoMetadataExtractor()
        organizer = VideoOrganizer()
        processed = []

        for video_path in files:
            try:
                metadata = extractor.extract(video_path)
                folder_name, filename_stem = organizer.generate_path(metadata)
                description = organizer.generate_description(metadata)

                processed.append(
                    ProcessedFile(
                        file_path=video_path,
                        description=description,
                        folder_name=folder_name,
                        filename=filename_stem,
                        error=None,
                    )
                )
                logger.debug(f"Video processed: {video_path.name} → {folder_name}/{filename_stem}")

            except FileNotFoundError:
                raise
            except Exception as exc:
                logger.warning(f"Video metadata extraction failed for {video_path.name}: {exc}")
                processed.append(
                    ProcessedFile(
                        file_path=video_path,
                        description="",
                        folder_name="Videos/Unsorted",
                        filename=video_path.stem,
                        error=str(exc),
                    )
                )

        return processed

    def _organize_files(
        self,
        processed: list[ProcessedFile | ProcessedImage],
        output_path: Path,
        skip_existing: bool,
    ) -> dict[str, list[str]]:
        """Actually organize files into output directory.

        Args:
            processed: List of processed files (text or images)
            output_path: Output directory
            skip_existing: Skip existing files

        Returns:
            Dictionary of folder -> list of files
        """
        organized = {}
        output_path.mkdir(parents=True, exist_ok=True)

        for result in processed:
            if result.error:
                continue

            # Create folder path
            folder_path = output_path / result.folder_name
            folder_path.mkdir(parents=True, exist_ok=True)

            # Create new filename
            new_filename = f"{result.filename}{result.file_path.suffix}"
            new_path = folder_path / new_filename

            # Handle existing files
            if new_path.exists() and skip_existing:
                logger.debug(f"Skipping existing file: {new_path}")
                continue

            # Handle duplicate names
            counter = 1
            while new_path.exists():
                new_filename = f"{result.filename}_{counter}{result.file_path.suffix}"
                new_path = folder_path / new_filename
                counter += 1

            # Copy or link file
            try:
                if self.use_hardlinks:
                    os.link(result.file_path, new_path)
                else:
                    shutil.copy2(result.file_path, new_path)

                # Log the operation for undo/redo support
                if self._undo_manager is not None and self._last_transaction_id is not None:
                    self._undo_manager.history.log_operation(
                        OperationType.COPY,
                        source_path=result.file_path,
                        destination_path=new_path,
                        transaction_id=self._last_transaction_id,
                    )

                # Track in structure
                if result.folder_name not in organized:
                    organized[result.folder_name] = []
                organized[result.folder_name].append(new_filename)

            except Exception as e:
                logger.error(f"Failed to organize {result.file_path}: {e}")

        return organized

    def _simulate_organization(
        self,
        processed: list[ProcessedFile | ProcessedImage],
        output_path: Path,
    ) -> dict[str, list[str]]:
        """Simulate organization without actually moving files.

        Args:
            processed: List of processed files (text or images)
            output_path: Output directory

        Returns:
            Dictionary of folder -> list of files
        """
        organized = {}

        for result in processed:
            if result.error:
                continue

            new_filename = f"{result.filename}{result.file_path.suffix}"

            if result.folder_name not in organized:
                organized[result.folder_name] = []
            organized[result.folder_name].append(new_filename)

        return organized

    def _show_skipped_files(
        self,
        image_files: list[Path],
        video_files: list[Path],
        audio_files: list[Path],
    ) -> None:
        """Show information about skipped files."""
        self.console.print("\n[bold yellow]Skipped Files:[/bold yellow]")

        if image_files:
            self.console.print(
                f"  [yellow]•[/yellow] {len(image_files)} images (need vision model - Week 2)"
            )
        if video_files:
            self.console.print(
                f"  [yellow]•[/yellow] {len(video_files)} videos (need vision model - Week 2)"
            )
        if audio_files:
            self.console.print(
                f"  [yellow]•[/yellow] {len(audio_files)} audio files (need audio model - Phase 3)"
            )

        self.console.print("\n  [dim]These will be supported in future phases[/dim]")

    def _show_summary(self, result: OrganizationResult, output_path: Path) -> None:
        """Show final summary.

        Args:
            result: Organization result
            output_path: Output path
        """
        self.console.print("\n" + "=" * 70)
        self.console.print("[bold green]Organization Complete![/bold green]")
        self.console.print("=" * 70)

        # Statistics
        self.console.print("\n[bold]Statistics:[/bold]")
        self.console.print(f"  Total files scanned: {result.total_files}")
        self.console.print(f"  [green]Processed: {result.processed_files}[/green]")
        self.console.print(f"  [yellow]Skipped: {result.skipped_files}[/yellow]")
        self.console.print(f"  [red]Failed: {result.failed_files}[/red]")
        self.console.print(f"  Processing time: {result.processing_time:.2f}s")

        # Show structure
        if result.organized_structure:
            self.console.print("\n[bold]Organized Structure:[/bold]")
            self.console.print(f"[cyan]{output_path}/[/cyan]")

            for folder, files in sorted(result.organized_structure.items()):
                self.console.print(f"  [cyan]├── {folder}/[/cyan]")
                for i, filename in enumerate(sorted(files)):
                    prefix = "└──" if i == len(files) - 1 else "├──"
                    self.console.print(f"       {prefix} {filename}")

        if self.dry_run:
            self.console.print("\n[yellow]⚠️  DRY RUN - No files were actually moved[/yellow]")
            self.console.print("[dim]Run without --dry-run to perform actual organization[/dim]")
        else:
            self.console.print(f"\n[green]✓ Files organized in: {output_path}[/green]")

    # ------------------------------------------------------------------
    # Undo / Redo public API
    # ------------------------------------------------------------------

    def undo(self) -> bool:
        """Undo the last organize session.

        Returns:
            True if undo succeeded, False otherwise
        """
        if self._undo_manager is None or self._last_transaction_id is None:
            logger.warning("No organize session to undo")
            return False

        success = self._undo_manager.undo_transaction(self._last_transaction_id)

        # After rolling back file copies, remove any leftover empty directories
        if success and self._last_output_path is not None:
            self._cleanup_empty_dirs(self._last_output_path)

        return success

    def redo(self) -> bool:
        """Redo the last undone organize session.

        Returns:
            True if redo succeeded, False otherwise
        """
        if self._undo_manager is None or self._last_transaction_id is None:
            logger.warning("No organize session to redo")
            return False

        return self._undo_manager.redo_transaction(self._last_transaction_id)

    def _cleanup_empty_dirs(self, root: Path) -> None:
        """Remove empty directories under *root*, bottom-up.

        Only directories strictly below *root* are removed; the root itself
        is left in place (it was pre-existing before organize was called).

        Args:
            root: The output directory that was used during organize.
        """
        # Collect all subdirectories sorted deepest-first so we can safely
        # rmdir leaves before their parents.
        for dirpath in sorted(root.rglob("*"), reverse=True):
            if dirpath.is_dir() and dirpath != root:
                try:
                    dirpath.rmdir()  # Succeeds only when the directory is empty
                except OSError:
                    pass  # Not empty, or permission error – leave it in place
