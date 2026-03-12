"""Main file organizer orchestrator (facade).

``FileOrganizer`` is the public API for the organize workflow.  It
delegates to extracted modules for specific concerns:

- ``core.types``: ``OrganizationResult`` and extension constants
- ``core.initializer``: Processor startup and dependency wiring
- ``core.dispatcher``: Per-type file processing pipelines
- ``core.file_ops``: File collection, copy/link, simulation, cleanup
- ``core.display``: Rich UI output (progress, summary, tables)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import ClassVar

from loguru import logger
from rich.console import Console

from file_organizer.core import dispatcher, display, file_ops, initializer
from file_organizer.core.types import (
    AUDIO_EXTENSIONS,
    CAD_EXTENSIONS,
    IMAGE_EXTENSIONS,
    TEXT_EXTENSIONS,
    TEXT_FALLBACK_MAP,
    VIDEO_EXTENSIONS,
    OrganizationResult,
)
from file_organizer.models.base import ModelConfig
from file_organizer.parallel.config import ExecutorType, ParallelConfig
from file_organizer.parallel.processor import ParallelProcessor
from file_organizer.services import ProcessedFile, ProcessedImage, TextProcessor, VisionProcessor
from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor
from file_organizer.undo import UndoManager


class FileOrganizer:
    """Main file organizer that orchestrates the entire process.

    This class scans directories for files, routes them to the
    appropriate processor (text, image, audio, video), organizes
    results into a folder structure, and provides progress feedback.

    Attributes:
        TEXT_EXTENSIONS: Supported text file extensions
        IMAGE_EXTENSIONS: Supported image file extensions
        VIDEO_EXTENSIONS: Supported video file extensions
        AUDIO_EXTENSIONS: Supported audio file extensions
        CAD_EXTENSIONS: Supported CAD file extensions
    """

    # ClassVars re-exported from core.types for backward compatibility
    TEXT_EXTENSIONS: ClassVar[set[str]] = set(TEXT_EXTENSIONS)
    IMAGE_EXTENSIONS: ClassVar[set[str]] = set(IMAGE_EXTENSIONS)
    VIDEO_EXTENSIONS: ClassVar[set[str]] = set(VIDEO_EXTENSIONS)
    AUDIO_EXTENSIONS: ClassVar[set[str]] = set(AUDIO_EXTENSIONS)
    CAD_EXTENSIONS: ClassVar[set[str]] = set(CAD_EXTENSIONS)
    _TEXT_FALLBACK_MAP: ClassVar[dict[str, str]] = TEXT_FALLBACK_MAP

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Verify fallback map covers all text and CAD extensions.

        Fires only for subclasses, not for FileOrganizer itself.
        Raises ``TypeError`` at class-definition time if any extension
        in TEXT_EXTENSIONS or CAD_EXTENSIONS is missing from
        ``_TEXT_FALLBACK_MAP``.
        """
        super().__init_subclass__(**kwargs)
        missing = (cls.TEXT_EXTENSIONS | cls.CAD_EXTENSIONS) - cls._TEXT_FALLBACK_MAP.keys()
        if missing:
            raise TypeError(
                f"{cls.__name__}._TEXT_FALLBACK_MAP is missing entries for: {missing}. "
                "Add them to keep fallback organization consistent with extension routing."
            )

    def __init__(
        self,
        text_model_config: ModelConfig | None = None,
        vision_model_config: ModelConfig | None = None,
        dry_run: bool = True,
        use_hardlinks: bool = True,
        parallel_workers: int | None = None,
        no_prefetch: bool = False,
    ) -> None:
        """Initialize file organizer.

        Args:
            text_model_config: Configuration for text model (optional)
            vision_model_config: Configuration for vision model (optional)
            dry_run: If True, only simulate operations
            use_hardlinks: If True, create hardlinks instead of copying
            parallel_workers: Number of parallel workers (default: None = auto)
            no_prefetch: If True, disable I/O-compute overlap when using
                the stage-based pipeline (``PipelineOrchestrator``).
                Has no effect on the legacy processor path.
        """
        if text_model_config is None or vision_model_config is None:
            from file_organizer.config.provider_env import get_model_configs

            resolved_text, resolved_vision = get_model_configs()
            self.text_model_config = text_model_config or resolved_text
            self.vision_model_config = vision_model_config or resolved_vision
        else:
            self.text_model_config = text_model_config
            self.vision_model_config = vision_model_config
        self.dry_run = dry_run
        self.use_hardlinks = use_hardlinks
        self.no_prefetch = no_prefetch
        if no_prefetch:
            logger.warning(
                "no_prefetch=True has no effect: FileOrganizer uses ParallelProcessor, "
                "not PipelineOrchestrator. To control prefetch behaviour, construct "
                "PipelineOrchestrator directly with prefetch_depth=0."
            )
        self.console = Console()

        self.parallel_config = ParallelConfig(
            max_workers=parallel_workers,
            executor_type=ExecutorType.THREAD,
            timeout_per_file=60.0,
            retry_count=1,
        )
        self.parallel_processor = ParallelProcessor(self.parallel_config)

        self.text_processor: TextProcessor | None = None
        self.vision_processor: VisionProcessor | None = None
        self._undo_manager: UndoManager | None = None
        self._last_transaction_id: str | None = None
        self._last_output_path: Path | None = None

        logger.info(
            "FileOrganizer initialized (dry_run={}, parallel={})", dry_run, parallel_workers
        )

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

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

        Raises:
            ValueError: If input path does not exist
        """
        start_time = time.time()
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise ValueError(f"Input path does not exist: {input_path}")

        self.console.print(f"\n[bold blue]Scanning:[/bold blue] {input_path}")
        files = file_ops.collect_files(input_path, self.console)

        result = OrganizationResult(total_files=len(files))
        if not files:
            self.console.print("[yellow]No files found to organize[/yellow]")
            return result

        # Categorize files (single pass)
        text_files: list[Path] = []
        image_files: list[Path] = []
        video_files: list[Path] = []
        audio_files: list[Path] = []
        cad_files: list[Path] = []
        other_files: list[Path] = []

        for f in files:
            ext = f.suffix.lower()
            if ext in self.TEXT_EXTENSIONS:
                text_files.append(f)
            elif ext in self.IMAGE_EXTENSIONS:
                image_files.append(f)
            elif ext in self.VIDEO_EXTENSIONS:
                video_files.append(f)
            elif ext in self.AUDIO_EXTENSIONS:
                audio_files.append(f)
            elif ext in self.CAD_EXTENSIONS:
                cad_files.append(f)
            else:
                other_files.append(f)

        display.show_file_breakdown(
            self.console,
            text_files=text_files,
            image_files=image_files,
            video_files=video_files,
            audio_files=audio_files,
            cad_files=cad_files,
            other_files=other_files,
        )

        # Process each file type
        all_processed: list[ProcessedFile | ProcessedImage] = []
        self.text_processor = None
        self.vision_processor = None

        try:
            # Text + CAD
            if text_files or cad_files:
                self._init_text_processor()

            text_ready = (
                self.text_processor is not None and self.text_processor.text_model.is_initialized
            )

            if text_files:
                self.console.print(
                    f"\n[bold blue]Processing {len(text_files)} text files...[/bold blue]"
                )
                if text_ready:
                    all_processed.extend(self._process_text_files(text_files))
                else:
                    all_processed.extend(self._fallback_by_extension(text_files))

            if cad_files:
                self.console.print(
                    f"\n[bold blue]Processing {len(cad_files)} CAD files...[/bold blue]"
                )
                if text_ready:
                    all_processed.extend(self._process_text_files(cad_files))
                else:
                    all_processed.extend(self._fallback_by_extension(cad_files))

            # Release text model VRAM before loading vision model
            if image_files and self.text_processor:
                self.text_processor.cleanup()
                self.text_processor = None

            # Images
            if image_files:
                self._init_vision_processor()
                vision_ready = (
                    self.vision_processor is not None
                    and self.vision_processor.vision_model.is_initialized
                )
                self.console.print(
                    f"\n[bold blue]Processing {len(image_files)} images...[/bold blue]"
                )
                if vision_ready:
                    all_processed.extend(self._process_image_files(image_files))
                else:
                    all_processed.extend(self._fallback_by_extension(image_files))

            # Audio
            if audio_files:
                self.console.print(
                    f"\n[bold blue]Processing {len(audio_files)} audio files...[/bold blue]"
                )
                all_processed.extend(self._process_audio_files(audio_files))

            # Video
            if video_files:
                self.console.print(
                    f"\n[bold blue]Processing {len(video_files)} videos...[/bold blue]"
                )
                all_processed.extend(self._process_video_files(video_files))

        finally:
            if self.text_processor:
                self.text_processor.cleanup()
            if self.vision_processor:
                self.vision_processor.cleanup()

        # Organize
        if all_processed:
            failed_cnt = len([p for p in all_processed if p.error])
            result.processed_files = len(all_processed) - failed_cnt
            result.failed_files = failed_cnt

            if not self.dry_run:
                self.console.print("\n[bold blue]Organizing files...[/bold blue]")
                if self._undo_manager is None:
                    self._undo_manager = UndoManager()
                self._last_transaction_id = self._undo_manager.history.start_transaction(
                    metadata={"input_path": str(input_path), "output_path": str(output_path)}
                )
                self._last_output_path = output_path

                try:
                    organized = file_ops.organize_files(
                        all_processed,
                        output_path,
                        skip_existing,
                        use_hardlinks=self.use_hardlinks,
                        undo_manager=self._undo_manager,
                        transaction_id=self._last_transaction_id,
                    )
                except Exception:
                    logger.exception(
                        "Error while organizing files; leaving transaction {} uncommitted",
                        self._last_transaction_id,
                    )
                    raise
                else:
                    self._undo_manager.history.commit_transaction(self._last_transaction_id)
                    result.organized_structure = organized
            else:
                self.console.print(
                    "\n[bold yellow]DRY RUN - Simulating organization...[/bold yellow]"
                )
                result.organized_structure = file_ops.simulate_organization(
                    all_processed, output_path
                )

        # Skipped files
        if other_files:
            result.skipped_files = len(other_files)
            self.console.print("\n[bold yellow]Skipped Files:[/bold yellow]")
            for f in other_files:
                self.console.print(f"  [yellow]•[/yellow] {f.name} (unsupported type)")
            self.console.print("\n  [dim]These file types are not yet supported[/dim]")

        result.processing_time = time.time() - start_time
        display.show_summary(self.console, result, output_path, dry_run=self.dry_run)

        return result

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def undo(self) -> bool:
        """Undo the last organize session."""
        if self._undo_manager is None or self._last_transaction_id is None:
            logger.warning("No organize session to undo")
            return False

        success = self._undo_manager.undo_transaction(self._last_transaction_id)
        if success and self._last_output_path is not None:
            file_ops.cleanup_empty_dirs(self._last_output_path)
        return success

    def redo(self) -> bool:
        """Redo the last undone organize session."""
        if self._undo_manager is None or self._last_transaction_id is None:
            logger.warning("No organize session to redo")
            return False

        return self._undo_manager.redo_transaction(self._last_transaction_id)

    # ------------------------------------------------------------------
    # Backward-compatible delegation (used by existing tests)
    # ------------------------------------------------------------------

    def _collect_files(self, path: Path) -> list[Path]:
        return file_ops.collect_files(path, self.console)

    def _fallback_by_extension(self, files: list[Path]) -> list[ProcessedFile]:
        return file_ops.fallback_by_extension(files)

    def _organize_files(
        self,
        processed: list[ProcessedFile | ProcessedImage],
        output_path: Path,
        skip_existing: bool,
    ) -> dict[str, list[str]]:
        return file_ops.organize_files(
            processed,
            output_path,
            skip_existing,
            use_hardlinks=self.use_hardlinks,
            undo_manager=self._undo_manager,
            transaction_id=self._last_transaction_id,
        )

    def _simulate_organization(
        self,
        processed: list[ProcessedFile | ProcessedImage],
        output_path: Path,
    ) -> dict[str, list[str]]:
        return file_ops.simulate_organization(processed, output_path)

    def _cleanup_empty_dirs(self, root: Path) -> None:
        file_ops.cleanup_empty_dirs(root)

    def _init_text_processor(self) -> None:
        self.text_processor = initializer.init_text_processor(
            self.text_model_config,
            self.console,
            processor_cls=TextProcessor,
        )

    def _init_vision_processor(self) -> None:
        self.vision_processor = initializer.init_vision_processor(
            self.vision_model_config,
            self.console,
            processor_cls=VisionProcessor,
        )

    def _process_text_files(self, files: list[Path]) -> list[ProcessedFile]:
        assert self.text_processor is not None
        return dispatcher.process_text_files(
            files, self.text_processor, self.parallel_processor, self.console
        )

    def _process_image_files(self, files: list[Path]) -> list[ProcessedImage]:
        assert self.vision_processor is not None
        return dispatcher.process_image_files(
            files, self.vision_processor, self.parallel_processor, self.console
        )

    def _process_audio_files(self, files: list[Path]) -> list[ProcessedFile]:
        return dispatcher.process_audio_files(files, extractor_cls=AudioMetadataExtractor)

    def _process_video_files(self, files: list[Path]) -> list[ProcessedFile]:
        return dispatcher.process_video_files(files, extractor_cls=VideoMetadataExtractor)
