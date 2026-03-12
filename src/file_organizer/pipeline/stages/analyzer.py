"""Analyzer stage - LLM-based content analysis.

Routes the file to the appropriate processor (text, vision, audio)
and populates ``context.analysis`` with category and suggested filename.
"""

from __future__ import annotations

import logging
from pathlib import Path

from file_organizer.interfaces.pipeline import StageContext
from file_organizer.pipeline.processor_pool import (
    BaseProcessor,
    ProcessorPool,
    normalize_processor_result,
)
from file_organizer.pipeline.router import FileRouter, ProcessorType

logger = logging.getLogger(__name__)


class AnalyzerStage:
    """Run LLM analysis on the file and populate ``context.analysis``.

    Uses a :class:`FileRouter` to determine which processor handles
    the file, and a :class:`ProcessorPool` to obtain a (lazy-loaded)
    processor instance.

    If no router or pool is provided, the stage is a no-op (useful
    for testing custom pipelines that skip analysis).
    """

    def __init__(
        self,
        router: FileRouter | None = None,
        processor_pool: ProcessorPool | None = None,
    ) -> None:
        """Initialize with optional router and processor pool."""
        self._router = router
        self._pool = processor_pool

    @property
    def name(self) -> str:
        """Return stage name."""
        return "analyzer"

    def process(self, context: StageContext) -> StageContext:
        """Analyze the file and fill ``context.analysis``."""
        if context.failed:
            return context

        if self._router is None or self._pool is None:
            logger.debug("Analyzer stage skipped (no router/pool configured)")
            return context

        processor_type = self._router.route(context.file_path)
        if processor_type == ProcessorType.UNKNOWN:
            context.error = "No processor available for this file type"
            return context

        processor = self._pool.get_processor(processor_type)
        if processor is None:
            context.error = f"Failed to initialize {processor_type.value} processor"
            return context

        try:
            result = self._run_processor(context.file_path, processor)
            context.analysis = result
            context.category = result.get("category", "uncategorized")
            context.filename = result.get("filename", context.filename)
            context.extra["analyzer.processor_type"] = processor_type
        except Exception as exc:
            logger.exception("Analyzer failed for %s", context.file_path)
            context.error = str(exc)

        return context

    @staticmethod
    def _run_processor(file_path: Path, processor: BaseProcessor) -> dict[str, str]:
        """Invoke the processor and normalise output to a dict."""
        raw = processor.process_file(file_path)
        return normalize_processor_result(file_path, raw)
