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
        *,
        generate_tags: bool = False,
    ) -> None:
        """Initialize with optional router, processor pool, and tagging flag."""
        self._router = router
        self._pool = processor_pool
        self._generate_tags = generate_tags

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
            generate_tags = bool(context.extra.get("generate_tags", False) or self._generate_tags)
            result = self._run_processor(
                context.file_path,
                processor,
                scan_root=context.trusted_root,
                generate_tags=generate_tags,
            )
            context.analysis = result
            context.category = result.get("category", "uncategorized")
            context.filename = result.get("filename", context.filename)
            if "tags" in result:
                context.extra["tags"] = result["tags"]
            context.extra["analyzer.processor_type"] = processor_type
        except Exception as exc:  # Intentional catch-all: processor is user-provided
            logger.exception("Analyzer failed for %s", context.file_path)
            context.error = str(exc)

        return context

    @staticmethod
    def _run_processor(
        file_path: Path,
        processor: BaseProcessor,
        scan_root: Path | None = None,
        generate_tags: bool = False,
    ) -> dict[str, Any]:
        """Invoke the processor and normalise output to a dict."""
        proc_hashable = cast(Hashable, type(processor))
        kwargs: dict[str, Any] = {}
        if AnalyzerStage._processor_accepts_param(proc_hashable, "scan_root"):
            kwargs["scan_root"] = scan_root
        if AnalyzerStage._processor_accepts_param(proc_hashable, "relative_path"):
            if scan_root is not None:
                try:
                    kwargs["relative_path"] = file_path.relative_to(scan_root)
                except ValueError:
                    kwargs["relative_path"] = file_path.name
            else:
                kwargs["relative_path"] = file_path.name
        if AnalyzerStage._processor_accepts_param(proc_hashable, "generate_tags"):
            kwargs["generate_tags"] = generate_tags

        raw = cast(Any, processor).process_file(file_path, **kwargs)
        return cast(dict[str, Any], normalize_processor_result(file_path, raw))

    @staticmethod
    @cache
    def _processor_params(processor_type: Hashable) -> frozenset[str]:
        """Inspect and cache parameter names of processor_type's process_file."""
        try:
            processor_cls = cast(type[BaseProcessor], processor_type)
            params = inspect.signature(processor_cls.process_file).parameters
            return frozenset(params.keys())
        except (AttributeError, TypeError, ValueError):
            return frozenset()

    @staticmethod
    @cache
    def _processor_accepts_param(processor_type: Hashable, param_name: str) -> bool:
        """Whether *processor_type*'s ``process_file`` accepts *param_name*."""
        return param_name in AnalyzerStage._processor_params(processor_type)

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
        return AnalyzerStage._processor_accepts_param(processor_type, "scan_root")
