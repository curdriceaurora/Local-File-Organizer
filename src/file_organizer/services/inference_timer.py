"""Shared per-inference timer for the text + vision processors (#410).

A small context-manager wrapping ``time.perf_counter`` so the two
processors don't redefine timing logic, and so operators get a
consistent ``{kind}_inference_ms=<N>`` log line for every call that
actually invoked the model — including the failure branches that
previously silently swallowed timing data.

Usage:

    from services.inference_timer import time_inference

    with time_inference("vision", file_path) as t:
        ...  # body that MAY or MAY NOT invoke the model
        if about_to_call_model:
            t.mark_invoked()
        ...  # the model call itself
    # t.elapsed_ms carries the duration regardless. The structured log
    # line fires on __exit__ only when mark_invoked() was called or
    # the body raised (failures during a started inference count).

Pre-inference early returns that never call ``mark_invoked()`` are
silently excluded — both from the log stream AND from the in-process
samples — so log-based dashboards don't get biased downward by
near-zero non-events (CodeRabbit P2 round-trip on PR #424).
"""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType
from typing import Literal

from loguru import logger

InferenceKind = Literal["vision", "text"]


class _InferenceTimer:
    """Context-manager handle returned from :func:`time_inference`.

    Exposes ``elapsed_ms`` (a float, always >= 0) so callers can attach
    the timing to a result object as well as relying on the log line.
    Callers must call :meth:`mark_invoked` before exit to opt into the
    structured log; an exception during the body counts as an invoked-
    but-failed inference and also triggers the log automatically.
    """

    __slots__ = ("_kind", "_path", "_t0", "_invoked", "elapsed_ms")

    def __init__(self, kind: InferenceKind, file_path: Path | str) -> None:
        self._kind = kind
        self._path = Path(file_path) if not isinstance(file_path, Path) else file_path
        self._t0: float = 0.0
        self._invoked: bool = False
        self.elapsed_ms: float = 0.0

    def mark_invoked(self) -> None:
        """Signal that the body actually invoked the model.

        Without this call, a clean exit from the context manager
        produces no log line — ``elapsed_ms`` is still measured so
        callers can read it directly. With it, the log fires on
        ``__exit__`` and observability pipelines see a sample for
        this file.
        """
        self._invoked = True

    def __enter__(self) -> _InferenceTimer:
        self._t0 = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # Always record the elapsed time, even on the exception path.
        self.elapsed_ms = max(0.0, (time.perf_counter() - self._t0) * 1000.0)
        # Log only when the model was actually invoked. An exception
        # mid-body is treated as an invoked-but-failed inference: those
        # samples are exactly what operators need during degraded-
        # backend periods, so they fire the log.
        if not self._invoked and exc is None:
            return
        # Structured single-line log so log-grep / NDJSON consumers can
        # extract `{kind}_inference_ms=` deterministically.
        if exc is None:
            logger.debug(
                "{}_inference_ms={:.1f} file={}",
                self._kind,
                self.elapsed_ms,
                self._path.name,
            )
        else:
            logger.debug(
                "{}_inference_ms={:.1f} file={} error={}",
                self._kind,
                self.elapsed_ms,
                self._path.name,
                exc_type.__name__ if exc_type is not None else "unknown",
            )


def time_inference(kind: InferenceKind, file_path: Path | str) -> _InferenceTimer:
    """Open a per-inference timing scope.

    Args:
        kind: ``"vision"`` or ``"text"`` — used as the log-field prefix
            and to keep p50/p95/p99 stats partitioned per-modality in
            the run summary.
        file_path: The file being processed (used as the log's ``file``
            field; the timer never opens or stats the path itself).

    Returns:
        A context-manager whose ``.elapsed_ms`` attribute holds the
        measured duration in milliseconds after ``__exit__``. The
        structured log line is emitted only when
        :meth:`_InferenceTimer.mark_invoked` was called or the body
        raised an exception.
    """
    return _InferenceTimer(kind, file_path)
