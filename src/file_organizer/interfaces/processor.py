"""Protocol definitions for file-processing services.

Defines structural interfaces for single-file and batch-file processors.
``TextProcessor`` and ``VisionProcessor`` satisfy ``FileProcessorProtocol``
without inheritance changes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FileProcessorProtocol(Protocol):
    """Structural contract for single-file AI processors.

    Implementations accept a file path and return a processed-file
    dataclass (``ProcessedFile``, ``ProcessedImage``, etc.).

    The three keyword arguments below are the common subset shared by
    every concrete processor (``TextProcessor``, ``VisionProcessor``, etc.).
    Individual implementations may expose additional keyword-only parameters
    (e.g. ``perform_ocr`` on ``VisionProcessor``) without violating this
    protocol.
    """

    def initialize(self) -> None:
        """Acquire resources and prepare the processor."""
        ...

    def process_file(
        self,
        file_path: str | Path,
        *,
        generate_description: bool = True,
        generate_folder: bool = True,
        generate_filename: bool = True,
    ) -> Any:
        """Process a single file and return a result dataclass.

        Args:
            file_path: Path to the file to process.
            generate_description: Whether to generate a natural-language
                description of the file's content.
            generate_folder: Whether to suggest a target folder name.
            generate_filename: Whether to suggest a new filename.

        Returns:
            A processed-file dataclass (e.g. ``ProcessedFile``,
            ``ProcessedImage``) containing the generated metadata.
        """
        ...


@runtime_checkable
class BatchProcessorProtocol(Protocol):
    """Structural contract for batch-file processors.

    Implementations accept a list of paths plus a per-file processing
    function and return an aggregate result.
    """

    def process_batch(
        self,
        files: list[Path],
        process_fn: Callable[[Path], Any],
    ) -> Any:
        """Process a batch of files using the given processing function."""
        ...
