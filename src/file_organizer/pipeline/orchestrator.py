"""Pipeline orchestrator for auto-organization.

Coordinates file discovery (via watcher or batch), routing, processing,
and organization into a cohesive pipeline.  Supports composable stages
via :class:`~file_organizer.interfaces.PipelineStage`.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from file_organizer.interfaces.pipeline import PipelineStage, StageContext

from .config import PipelineConfig
from .processor_pool import (
    BaseProcessor,
    ProcessorPool,
    ProcessorResult,
    normalize_processor_result,
)
from .router import FileRouter, ProcessorType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessingResult:
    """Result of processing a single file through the pipeline.

    Attributes:
        file_path: Original path of the processed file.
        success: Whether processing completed without errors.
        category: The folder/category name assigned to the file.
        destination: The target path where the file was (or would be) placed.
        duration_ms: Processing time in milliseconds.
        error: Error message if processing failed, None otherwise.
        processor_type: The processor type that handled the file.
        dry_run: Whether this was a dry-run (no files actually moved).
    """

    file_path: Path
    success: bool
    category: str = ""
    destination: Path | None = None
    duration_ms: float = 0.0
    error: str | None = None
    processor_type: ProcessorType = ProcessorType.UNKNOWN
    dry_run: bool = True


@dataclass
class PipelineStats:
    """Cumulative statistics for pipeline operations.

    Attributes:
        total_processed: Total files that went through the pipeline.
        successful: Number of files processed successfully.
        failed: Number of files that failed processing.
        skipped: Number of files skipped (unsupported, filtered).
        total_duration_ms: Total processing time in milliseconds.
    """

    total_processed: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    total_duration_ms: float = 0.0


class PipelineOrchestrator:
    """Orchestrates the auto-organization pipeline.

    Connects file discovery to processing and organization.  Supports
    both batch mode (process a list of files) and watch mode (react
    to file-system events in real-time).

    The orchestrator can operate in two modes:

    1. **Stage-based** (new): supply a ``stages`` list of
       :class:`~file_organizer.interfaces.PipelineStage` instances.
       Each file flows through the stages in order.
    2. **Legacy** (default): uses the built-in router, processor pool,
       and ``_process_with_processor`` / ``_organize_file`` helpers
       for backward compatibility.

    Dry-run mode is enabled by default for safety.  Files are only
    moved when both ``dry_run=False`` and ``auto_organize=True`` in
    config.

    Example::

        from file_organizer.pipeline.stages import (
            PreprocessorStage, AnalyzerStage,
            PostprocessorStage, WriterStage,
        )
        config = PipelineConfig(
            output_directory=Path("organized"),
            dry_run=True,
        )
        pipeline = PipelineOrchestrator(
            config,
            stages=[
                PreprocessorStage(),
                AnalyzerStage(),
                PostprocessorStage(output_directory=config.output_directory),
                WriterStage(),
            ],
        )
        result = pipeline.process_file(Path("document.pdf"))
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        stages: Sequence[PipelineStage] | None = None,
    ) -> None:
        """Initialize the pipeline orchestrator.

        Args:
            config: Pipeline configuration.  Uses safe defaults if *None*.
            stages: Optional list of composable pipeline stages.
                When provided, ``process_file`` delegates to these stages
                instead of the legacy router/pool path.
        """
        self.config = config or PipelineConfig()
        self.router = FileRouter()
        self.processor_pool = ProcessorPool()
        self.stats = PipelineStats()
        self._stats_lock = threading.Lock()
        self._stages: list[PipelineStage] = list(stages) if stages else []

        self._running = False
        self._lock = threading.Lock()
        self._monitor: Any = None
        self._watch_thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=self.config.max_concurrent,
        )

    # ------------------------------------------------------------------
    # Stage management
    # ------------------------------------------------------------------

    @property
    def stages(self) -> list[PipelineStage]:
        """Return the current stage list (mutable copy)."""
        return list(self._stages)

    def set_stages(self, stages: Sequence[PipelineStage]) -> None:
        """Replace the stage list at runtime (thread-safe).

        Args:
            stages: New ordered list of pipeline stages.
        """
        with self._lock:
            self._stages = list(stages)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the pipeline, including watch mode if configured.

        When watch_config is set, starts a background thread that
        polls the file monitor for events and processes them.

        Raises:
            RuntimeError: If the pipeline is already running.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("Pipeline is already running")

            self._running = True

            # Start file monitor if watch config is provided
            if self.config.watch_config is not None:
                self._start_watch_mode()

            logger.info(
                "Pipeline started (dry_run=%s, auto_organize=%s)",
                self.config.dry_run,
                self.config.auto_organize,
            )

    def stop(self) -> None:
        """Stop the pipeline and clean up resources.

        Stops the file monitor (if running), cleans up processors,
        and resets pipeline state. Safe to call even if not running.
        """
        with self._lock:
            if not self._running:
                return

            self._running = False

            # Stop file monitor
            if self._monitor is not None:
                self._monitor.stop()
                self._monitor = None

            # Wait for watch thread
            if self._watch_thread is not None:
                self._watch_thread.join(timeout=5.0)
                self._watch_thread = None

            # Clean up executor
            self._executor.shutdown(wait=False)

            # Clean up processors
            self.processor_pool.cleanup()

            logger.info("Pipeline stopped")

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def process_file(self, file_path: Path) -> ProcessingResult:
        """Process a single file through the pipeline.

        If ``stages`` were provided, each stage is executed in order.
        Otherwise, falls back to the legacy router/pool path.

        Args:
            file_path: Path to the file to process.

        Returns:
            ProcessingResult with processing outcome and metadata.
        """
        stages = self._stages  # snapshot once; set_stages() may replace list concurrently
        if stages:
            return self._process_file_staged(file_path, stages)
        return self._process_file_legacy(file_path)

    def process_batch(self, files: list[Path]) -> list[ProcessingResult]:
        """Process a batch of files through the pipeline.

        Files are processed sequentially. Each file is routed, processed,
        and optionally organized independently.

        Args:
            files: List of file paths to process.

        Returns:
            List of ProcessingResult instances, one per file.
        """
        return [self.process_file(f) for f in files]

    @property
    def is_running(self) -> bool:
        """Return True if the pipeline is currently running."""
        return self._running

    # ------------------------------------------------------------------
    # Stage-based processing (new)
    # ------------------------------------------------------------------

    def _process_file_staged(
        self, file_path: Path, stages: list[PipelineStage]
    ) -> ProcessingResult:
        """Run *file_path* through the configured stages.

        Each stage is wrapped in a try/except so that an unexpected
        exception is recorded on the context rather than crashing the
        caller.  A custom stage returning ``None`` is also treated as a
        failure so downstream stages are not passed a ``None`` context.
        """
        start_time = time.monotonic()
        file_path = Path(file_path)

        context = StageContext(
            file_path=file_path,
            dry_run=not self.config.should_move_files,
        )

        for stage in stages:
            try:
                returned = stage.process(context)
            except Exception as exc:
                logger.exception("Stage %s raised for %s", stage.name, file_path)
                context.error = str(exc)
                break
            if returned is None:
                logger.error("Stage %s returned None for %s", stage.name, file_path)
                context.error = f"Stage {stage.name!r} returned None"
                break
            context = returned

        duration_ms = (time.monotonic() - start_time) * 1000

        processor_type = context.extra.get("analyzer.processor_type", ProcessorType.UNKNOWN)

        # Update stats (thread-safe for watch mode)
        with self._stats_lock:
            self.stats.total_processed += 1
            self.stats.total_duration_ms += duration_ms
            if context.failed:
                self.stats.failed += 1
            else:
                self.stats.successful += 1

        self._notify(file_path, not context.failed)

        return ProcessingResult(
            file_path=file_path,
            success=not context.failed,
            category=context.category,
            destination=context.destination,
            duration_ms=duration_ms,
            error=context.error,
            processor_type=processor_type,
            dry_run=context.dry_run,
        )

    # ------------------------------------------------------------------
    # Legacy processing (backward compatible)
    # ------------------------------------------------------------------

    def _process_file_legacy(self, file_path: Path) -> ProcessingResult:
        """Original monolithic processing path."""
        start_time = time.monotonic()
        file_path = Path(file_path)

        # Validate file exists
        if not file_path.exists():
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=f"File not found: {file_path}",
                dry_run=self.config.dry_run,
            )

        if not file_path.is_file():
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=f"Not a file: {file_path}",
                dry_run=self.config.dry_run,
            )

        # Check if extension is supported
        if not self.config.is_supported(file_path):
            duration_ms = (time.monotonic() - start_time) * 1000
            with self._stats_lock:
                self.stats.skipped += 1
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=f"Unsupported file extension: {file_path.suffix}",
                duration_ms=duration_ms,
                dry_run=self.config.dry_run,
            )

        # Route to processor
        processor_type = self.router.route(file_path)

        if processor_type == ProcessorType.UNKNOWN:
            duration_ms = (time.monotonic() - start_time) * 1000
            with self._stats_lock:
                self.stats.skipped += 1
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error="No processor available for this file type",
                processor_type=processor_type,
                duration_ms=duration_ms,
                dry_run=self.config.dry_run,
            )

        # Get processor from pool
        processor = self.processor_pool.get_processor(processor_type)

        if processor is None:
            duration_ms = (time.monotonic() - start_time) * 1000
            with self._stats_lock:
                self.stats.failed += 1
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=f"Failed to initialize {processor_type.value} processor",
                processor_type=processor_type,
                duration_ms=duration_ms,
                dry_run=self.config.dry_run,
            )

        # Process the file
        try:
            result = self._process_with_processor(file_path, processor, processor_type)
            duration_ms = (time.monotonic() - start_time) * 1000

            # Build destination path
            category = result.get("category", "uncategorized")
            filename = result.get("filename", file_path.stem)
            destination = self.config.output_directory / category / f"{filename}{file_path.suffix}"

            # Organize file if configured
            if self.config.should_move_files:
                self._organize_file(file_path, destination)

            # Update stats
            with self._stats_lock:
                self.stats.total_processed += 1
                self.stats.successful += 1
                self.stats.total_duration_ms += duration_ms

            processing_result = ProcessingResult(
                file_path=file_path,
                success=True,
                category=category,
                destination=destination,
                duration_ms=duration_ms,
                processor_type=processor_type,
                dry_run=self.config.dry_run,
            )

            self._notify(file_path, True)
            return processing_result

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            with self._stats_lock:
                self.stats.total_processed += 1
                self.stats.failed += 1
                self.stats.total_duration_ms += duration_ms

            logger.exception("Failed to process %s", file_path)

            self._notify(file_path, False)
            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=str(e),
                processor_type=processor_type,
                duration_ms=duration_ms,
                dry_run=self.config.dry_run,
            )

    def _notify(self, file_path: Path, success: bool) -> None:
        """Fire the notification callback, swallowing exceptions."""
        if self.config.notification_callback is not None:
            try:
                self.config.notification_callback(file_path, success)
            except Exception:
                logger.exception("Notification callback failed for %s", file_path)

    def _process_with_processor(
        self,
        file_path: Path,
        processor: BaseProcessor,
        processor_type: ProcessorType,
    ) -> ProcessorResult:
        """Process a file and return normalised ``{category, filename}`` dict.

        Args:
            file_path: Path to the file to process.
            processor: The processor instance to use.
            processor_type: The type of processor (for logging).

        Returns:
            Dictionary with 'category' and 'filename' keys.

        Raises:
            RuntimeError: If the processor reports an error.
        """
        raw = processor.process_file(file_path)
        return normalize_processor_result(file_path, raw)

    def _organize_file(self, source: Path, destination: Path) -> None:
        """Move or copy a file to its destination.

        Creates the destination directory if needed.

        Args:
            source: Source file path.
            destination: Destination file path.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Handle duplicate filenames
        final_dest = destination
        counter = 1
        while final_dest.exists():
            stem = destination.stem
            suffix = destination.suffix
            final_dest = destination.parent / f"{stem}_{counter}{suffix}"
            counter += 1

        shutil.copy2(source, final_dest)
        logger.info("Organized %s -> %s", source, final_dest)

    def _start_watch_mode(self) -> None:
        """Start the file monitor and watch thread."""
        from file_organizer.watcher import FileMonitor

        self._monitor = FileMonitor(config=self.config.watch_config)
        self._monitor.start()

        self._watch_thread = threading.Thread(
            target=self._watch_loop,
            name="pipeline-watcher",
            daemon=True,
        )
        self._watch_thread.start()
        logger.info("Watch mode started")

    def _watch_loop(self) -> None:
        """Background loop that polls the monitor for events and processes them.

        Uses a thread pool executor to process files without blocking
        the event loop.
        """
        while self._running and self._monitor is not None:
            try:
                events = self._monitor.get_events(max_size=self.config.max_concurrent)

                for event in events:
                    if event.is_directory:
                        continue

                    try:
                        # Submit to executor to avoid blocking the watch loop
                        self._executor.submit(self.process_file, event.path)
                    except Exception:
                        logger.exception("Error processing %s", event.path)

            except Exception:
                logger.exception("Error in watch loop")

            # Small sleep to avoid busy-waiting
            time.sleep(0.5)
