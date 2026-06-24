"""Analyzer stage - LLM-based content analysis.

Routes the file to the appropriate processor (text, vision, audio)
and populates ``context.analysis`` with category and suggested filename.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Hashable
from functools import cache
from pathlib import Path
from typing import Any, cast

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

        router = self._router
        pool = self._pool
        processor_type = router.route(context.file_path)
        if processor_type == ProcessorType.UNKNOWN:
            context.error = "No processor available for this file type"
            return context

        processor = pool.get_processor(processor_type)
        if processor is None:
            context.error = f"Failed to initialize {processor_type.value} processor"
            return context

        try:
            result = self._run_processor(
                context.file_path, processor, scan_root=context.trusted_root
            )
            context.analysis = result
            context.category = result.get("category", "uncategorized")
            context.filename = result.get("filename", context.filename)
            context.extra["analyzer.processor_type"] = processor_type
        except Exception as exc:  # Intentional catch-all: processor is user-provided
            logger.exception("Analyzer failed for %s", context.file_path)
            context.error = str(exc)

        return context

    @staticmethod
    def _run_processor(
        file_path: Path, processor: BaseProcessor, scan_root: Path | None = None
    ) -> dict[str, str]:
        """Invoke the processor and normalise output to a dict."""
        # Only pass scan_root if the processor's process_file accepts it (like
        # TextProcessor). BaseProcessor's Protocol signature doesn't declare
        # scan_root since not every concrete processor supports it, so the
        # conditional call below is checked via runtime introspection rather
        # than the static type, hence the cast.
        if AnalyzerStage._processor_accepts_scan_root(type(processor)):
            raw = cast(Any, processor).process_file(file_path, scan_root=scan_root)
        else:
            raw = processor.process_file(file_path)
        return cast(dict[str, str], normalize_processor_result(file_path, raw))

    @staticmethod
    @cache
    def _processor_accepts_scan_root(processor_type: Hashable) -> bool:
        """Whether *processor_type*'s ``process_file`` accepts ``scan_root``.

        Memoized per class so the introspection cost isn't paid on every
        file processed. Returns ``False`` if ``process_file`` can't be
        introspected on the class (e.g. an unspecced test double), matching
        the pre-introspection behaviour of calling without ``scan_root``.

        Takes ``Hashable`` rather than ``type`` because Pyre's stub for
        ``functools.cache`` requires args to satisfy ``Hashable``, and
        doesn't infer that ``Type[BaseProcessor]`` (a Protocol) qualifies.
        """
        try:
            processor_cls = cast(type[BaseProcessor], processor_type)
            params = inspect.signature(processor_cls.process_file).parameters
        except (AttributeError, TypeError, ValueError):
            return False
        return "scan_root" in params
