"""Executor factory with fallback chain for parallel processing.

Implements graceful fallback from ProcessPoolExecutor to ThreadPoolExecutor
when process pool creation fails (e.g., in Docker, CI, or restricted
environments with semaphore limitations).
"""

from __future__ import annotations

import logging
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor

logger = logging.getLogger(__name__)


def create_executor(
    executor_type: str,
    max_workers: int,
) -> tuple[Executor, str]:
    """Create a parallel executor with graceful fallback.

    Attempts to create the specified executor type, falling back to
    ThreadPoolExecutor if the requested type fails to initialize.

    Args:
        executor_type: "process" or "thread" to specify preferred executor.
        max_workers: Number of worker threads/processes.

    Returns:
        Tuple of (executor_instance, executor_type_used) where executor_type_used
        is either "process" or "thread" indicating which was actually created.
    """
    if executor_type == "process":
        process_executor = None
        try:
            process_executor = ProcessPoolExecutor(max_workers=max_workers)
            logger.info(
                "Created ProcessPoolExecutor with %d workers",
                max_workers,
            )
            return process_executor, "process"
        except (RuntimeError, OSError) as e:
            if process_executor is not None:
                process_executor.shutdown(wait=False)
            logger.warning(
                "ProcessPoolExecutor initialization failed: %s. "
                "Falling back to ThreadPoolExecutor.",
                e,
                exc_info=True,
            )
            thread_executor = ThreadPoolExecutor(max_workers=max_workers)
            logger.info(
                "Created ThreadPoolExecutor with %d workers (fallback)",
                max_workers,
            )
            return thread_executor, "thread"
    else:
        thread_executor = ThreadPoolExecutor(max_workers=max_workers)
        logger.info(
            "Created ThreadPoolExecutor with %d workers",
            max_workers,
        )
        return thread_executor, "thread"


__all__ = ["create_executor"]
