"""Classify per-file failures into the #411 error taxonomy.

Final summary surfaces:

  vision_timeout    — files where vision exceeded its dispatcher timeout
                      (whether or not the metadata fallback rescued them)
  read_error        — filesystem-layer failures: read denied, symlink
                      rejected, file too large
  unsupported_type  — read returned None / "Unsupported file type"
  inference_error   — model-call failures (provider 500, AttributeError,
                      generic RuntimeError raised by the inference path)
  other             — anything that didn't match the buckets above

Returning a stable string keeps the summary renderer
(``core/display.py``) decoupled from the result classes and lets
analytics consumers (``--json``) emit a clean category field.
"""

from __future__ import annotations

from typing import Any, Literal

ErrorCategory = Literal[
    "vision_timeout",
    "read_error",
    "unsupported_type",
    "inference_error",
    "other",
]

# Recommendation strings the summary renderer attaches to each category
# when it exceeds the 10%-of-scanned-files trigger.  Phrased as
# actionable next steps so an operator can fix the issue without
# re-reading the dispatcher source.
RECOMMENDATIONS: dict[str, str] = {
    "vision_timeout": (
        "consider `--timeout-per-file` to raise the cap or `--workers` to parallelise (#396 / #408)"
    ),
    "read_error": ("check filesystem permissions or exclude unreadable files from the input set"),
    "unsupported_type": (
        "see the top-skipped-extensions list above; install the matching extra "
        "(e.g. `[scientific]`, `[cad]`) or skip those files explicitly"
    ),
    "inference_error": (
        "check Ollama / provider health; for worker-pool aborts on low-memory "
        "hardware try `--timeout-per-file 1800` or `--workers 1` (#396 / #408)"
    ),
    "other": ("inspect the per-file logs — these failures didn't fit the known taxonomy"),
}


# Substring tokens that signal a read-side failure, anchored to the
# exact error strings the codebase emits today. We match case-insensitively
# to absorb minor wording drift.
_READ_ERROR_TOKENS: tuple[str, ...] = (
    "refused to read symlink",
    "file not found",
    "permission denied",
    "exceeds max_file_size",  # FileTooLargeError shape
    "filereaderror",
    "fileexists",
    # Every reader in utils/readers/ wraps parse / decode failures as
    # ``FileReadError(f"Failed to read <FORMAT> ...")`` — those propagate
    # through services.text_processor.process_file → ProcessedFile.error
    # as "Failed to read DOCX file ...", "Failed to read PDF file ...",
    # etc.  Without this token they bucket into ``inference_error`` and
    # mislead the operator-facing recommendation.
    "failed to read",
)

# Tokens that signal the file's extension / content type isn't supported.
_UNSUPPORTED_TYPE_TOKENS: tuple[str, ...] = ("unsupported file type",)

# Tokens that positively identify a model-invocation failure. We require
# a match here before bucketing as ``inference_error`` because audio /
# video metadata pipelines emit ``confidence=0.0`` on ANY extractor
# exception (#409 surfacing) even when no provider was contacted — without
# this guard those runs would land in ``inference_error`` and produce the
# wrong operator recommendation ("check Ollama / provider health").
# Codex P2 catch on PR #427.
_INFERENCE_ERROR_TOKENS: tuple[str, ...] = (
    "ollama",
    "anthropic",
    "openai",
    "rate limit",
    "rate_limit",
    "http 5",  # HTTP 5xx responses from a vision / text provider
    "model returned",
    "model error",
    "provider",
    "api error",
    "api_error",
    "json decode",
    "jsondecode",
    "completion failed",
    "inference failed",
    # VisionProcessor._circuit_open_error() emits this exact prefix when
    # the backend's failure circuit is open; otherwise it would fall
    # through to `other` and weaken operator guidance during degraded
    # availability (Codex P2 on PR #427).
    "vision backend unavailable",
    "backend unavailable",
    # Parallel-processor pool abort (#431). When the worker pool detects
    # hung tasks and aborts, every untried-or-hung task surfaces with
    # one of these prefixes. The 2026-05-26 organize run produced 478
    # of them; without these tokens they fall through to ``other`` with
    # the useless "inspect per-file logs" recommendation. They are
    # genuine inference-side failures (the model hung), so
    # ``inference_error`` is the right bucket.
    "worker pool",
    "hung tasks",
    "model is shutting down",
    "aborted:",
)


def classify_error(result: Any) -> ErrorCategory | None:
    """Return the taxonomy bucket for *result*, or ``None`` if it isn't a failure.

    Args:
        result: ``ProcessedImage`` or ``ProcessedFile``. Any object that
            exposes ``error`` and optionally ``source`` is accepted —
            we duck-type rather than importing the services package so
            this helper stays cheap to load.

    Returns:
        One of the ``ErrorCategory`` literals when the result represents
        a failure (or a #406 vision-timeout fallback); ``None`` for
        clean, happy-path results that don't need bucketing.

    Resolution order matters: vision-timeout fallback is checked first
    because those results carry ``source=fallback_*`` AND ``error=None``,
    so the rest of the matching would treat them as happy-path.
    """
    source = str(getattr(result, "source", "") or "")
    if source.startswith("fallback_"):
        return "vision_timeout"

    error = getattr(result, "error", None)
    if not error:
        return None
    err_lc = str(error).lower()

    # Parallel processor's timeout sentinel is emitted for BOTH text
    # and vision batches (Codex P2 catch on PR #427). Map to
    # ``vision_timeout`` only when the result is image-shaped — i.e.
    # exposes a ``source`` attribute (set on ProcessedImage; absent on
    # ProcessedFile). Generic text timeouts fall through to ``other``.
    if err_lc.startswith("timed out after"):
        if hasattr(result, "source"):
            return "vision_timeout"
        return "other"

    if any(tok in err_lc for tok in _UNSUPPORTED_TYPE_TOKENS):
        return "unsupported_type"

    if any(tok in err_lc for tok in _READ_ERROR_TOKENS):
        return "read_error"

    # Inference-error bucket requires a positive token match. Audio /
    # video metadata pipelines set ``confidence=0.0`` on any extractor
    # exception (#409) — without the explicit token check those runs
    # would mis-bucket as inference_error and emit the wrong "check
    # Ollama / provider health" hint (Codex P2 on PR #427).
    if any(tok in err_lc for tok in _INFERENCE_ERROR_TOKENS):
        return "inference_error"

    # Anything left over (including the audio/video confidence==0.0
    # metadata-extractor failures) lands in ``other``. The operator
    # recommendation for ``other`` points at the per-file logs, which is
    # the correct next step when the failure didn't match a known
    # provider / reader / extension shape.
    return "other"
