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
    (
        IntentType.ORGANIZE,
        [
            r"\borgani[sz]e\b",
            r"\bsort\s+(my\s+)?files\b",
            r"\bclean\s+up\b",
            r"\btidy\b",
            r"\bcategoriz[es]\b",
        ],
        0.85,
    ),
    (
        IntentType.MOVE,
        [
            r"\bmove\b",
            r"\brelocate\b",
            r"\btransfer\b",
        ],
        0.85,
    ),
    (
        IntentType.RENAME,
        [
            r"\brename\b",
            r"\bchange\s+(the\s+)?name\b",
        ],
        0.85,
    ),
    (
        IntentType.FIND,
        [
            r"\bfind\b",
            r"\bsearch\b",
            r"\bwhere\s+is\b",
            r"\blocate\b",
            r"\blook\s+for\b",
        ],
        0.80,
    ),
    (
        IntentType.PREVIEW,
        [
            r"\bpreview\b",
            r"\bdry[\s-]?run\b",
            r"\bwhat\s+would\b",
            r"\bsimulate\b",
        ],
        0.80,
    ),
    (
        IntentType.SUGGEST,
        [
            r"\bsuggest\b",
            r"\brecommend\b",
            r"\bwhere\s+should\b",
            r"\bbetter\s+location\b",
        ],
        0.75,
    ),
    (
        IntentType.STATUS,
        [
            r"\bstatus\b",
            r"\bhow\s+many\b",
            r"\bstatistics\b",
            r"\bstats\b",
        ],
        0.70,
    ),
    (
        IntentType.HELP,
        [
            r"\bhelp\b",
            r"\bwhat\s+can\s+you\b",
            r"\bcommands?\b",
            r"\bcapabilit",
        ],
        0.70,
    ),
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

    def _extract_parameters(self, intent_type: IntentType, text: str) -> dict[str, Any]:
        """Extract intent-specific parameters from the user text.

        Args:
            intent_type: The classified intent.
            text: Original user text.

        Returns:
            Dict of extracted parameters.
        """
        params: dict[str, Any] = {}

        # Extract common elements
        quoted = self._extract_quoted_strings(text)
        if quoted:
            params["quoted_args"] = quoted

        paths = self._extract_paths(text)
        if paths:
            params["paths"] = paths

        # Dispatch to intent-specific extraction
        self._extract_intent_specific_params(intent_type, text, params, quoted, paths)

        return params

    @staticmethod
    def _extract_quoted_strings(text: str) -> list[str]:
        """Extract quoted strings from text.

        Args:
            text: Input text.

        Returns:
            List of quoted strings.
        """
        return re.findall(r'"([^"]+)"', text) + re.findall(r"'([^']+)'", text)

    @staticmethod
    def _extract_paths(text: str) -> list[str]:
        """Extract file paths from text (Unix-style or Windows-style).

        Args:
            text: Input text.

        Returns:
            List of detected paths.
        """
        return re.findall(
            r"(?:[~/][\w./-]+|[A-Z]:\\[\w.\\-]+)",
            text,
        )

    def _extract_intent_specific_params(
        self,
        intent_type: IntentType,
        text: str,
        params: dict[str, Any],
        quoted: list[str],
        paths: list[str],
    ) -> None:
        """Extract intent-specific parameters and update params dict.

        Args:
            intent_type: The classified intent.
            text: Original user text.
            params: Parameter dict to update in-place.
            quoted: Pre-extracted quoted strings.
            paths: Pre-extracted paths.
        """
        if intent_type == IntentType.ORGANIZE:
            self._extract_organize_params(text, params, paths)
        elif intent_type == IntentType.MOVE:
            self._extract_move_params(params, paths)
        elif intent_type == IntentType.RENAME:
            self._extract_rename_params(params, quoted, paths)
        elif intent_type == IntentType.FIND:
            self._extract_find_params(text, params)

    @staticmethod
    def _extract_organize_params(text: str, params: dict[str, Any], paths: list[str]) -> None:
        """Extract parameters for ORGANIZE intent.

        Args:
            text: Original user text.
            params: Parameter dict to update.
            paths: Pre-extracted paths.
        """
        if paths:
            params["source"] = paths[0]
            if len(paths) > 1:
                params["destination"] = paths[1]
        if re.search(r"\bdry[\s-]?run\b|\bpreview\b", text, re.IGNORECASE):
            params["dry_run"] = True

    @staticmethod
    def _extract_move_params(params: dict[str, Any], paths: list[str]) -> None:
        """Extract parameters for MOVE intent.

        Args:
            params: Parameter dict to update.
            paths: Pre-extracted paths.
        """
        if paths:
            params["source"] = paths[0]
            if len(paths) > 1:
                params["destination"] = paths[1]

    @staticmethod
    def _extract_rename_params(params: dict[str, Any], quoted: list[str], paths: list[str]) -> None:
        """Extract parameters for RENAME intent.

        Args:
            params: Parameter dict to update.
            quoted: Pre-extracted quoted strings.
            paths: Pre-extracted paths.
        """
        if quoted:
            params["new_name"] = quoted[-1]
        if paths:
            params["target"] = paths[0]

    @staticmethod
    def _extract_find_params(text: str, params: dict[str, Any]) -> None:
        """Extract parameters for FIND intent.

        Args:
            text: Original user text.
            params: Parameter dict to update.
        """
        for kw in ("find", "search", "locate", "look for"):
            idx = text.lower().find(kw)
            if idx >= 0:
                query = text[idx + len(kw) :].strip().strip('"').strip("'")
                if query:
                    params["query"] = query
                break
