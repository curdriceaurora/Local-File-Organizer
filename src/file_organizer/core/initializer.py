"""Processor initialization helpers.

Handles lazy creation and initialization of text and vision processors
with graceful fallback when models are unavailable.  Extracted from
``organizer.py`` to separate startup/dependency concerns.
"""

from __future__ import annotations

from loguru import logger
from rich.console import Console

from file_organizer.models.base import ModelConfig
from file_organizer.services import TextProcessor, VisionProcessor


def init_text_processor(
    config: ModelConfig,
    console: Console,
    *,
    processor_cls: type[TextProcessor] | None = None,
) -> TextProcessor | None:
    """Create and initialize a text processor.

    On any initialization failure (Ollama unavailable, config errors,
    import errors, etc.), logs a warning and returns ``None`` so callers
    can fall back to extension-based organization.

    Args:
        config: Model configuration for the text model.
        console: Rich console for status output.
        processor_cls: Optional processor class override used to preserve
            patchable seams in tests while keeping construction centralized.

    Returns:
        Initialized ``TextProcessor``, or ``None`` on failure.
    """
    processor: TextProcessor | None = None
    try:
        processor_type = processor_cls or TextProcessor
        processor = processor_type(config=config)
        processor.initialize()
        console.print("[green]✓[/green] Text model ready")
        return processor
    except Exception as e:
        if processor is not None:
            try:
                processor.cleanup()
            except Exception as cleanup_err:
                logger.opt(exception=cleanup_err).warning(
                    "Text processor cleanup failed after init error"
                )
        console.print(
            f"[yellow]⚠ Text model unavailable ({e.__class__.__name__}): "
            "falling back to extension-based organization[/yellow]"
        )
        logger.opt(exception=e).warning("Text model init failed, using extension fallback")
        return None


def init_vision_processor(
    config: ModelConfig,
    console: Console,
    *,
    processor_cls: type[VisionProcessor] | None = None,
) -> VisionProcessor | None:
    """Create and initialize a vision processor.

    On failure, logs a warning and returns ``None`` so callers can fall
    back to extension-based organization for images.

    Args:
        config: Model configuration for the vision model.
        console: Rich console for status output.
        processor_cls: Optional processor class override used to preserve
            patchable seams in tests while keeping construction centralized.

    Returns:
        Initialized ``VisionProcessor``, or ``None`` on failure.
    """
    processor: VisionProcessor | None = None
    try:
        processor_type = processor_cls or VisionProcessor
        processor = processor_type(config=config)
        processor.initialize()
        console.print("[green]✓[/green] Vision model ready")
        return processor
    except Exception as e:
        if processor is not None:
            try:
                processor.cleanup()
            except Exception as cleanup_err:
                logger.opt(exception=cleanup_err).warning(
                    "Vision processor cleanup failed after init error"
                )
        console.print(
            f"[yellow]⚠ Vision model unavailable ({e.__class__.__name__}): "
            "falling back to extension-based organization for images[/yellow]"
        )
        logger.opt(exception=e).warning("Vision model init failed, using extension fallback")
        return None
