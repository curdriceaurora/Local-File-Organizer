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
    """

    def initialize(self) -> None:
        """Acquire resources and prepare the processor."""
        ...

    def process_file(
        self,
        file_path: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Process a single file and return a result dataclass."""
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
