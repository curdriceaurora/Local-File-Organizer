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
    ProcessorResult,
    normalize_processor_result,
)
from file_organizer.pipeline.router import FileRouter, ProcessorType

logger = logging.getLogger(__name__)

# process_file() kwargs AnalyzerStage knows how to forward. Whether a given
# processor accepts any of them is decided per-class by introspection in
# _processor_accepted_params(), never guessed from processor type.
_KNOWN_PROCESS_FILE_KWARGS = frozenset(
    {"scan_root", "context_root", "generate_tags", "tag_style", "tag_prompt"}
)


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
        tag_style: str | None = None,
        tag_prompt: str | None = None,
    ) -> None:
        """Initialize with optional router and processor pool.

        Args:
            router: Determines which processor handles a given file.
            processor_pool: Supplies lazily-initialized processor instances.
            generate_tags: Whether to ask the processor to generate
                descriptive tags. Forwarded to ``process_file`` only for
                processors whose signature declares this parameter.
            tag_style: Optional tagging style preset name, forwarded the
                same way as *generate_tags*.
            tag_prompt: Optional user-supplied tagging guidance prompt,
                forwarded the same way as *generate_tags*.
        """
        self._router = router
        self._pool = processor_pool
        self._generate_tags = generate_tags
        self._tag_style = tag_style
        self._tag_prompt = tag_prompt

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
                context.file_path,
                processor,
                scan_root=context.trusted_root,
                generate_tags=self._generate_tags,
                tag_style=self._tag_style,
                tag_prompt=self._tag_prompt,
            )
            context.analysis = dict(result)
            context.category = result.get("category", "uncategorized")
            context.filename = result.get("filename", context.filename)
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
        tag_style: str | None = None,
        tag_prompt: str | None = None,
    ) -> ProcessorResult:
        """Invoke the processor and normalise output to a ProcessorResult."""
        # Only pass the kwargs a given processor's process_file actually
        # declares (like TextProcessor's scan_root or VisionProcessor's
        # context_root). BaseProcessor's Protocol signature doesn't declare
        # any of them since not every concrete processor supports them, so
        # the conditional call below is checked via runtime introspection
        # rather than the static type, hence the cast. type(processor) is
        # also cast to Hashable here: Pyre's stub for the @cache-wrapped
        # callee checks the call site's argument type against Hashable
        # directly, regardless of the callee's own declared parameter type.
        accepted = AnalyzerStage._processor_accepted_params(cast(Hashable, type(processor)))
        kwargs: dict[str, Any] = {}
        if "scan_root" in accepted:
            kwargs["scan_root"] = scan_root
        elif "context_root" in accepted:
            kwargs["context_root"] = scan_root
        if "generate_tags" in accepted:
            kwargs["generate_tags"] = generate_tags
        if "tag_style" in accepted:
            kwargs["tag_style"] = tag_style
        if "tag_prompt" in accepted:
            kwargs["tag_prompt"] = tag_prompt

        if kwargs:
            raw = cast(Any, processor).process_file(file_path, **kwargs)
        else:
            raw = processor.process_file(file_path)
        return normalize_processor_result(file_path, raw)

    @staticmethod
    @cache
    def _processor_accepted_params(processor_type: Hashable) -> frozenset[str]:
        """Which of the known ``process_file`` kwargs *processor_type* accepts.

        Memoized per class so the introspection cost isn't paid on every
        file processed. Returns an empty ``frozenset`` if ``process_file``
        can't be introspected on the class (e.g. an unspecced test double),
        matching the pre-introspection behaviour of calling with no extra
        kwargs at all.

        Takes ``Hashable`` rather than ``type`` because Pyre's stub for
        ``functools.cache`` requires args to satisfy ``Hashable``, and
        doesn't infer that ``Type[BaseProcessor]`` (a Protocol) qualifies.
        """
        try:
            processor_cls = cast(type[BaseProcessor], processor_type)
            params = inspect.signature(processor_cls.process_file).parameters
        except (AttributeError, TypeError, ValueError):
            return frozenset()
        return frozenset(params) & _KNOWN_PROCESS_FILE_KWARGS
