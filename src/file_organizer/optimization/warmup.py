"""Model warmup for pre-loading models in background threads.

Provides mechanisms to pre-load models before they are needed,
reducing latency on first use.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from file_organizer.models.base import BaseModel
from file_organizer.optimization.model_cache import ModelCache

logger = logging.getLogger(__name__)


@dataclass
class WarmupResult:
    """Result of a model warmup operation.

    Attributes:
        loaded: List of model names that were successfully loaded.
        failed: List of (model_name, error_message) tuples for failures.
        duration_ms: Total wall-clock time for the warmup in milliseconds.
    """

    loaded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def total_requested(self) -> int:
        """Total number of models that were requested for warmup."""
        return len(self.loaded) + len(self.failed)

    @property
    def success_rate(self) -> float:
        """Fraction of models successfully loaded (0.0 to 1.0)."""
        total = self.total_requested
        if total == 0:
            return 1.0
        return len(self.loaded) / total


class ModelWarmup:
    """Pre-load models in background threads for reduced first-access latency.

    Uses a ModelCache instance to store pre-loaded models. Models are loaded
    in parallel using a thread pool.

    Args:
        cache: ModelCache instance to store warmed-up models.
        loader_factory: Callable that takes a model name and returns a
            loader function (Callable[[], BaseModel]).
        max_workers: Maximum number of parallel loading threads.

    Example:
        >>> cache = ModelCache(max_models=5)
        >>> warmup = ModelWarmup(cache, my_loader_factory)
        >>> result = warmup.warmup(["model-a", "model-b"])
        >>> print(f"Loaded {len(result.loaded)} models in {result.duration_ms:.0f}ms")
    """

    def __init__(
        self,
        cache: ModelCache,
        loader_factory: Callable[[str], Callable[[], BaseModel]],
        max_workers: int = 2,
    ) -> None:
        """Initialize the warmup manager.

        Args:
            cache: Cache to store pre-loaded models.
            loader_factory: Function that creates a loader for a given model name.
            max_workers: Maximum parallel loading threads.

        Raises:
            ValueError: If max_workers < 1.
        """
        if max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {max_workers}")

        self._cache = cache
        self._loader_factory = loader_factory
        self._max_workers = max_workers

    def warmup(self, model_names: list[str]) -> WarmupResult:
        """Pre-load models synchronously (blocks until all complete).

        Loads models in parallel using a thread pool, then waits for all
        to complete before returning.

        Args:
            model_names: List of model names to pre-load.

        Returns:
            WarmupResult with loading outcomes and timing.
        """
        if not model_names:
            return WarmupResult(duration_ms=0.0)

        start = time.monotonic()
        result = WarmupResult()

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_names: list[str] = []
        for name in model_names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)

        # Skip models already cached
        to_load: list[str] = []
        for name in unique_names:
            if self._cache.contains(name):
                result.loaded.append(name)
                logger.debug("Model '%s' already cached, skipping warmup", name)
            else:
                to_load.append(name)

        if to_load:
            self._load_models_parallel(to_load, result)

        elapsed = time.monotonic() - start
        result.duration_ms = elapsed * 1000.0

        logger.info(
            "Warmup complete: %d loaded, %d failed in %.0fms",
            len(result.loaded),
            len(result.failed),
            result.duration_ms,
        )
        return result

    def warmup_async(self, model_names: list[str]) -> Future[WarmupResult]:
        """Pre-load models asynchronously in a background thread.

        Returns immediately with a Future that resolves to the WarmupResult
        when all models have been loaded (or failed).

        Args:
            model_names: List of model names to pre-load.

        Returns:
            Future that resolves to WarmupResult.
        """
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="warmup-async")
        future = executor.submit(self.warmup, model_names)
        executor.shutdown(wait=False)
        return future

    def _load_models_parallel(
        self,
        model_names: list[str],
        result: WarmupResult,
    ) -> None:
        """Load models in parallel using a thread pool.

        Args:
            model_names: Models to load.
            result: WarmupResult to populate with outcomes.
        """
        workers = min(self._max_workers, len(model_names))

        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="warmup",
        ) as executor:
            futures: dict[Future[str], str] = {}
            for name in model_names:
                future = executor.submit(self._load_single_model, name)
                futures[future] = name

            for future in futures:
                name = futures[future]
                try:
                    future.result()
                    result.loaded.append(name)
                except Exception as exc:
                    error_msg = str(exc)
                    result.failed.append((name, error_msg))
                    logger.warning(
                        "Warmup failed for model '%s': %s",
                        name,
                        error_msg,
                    )

    def _load_single_model(self, model_name: str) -> str:
        """Load a single model into the cache.

        Args:
            model_name: Name of the model to load.

        Returns:
            The model name on success.

        Raises:
            Exception: If loading fails.
        """
        loader = self._loader_factory(model_name)
        self._cache.get_or_load(model_name, loader)
        logger.debug("Warmup: loaded model '%s'", model_name)
        return model_name
