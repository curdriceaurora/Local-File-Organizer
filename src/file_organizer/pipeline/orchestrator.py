"""Pipeline orchestrator for auto-organization.

Coordinates file discovery (via watcher or batch), routing, processing,
and organization into a cohesive pipeline.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import PipelineConfig
from .processor_pool import BaseProcessor, ProcessorPool
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

    Connects file discovery to processing and organization. Supports
    both batch mode (process a list of files) and watch mode (react
    to file system events in real-time).

    Dry-run mode is enabled by default for safety. Files are only
    moved when both dry_run=False and auto_organize=True in config.

    Example:
        >>> config = PipelineConfig(
        ...     output_directory=Path("/tmp/organized"),
        ...     dry_run=True,
        ... )
        >>> pipeline = PipelineOrchestrator(config)
        >>> result = pipeline.process_file(Path("document.pdf"))
        >>> print(result.category)
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        """Initialize the pipeline orchestrator.

        Args:
            config: Pipeline configuration. Uses safe defaults if None.
        """
        self.config = config or PipelineConfig()
        self.router = FileRouter()
        self.processor_pool = ProcessorPool()
        self.stats = PipelineStats()

        self._running = False
        self._lock = threading.Lock()
        self._monitor: Any = None
        self._watch_thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(max_workers=config.max_concurrent if config else 4)

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

    def process_file(self, file_path: Path) -> ProcessingResult:
        """Process a single file through the pipeline.

        Routes the file to the appropriate processor, processes it,
        and optionally organizes it into the output directory.

        Args:
            file_path: Path to the file to process.

        Returns:
            ProcessingResult with processing outcome and metadata.
        """
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

            # Notification callback
            if self.config.notification_callback is not None:
                try:
                    self.config.notification_callback(file_path, True)
                except Exception:
                    logger.exception("Notification callback failed for %s", file_path)

            return processing_result

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            self.stats.total_processed += 1
            self.stats.failed += 1
            self.stats.total_duration_ms += duration_ms

            logger.exception("Failed to process %s", file_path)

            # Notification callback for failure
            if self.config.notification_callback is not None:
                try:
                    self.config.notification_callback(file_path, False)
                except Exception:
                    logger.exception("Notification callback failed for %s", file_path)

            return ProcessingResult(
                file_path=file_path,
                success=False,
                error=str(e),
                processor_type=processor_type,
                duration_ms=duration_ms,
                dry_run=self.config.dry_run,
            )

    def process_batch(self, files: list[Path]) -> list[ProcessingResult]:
        """Process a batch of files through the pipeline.

        Files are processed sequentially. Each file is routed, processed,
        and optionally organized independently.

        Args:
            files: List of file paths to process.

        Returns:
            List of ProcessingResult instances, one per file.
        """
        results: list[ProcessingResult] = []

        for file_path in files:
            result = self.process_file(file_path)
            results.append(result)

        return results

    @property
    def is_running(self) -> bool:
        """Return True if the pipeline is currently running."""
        return self._running

    def _process_with_processor(
        self,
        file_path: Path,
        processor: BaseProcessor,
        processor_type: ProcessorType,
    ) -> dict[str, str]:
        """Process a file using the given processor.

        Adapts the processor's output into a standardized dictionary
        with 'category' and 'filename' keys.

        Args:
            file_path: Path to the file to process.
            processor: The processor instance to use.
            processor_type: The type of processor (for logging).

        Returns:
            Dictionary with 'category' and 'filename' keys.

        Raises:
            Exception: If the processor fails.
        """
        # Use the processor's process_file method
        result = processor.process_file(file_path)  # type: ignore[attr-defined]

        # Adapt the result - both ProcessedFile and ProcessedImage
        # have folder_name and filename attributes
        category = "uncategorized"
        filename = file_path.stem

        if hasattr(result, "folder_name") and result.folder_name:
            category = result.folder_name
        if hasattr(result, "filename") and result.filename:
            filename = result.filename

        # Check for processing errors in the result
        if hasattr(result, "error") and result.error:
            raise RuntimeError(f"Processor reported error: {result.error}")

        return {"category": category, "filename": filename}

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

        Uses a thread pool executor to process files without blocking the event loop.
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
