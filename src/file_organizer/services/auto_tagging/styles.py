"""Tagging style presets and prompt validators.

Provides validation for style names and custom prompts for auto-tagging,
as well as vocabulary definitions, candidate data modeling (ScoredTag),
and heuristic ranking algorithms.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .tag_normalize import normalize_tag

STYLE_PRESETS: tuple[str, ...] = ("sfx", "audio", "code", "descriptive", "hierarchical")
_STYLE_NAMES: frozenset[str] = frozenset(STYLE_PRESETS)

MAX_TAG_PROMPT_LENGTH = 500

# SFX / Audio vocabulary terms (shared by sfx and audio alias)
SFX_VOCAB: frozenset[str] = frozenset(
    {
        "whoosh",
        "impact",
        "ambient",
        "foley",
        "drone",
        "riser",
        "sweep",
        "explosion",
        "hit",
        "glitch",
        "sub",
        "bass",
        "synth",
        "loop",
        "percussion",
        "beat",
        "melody",
        "vocal",
        "sfx",
        "sound",
        "audio",
        "transition",
        "cinematic",
        "acoustic",
        "electronic",
        "drop",
        "noise",
        "crash",
        "texture",
        "effect",
        "reverb",
        "delay",
        "distortion",
        "stinger",
        "chime",
        "bell",
        "punch",
        "laser",
        "wind",
        "water",
        "fire",
    }
)

# Code extension to language name vocabulary
CODE_LANG_VOCAB: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "jsx": "javascript",
    "tsx": "typescript",
    "java": "java",
    "cpp": "cpp",
    "c": "c",
    "h": "c",
    "hpp": "cpp",
    "rb": "ruby",
    "go": "go",
    "rs": "rust",
    "php": "php",
    "sh": "bash",
    "bash": "bash",
    "html": "html",
    "css": "css",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "sql": "sql",
    "md": "markdown",
}


@dataclass(frozen=True)
class ScoredTag:
    """A candidate tag with a normalized relevance score and provenance sources.

    Attributes:
        tag: Canonical, normalized tag string.
        score: Relevance score normalized to [0.0, 1.0] before style/prompt boosts.
        sources: Provenance sources contributing to this tag (e.g. filename, extension,
            directory, metadata, content, style, prompt).
    """

    tag: str
    score: float
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate field types and convert sources to tuple."""
        if not isinstance(self.tag, str):
            raise TypeError(f"tag must be a string, got {type(self.tag).__name__}")
        if not isinstance(self.score, (int, float)):
            raise TypeError(f"score must be numeric, got {type(self.score).__name__}")
        if not isinstance(self.sources, tuple):
            object.__setattr__(self, "sources", tuple(self.sources))


def validate_tag_style(name: str | None) -> None:
    """Validate that *name* is an allowed style name or None.

    Raises:
        ValueError: If *name* is not None and not in ``_STYLE_NAMES``, or if not a str.
    """
    if name is None:
        return

    if not isinstance(name, str):
        raise ValueError(f"tag_style must be a string or None, got {type(name).__name__}")

    if name not in _STYLE_NAMES:
        valid = ", ".join(sorted(_STYLE_NAMES))
        raise ValueError(f"Invalid tag_style '{name}'. Must be one of: {valid}")


def normalize_tag_prompt(prompt: str | None) -> str | None:
    """Normalize and validate a user-supplied tagging guidance prompt.

    Strips leading/trailing whitespace. An empty or whitespace-only prompt
    normalizes to ``None``.

    Raises:
        ValueError: If *prompt* is not a string/None, or exceeds 500 characters.
    """
    if prompt is None:
        return None

    if not isinstance(prompt, str):
        raise ValueError(f"tag_prompt must be a string or None, got {type(prompt).__name__}")

    cleaned = prompt.strip()
    if not cleaned:
        return None

    if len(cleaned) > MAX_TAG_PROMPT_LENGTH:
        raise ValueError(
            f"tag_prompt exceeds maximum length of {MAX_TAG_PROMPT_LENGTH} characters "
            f"(got {len(cleaned)})"
        )

    return cleaned


def _normalize_and_dedup(candidates: Sequence[ScoredTag]) -> dict[str, ScoredTag]:
    """Normalize tags and merge duplicates keeping max score and union of sources."""
    merged: dict[str, ScoredTag] = {}
    for cand in candidates:
        norm = normalize_tag(cand.tag)
        if norm is None:
            continue
        score = float(cand.score)
        sources = tuple(cand.sources)
        if norm in merged:
            existing = merged[norm]
            new_score = max(existing.score, score)
            combined_sources = tuple(dict.fromkeys(existing.sources + sources))
            merged[norm] = ScoredTag(tag=norm, score=new_score, sources=combined_sources)
        else:
            merged[norm] = ScoredTag(tag=norm, score=score, sources=sources)
    return merged


def _apply_prompt_boost(
    merged: dict[str, ScoredTag],
    prompt: str | None,
    stop_words: set[str] | frozenset[str] | None,
) -> None:
    """Apply 1.5x score boost to candidates matching prompt tokens."""
    if not prompt:
        return
    normalized_prompt = normalize_tag_prompt(prompt)
    if not normalized_prompt:
        return

    tokens = re.split(r"[-_\s.]+", normalized_prompt.lower())
    prompt_tokens = {
        t
        for t in tokens
        if len(t) >= 2 and t.isascii() and (stop_words is None or t not in stop_words)
    }
    for pt in prompt_tokens:
        norm_pt = normalize_tag(pt)
        if norm_pt and norm_pt in merged:
            cand = merged[norm_pt]
            new_sources = (
                cand.sources + ("prompt",) if "prompt" not in cand.sources else cand.sources
            )
            merged[norm_pt] = ScoredTag(
                tag=norm_pt,
                score=cand.score * 1.5,
                sources=new_sources,
            )


def _apply_style_boost(merged: dict[str, ScoredTag], norm_style: str | None) -> None:
    """Apply style preset scoring boosts to existing candidates."""
    if norm_style == "sfx":
        for tag, cand in list(merged.items()):
            if tag in SFX_VOCAB:
                new_sources = (
                    cand.sources + ("style",) if "style" not in cand.sources else cand.sources
                )
                merged[tag] = ScoredTag(tag=tag, score=cand.score * 2.0, sources=new_sources)

    elif norm_style == "code":
        code_vocab_terms = set(CODE_LANG_VOCAB.keys()) | set(CODE_LANG_VOCAB.values())
        for tag, cand in list(merged.items()):
            if tag in code_vocab_terms:
                new_sources = (
                    cand.sources + ("style",) if "style" not in cand.sources else cand.sources
                )
                merged[tag] = ScoredTag(tag=tag, score=cand.score * 2.0, sources=new_sources)

    elif norm_style == "descriptive":
        for tag, cand in list(merged.items()):
            if (
                len(tag) > 6
                and "content" not in cand.sources
                and ("filename" in cand.sources or "directory" in cand.sources)
            ):
                new_sources = (
                    cand.sources + ("style",) if "style" not in cand.sources else cand.sources
                )
                merged[tag] = ScoredTag(tag=tag, score=cand.score * 1.2, sources=new_sources)


def _generate_compound_candidates(
    merged: dict[str, ScoredTag], norm_style: str | None
) -> list[ScoredTag]:
    """Generate style-specific compound candidates."""
    compound_candidates: list[ScoredTag] = []
    if norm_style == "code":
        for tag, cand in merged.items():
            if "extension" in cand.sources and tag in CODE_LANG_VOCAB:
                compound_candidates.append(
                    ScoredTag(tag=f"lang/{tag}", score=cand.score, sources=("style",))
                )

    elif norm_style == "hierarchical":
        cat_candidates = [c for c in merged.values() if "extension" in c.sources]
        sub_candidates = [
            c for c in merged.values() if "directory" in c.sources or "content" in c.sources
        ]
        for cat in cat_candidates:
            for sub in sub_candidates:
                compound = normalize_tag(f"{cat.tag}/{sub.tag}")
                if compound:
                    compound_candidates.append(
                        ScoredTag(
                            tag=compound,
                            score=max(cat.score, sub.score),
                            sources=("style",),
                        )
                    )
    return compound_candidates


def rank_tag_candidates(
    candidates: Sequence[ScoredTag],
    *,
    style: str | None = None,
    prompt: str | None = None,
    top_n: int | None = None,
    stop_words: set[str] | frozenset[str] | None = None,
) -> list[ScoredTag]:
    """Rank, merge, boost, and filter tag candidates using heuristic scoring rules.

    Explicit ordered steps:
    1. Normalize each candidate tag through ``normalize_tag()``.
    2. Drop candidates that fail normalization (empty or out of 2-40 char range).
    3. Merge candidates that normalize to the same tag: keep max score, union sources.
    4. Apply style and prompt boosts once to the merged set.
    5. Generate compound candidates (e.g. hierarchical cat/sub, code lang/<ext>).
    6. Sort by descending score, ties broken alphabetically by normalized tag.
    7. Apply caller's limit (top_n) if provided.
    """
    if not candidates:
        return []

    # Step 1, 2, 3: Normalize, drop invalid, and merge duplicates
    merged = _normalize_and_dedup(candidates)
    if not merged:
        return []

    # Step 4: Apply style / prompt boosts once
    _apply_prompt_boost(merged, prompt, stop_words)

    norm_style = style.lower() if style else None
    if norm_style == "audio":
        norm_style = "sfx"
    _apply_style_boost(merged, norm_style)

    # Step 5: Generate and merge compound candidates
    for comp in _generate_compound_candidates(merged, norm_style):
        if comp.tag in merged:
            existing = merged[comp.tag]
            merged[comp.tag] = ScoredTag(
                tag=comp.tag,
                score=max(existing.score, comp.score),
                sources=tuple(dict.fromkeys(existing.sources + comp.sources)),
            )
        else:
            merged[comp.tag] = comp

    # Step 6: Sort by descending score, ties broken alphabetically
    sorted_candidates = sorted(merged.values(), key=lambda c: (-c.score, c.tag))

    # Step 7: Apply limit
    if top_n is not None:
        return sorted_candidates[:top_n]
    return sorted_candidates
