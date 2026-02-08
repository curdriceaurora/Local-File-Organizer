"""Intent parser — maps natural language to structured commands.

Uses keyword matching with confidence scoring.  When an LLM is available
the parser can optionally upgrade to JSON-mode structured extraction, but
the keyword approach provides a reliable zero-dependency baseline.
"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger

from file_organizer.services.copilot.models import Intent, IntentType

# Keyword patterns for each intent type, ordered by specificity.
_INTENT_PATTERNS: list[tuple[IntentType, list[str], float]] = [
    # (intent, keyword_patterns, base_confidence)
    (IntentType.UNDO, [r"\bundo\b"], 0.95),
    (IntentType.REDO, [r"\bredo\b"], 0.95),
    (IntentType.ORGANIZE, [
        r"\borgani[sz]e\b",
        r"\bsort\s+(my\s+)?files\b",
        r"\bclean\s+up\b",
        r"\btidy\b",
        r"\bcategoriz[es]\b",
    ], 0.85),
    (IntentType.MOVE, [
        r"\bmove\b",
        r"\brelocate\b",
        r"\btransfer\b",
    ], 0.85),
    (IntentType.RENAME, [
        r"\brename\b",
        r"\bchange\s+(the\s+)?name\b",
    ], 0.85),
    (IntentType.FIND, [
        r"\bfind\b",
        r"\bsearch\b",
        r"\bwhere\s+is\b",
        r"\blocate\b",
        r"\blook\s+for\b",
    ], 0.80),
    (IntentType.PREVIEW, [
        r"\bpreview\b",
        r"\bdry[\s-]?run\b",
        r"\bwhat\s+would\b",
        r"\bsimulate\b",
    ], 0.80),
    (IntentType.SUGGEST, [
        r"\bsuggest\b",
        r"\brecommend\b",
        r"\bwhere\s+should\b",
        r"\bbetter\s+location\b",
    ], 0.75),
    (IntentType.STATUS, [
        r"\bstatus\b",
        r"\bhow\s+many\b",
        r"\bstatistics\b",
        r"\bstats\b",
    ], 0.70),
    (IntentType.HELP, [
        r"\bhelp\b",
        r"\bwhat\s+can\s+you\b",
        r"\bcommands?\b",
        r"\bcapabilit",
    ], 0.70),
]


class IntentParser:
    """Parse user text into a structured ``Intent``.

    Example::

        parser = IntentParser()
        intent = parser.parse("Organise my Downloads folder")
        assert intent.intent_type == IntentType.ORGANIZE
    """

    def parse(self, text: str, *, context: str = "") -> Intent:
        """Parse user text into an intent.

        Args:
            text: The raw user input.
            context: Optional conversation context for disambiguation.

        Returns:
            A parsed ``Intent`` instance.
        """
        text_lower = text.lower().strip()

        if not text_lower:
            return Intent(intent_type=IntentType.UNKNOWN, confidence=0.0, raw_text=text)

        # Try keyword matching
        best_intent: IntentType = IntentType.CHAT
        best_confidence: float = 0.3  # baseline for chat
        matched_patterns: list[str] = []

        for intent_type, patterns, base_conf in _INTENT_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    if base_conf > best_confidence:
                        best_intent = intent_type
                        best_confidence = base_conf
                        matched_patterns.append(pattern)
                    break  # one match per intent type is enough

        # Extract parameters based on the matched intent
        parameters = self._extract_parameters(best_intent, text)

        logger.debug(
            "IntentParser: '{}' -> {} (conf={:.2f}, patterns={})",
            text[:60],
            best_intent.value,
            best_confidence,
            matched_patterns,
        )

        return Intent(
            intent_type=best_intent,
            confidence=best_confidence,
            parameters=parameters,
            raw_text=text,
        )

    # ------------------------------------------------------------------
    # Parameter extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_parameters(intent_type: IntentType, text: str) -> dict[str, Any]:
        """Extract intent-specific parameters from the user text.

        Args:
            intent_type: The classified intent.
            text: Original user text.

        Returns:
            Dict of extracted parameters.
        """
        params: dict[str, Any] = {}

        # Extract quoted strings as explicit path / name references
        quoted = re.findall(r'"([^"]+)"', text) + re.findall(r"'([^']+)'", text)
        if quoted:
            params["quoted_args"] = quoted

        # Extract paths (Unix-style or Windows-style)
        paths = re.findall(
            r'(?:[~/][\w./-]+|[A-Z]:\\[\w.\\-]+)',
            text,
        )
        if paths:
            params["paths"] = paths

        # Intent-specific extraction
        if intent_type == IntentType.ORGANIZE:
            # Look for source and destination directories
            if paths:
                params["source"] = paths[0]
                if len(paths) > 1:
                    params["destination"] = paths[1]
            # Check for dry-run request
            if re.search(r"\bdry[\s-]?run\b|\bpreview\b", text, re.IGNORECASE):
                params["dry_run"] = True

        elif intent_type == IntentType.MOVE:
            if paths:
                params["source"] = paths[0]
                if len(paths) > 1:
                    params["destination"] = paths[1]

        elif intent_type == IntentType.RENAME:
            if quoted:
                params["new_name"] = quoted[-1]
            if paths:
                params["target"] = paths[0]

        elif intent_type == IntentType.FIND:
            # Everything after "find" / "search" is the query
            for kw in ("find", "search", "locate", "look for"):
                idx = text.lower().find(kw)
                if idx >= 0:
                    query = text[idx + len(kw):].strip().strip('"').strip("'")
                    if query:
                        params["query"] = query
                    break

        return params
