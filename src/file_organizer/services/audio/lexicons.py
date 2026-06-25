"""Externalized sentiment / keyword lexicons for audio content analysis.

Epic D.cleanup D6 (hardening roadmap #157). Before D6,
``src/services/audio/content_analyzer.py`` carried ~420 LOC of inline
dicts and frozensets — stop words, topic categories, and three-way
sentiment vocab. Moving them to a JSON data file loaded by this helper
shrinks the analyzer module and makes the lexicons editable without
touching Python code (and, in a future PR, swappable per-language).

**Public API**:

- :class:`SentimentLexicon` — frozen dataclass holding the five
  lexicons after load.
- :meth:`SentimentLexicon.load_default` — loads the bundled JSON
  that ships alongside this module. Result is cached module-wide,
  so repeated calls don't reparse.
- :meth:`SentimentLexicon.load_from_path` — loads from an arbitrary
  path. No caching; each call reparses. Intended for tests and for
  future per-language lexicon packs.
- :class:`SentimentLexiconError` — raised on missing file, invalid
  JSON, missing required key, or wrong field type. Never falls back
  to an empty lexicon, which would silently degrade analysis results.

**Backward compat**: ``content_analyzer.py`` still exposes
``STOP_WORDS``, ``TOPIC_CATEGORIES``, ``POSITIVE_WORDS``,
``NEGATIVE_WORDS``, and ``NEUTRAL_WORDS`` as module-level constants.
They now come from ``SentimentLexicon.load_default()`` — pre-D6
consumers importing those names continue to work unchanged.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# The bundled default JSON lives next to this module so it ships with
# the package and is discoverable via ``Path(__file__)``.
_DEFAULT_LEXICON_PATH = Path(__file__).parent / "data" / "content_analyzer_lexicon.json"

# Fields the loader expects to find in every lexicon JSON file.
# Order matters for the error message — list keys in the order users
# would naturally read them.
_REQUIRED_KEYS: tuple[str, ...] = (
    "stop_words",
    "topic_categories",
    "positive_words",
    "negative_words",
    "neutral_words",
)


class SentimentLexiconError(ValueError):
    """Raised when a lexicon file cannot be loaded.

    Specializes :class:`ValueError` so ``except ValueError`` paths in
    pre-D6 code still catch load failures without special-casing.
    """


@dataclass(frozen=True)
class SentimentLexicon:
    """Five lexicons used by :class:`~services.audio.content_analyzer.AudioContentAnalyzer`.

    Instances are immutable. Build via :meth:`load_default` (cached)
    or :meth:`load_from_path` (fresh each call).
    """

    stop_words: frozenset[str]
    topic_categories: dict[str, list[str]]
    positive_words: frozenset[str]
    negative_words: frozenset[str]
    neutral_words: frozenset[str]

    @classmethod
    def load_default(cls) -> SentimentLexicon:
        """Return the bundled lexicon, caching the result.

        Uses double-checked locking so concurrent importers don't each
        trigger a re-parse. The dataclass is frozen and its fields
        (frozenset, dict) are not mutated after construction, so
        readers past the lock see a stable instance.

        Coderabbit PR #191: binding to a local variable narrows the
        type from ``Optional[SentimentLexicon]`` → ``SentimentLexicon``
        for Pyre / mypy-strict; the raw dict lookup can't be narrowed
        by a preceding ``is None`` check.
        """
        cached = _LOAD_DEFAULT_CACHE["value"]
        if cached is not None:
            return cached
        with _LOAD_DEFAULT_LOCK:
            cached = _LOAD_DEFAULT_CACHE["value"]
            if cached is None:
                cached = cls.load_from_path(_DEFAULT_LEXICON_PATH)
                _LOAD_DEFAULT_CACHE["value"] = cached
        return cached

    @classmethod
    def load_from_path(cls, path: Path) -> SentimentLexicon:
        """Load a lexicon from *path*.

        Raises :class:`SentimentLexiconError` on missing file, malformed
        JSON, missing key, or wrong type.
        """
        if not path.exists():
            raise SentimentLexiconError(f"lexicon file not found: {path}")

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SentimentLexiconError(f"invalid JSON in lexicon file {path}: {exc}") from exc
        except OSError as exc:
            raise SentimentLexiconError(f"cannot read lexicon file {path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise SentimentLexiconError(
                f"lexicon JSON at {path} must be an object, got {type(raw).__name__}"
            )

        missing = [k for k in _REQUIRED_KEYS if k not in raw]
        if missing:
            raise SentimentLexiconError(
                f"lexicon {path} missing required key(s): {', '.join(missing)}"
            )

        stop_words = _as_frozenset("stop_words", raw["stop_words"], path)
        positive_words = _as_frozenset("positive_words", raw["positive_words"], path)
        negative_words = _as_frozenset("negative_words", raw["negative_words"], path)
        neutral_words = _as_frozenset("neutral_words", raw["neutral_words"], path)
        topic_categories = _as_topic_dict("topic_categories", raw["topic_categories"], path)

        return cls(
            stop_words=stop_words,
            topic_categories=topic_categories,
            positive_words=positive_words,
            negative_words=negative_words,
            neutral_words=neutral_words,
        )


# Module-level cache for ``load_default``. A one-slot dict is used
# instead of a plain variable to avoid ``nonlocal`` gymnastics inside
# the classmethod and to keep the cache explicitly visible. Writes
# are guarded by ``_LOAD_DEFAULT_LOCK`` under double-checked locking
# in ``load_default``; see coderabbit review on PR #191.
_LOAD_DEFAULT_CACHE: dict[str, SentimentLexicon | None] = {"value": None}
_LOAD_DEFAULT_LOCK = threading.Lock()


def _as_frozenset(field: str, value: Any, path: Path) -> frozenset[str]:
    """Coerce a JSON list to a frozenset of strings.

    Fails loudly on wrong type rather than silently coercing.
    """
    if not isinstance(value, list):
        raise SentimentLexiconError(
            f"lexicon field {field!r} in {path} must be a list, got {type(value).__name__}"
        )
    for item in value:
        if not isinstance(item, str):
            raise SentimentLexiconError(
                f"lexicon field {field!r} in {path} must contain only strings; "
                f"found {type(item).__name__}"
            )
    return frozenset(value)


def _as_topic_dict(field: str, value: Any, path: Path) -> dict[str, list[str]]:
    """Coerce a JSON object with list values to a ``dict[str, list[str]]``."""
    if not isinstance(value, dict):
        raise SentimentLexiconError(
            f"lexicon field {field!r} in {path} must be an object, got {type(value).__name__}"
        )
    result: dict[str, list[str]] = {}
    for category, keywords in value.items():
        if not isinstance(category, str):
            raise SentimentLexiconError(
                f"lexicon field {field!r} in {path} has non-string category: {category!r}"
            )
        if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
            raise SentimentLexiconError(
                f"lexicon field {field!r}[{category!r}] in {path} must be a list of strings"
            )
        result[category] = list(keywords)
    return result
