"""Processor pool for lazy-loading and managing file processors.

Provides centralized access to processor instances with lazy initialization
and proper resource cleanup.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol, cast, runtime_checkable

from .router import ProcessorType

logger = logging.getLogger(__name__)


@runtime_checkable
class BaseProcessor(Protocol):
    """Protocol defining the interface for file processors.

    All processors must support initialization, file processing,
    and cleanup. This protocol allows the pool to manage any
    processor that conforms to this interface.
    """

    def initialize(self) -> None:
        """Initialize the processor and its resources."""
        ...

    def cleanup(self) -> None:
        """Release resources held by the processor."""
        ...


class ProcessorPool:
    """Manages a pool of file processors with lazy initialization.

    Processors are created on first access and reused for subsequent
    requests. Supports proper cleanup of all initialized processors.

    Example:
        >>> pool = ProcessorPool()
        >>> pool.register_factory(ProcessorType.TEXT, lambda: TextProcessor())
        >>> processor = pool.get_processor(ProcessorType.TEXT)
        >>> # processor is lazily created and initialized
        >>> pool.cleanup()  # cleans up all processors
    """

    def __init__(self) -> None:
        """Initialize an empty processor pool."""
        self._factories: dict[ProcessorType, Callable[..., Any]] = {}
        self._processors: dict[ProcessorType, BaseProcessor] = {}

    def register_factory(
        self,
        processor_type: ProcessorType,
        factory: Callable[..., Any],
    ) -> None:
        """Register a factory function for a processor type.

        The factory is called lazily when get_processor is first
        invoked for this type. The factory should return an
        uninitialized processor instance.

        Args:
            processor_type: The type of processor this factory creates.
            factory: A callable that returns a new processor instance.
        """
        self._factories[processor_type] = factory
        logger.debug("Registered factory for %s", processor_type.value)

    def get_processor(self, processor_type: ProcessorType) -> BaseProcessor | None:
        """Get a processor instance for the given type.

        Returns a cached instance if available, otherwise creates one
        using the registered factory and initializes it.

        Args:
            processor_type: The type of processor to retrieve.

        Returns:
            The processor instance, or None if no factory is registered
            for this type.
        """
        # Return cached instance
        if processor_type in self._processors:
            return self._processors[processor_type]

        # Create from factory
        factory = self._factories.get(processor_type)
        if factory is None:
            logger.warning(
                "No factory registered for processor type: %s",
                processor_type.value,
            )
            return None

        try:
            raw = factory()
            processor = cast("BaseProcessor", raw)
            processor.initialize()
            self._processors[processor_type] = processor
            logger.info("Initialized processor for %s", processor_type.value)
            return processor
        except Exception:
            logger.exception("Failed to create processor for %s", processor_type.value)
            return None

    def has_processor(self, processor_type: ProcessorType) -> bool:
        """Check if a processor is available (registered or initialized).

        Args:
            processor_type: The processor type to check.

        Returns:
            True if a factory is registered or processor is initialized.
        """
        return processor_type in self._processors or processor_type in self._factories

    def is_initialized(self, processor_type: ProcessorType) -> bool:
        """Check if a processor has been initialized.

        Args:
            processor_type: The processor type to check.

        Returns:
            True if the processor has been created and initialized.
        """
        return processor_type in self._processors

    def cleanup(self) -> None:
        """Clean up all initialized processors.

        Calls cleanup() on each processor and removes it from the cache.
        Errors during cleanup are logged but do not prevent other
        processors from being cleaned up.
        """
        for processor_type, processor in list(self._processors.items()):
            try:
                processor.cleanup()
                logger.info("Cleaned up processor for %s", processor_type.value)
            except Exception:
                logger.exception("Error cleaning up processor for %s", processor_type.value)

        self._processors.clear()

    @property
    def active_count(self) -> int:
        """Return the number of currently initialized processors."""
        return len(self._processors)

    @property
    def registered_types(self) -> list[ProcessorType]:
        """Return list of processor types with registered factories."""
        return list(self._factories.keys())
