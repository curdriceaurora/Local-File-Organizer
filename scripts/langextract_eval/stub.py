"""Offline oracle model for plumbing checks.

``--backend stub`` swaps the LLM for :class:`OracleStubModel`, which answers
with the gold entities found in the prompt's target text plus one fabricated
entity. Scores from a stub run say nothing about extraction quality; they
only prove the pipeline, scoring and grounding checks are wired correctly
(e.g. the fabricated entity must show up as unaligned / not verbatim).
"""

from __future__ import annotations

import json
from typing import Any

from file_organizer.models.base import BaseModel, ModelConfig, ModelType
from scripts.langextract_eval.corpus import CORPUS

FABRICATED = ("organization", "Nonexistent Holdings Ltd")


def _target_text(prompt: str) -> tuple[str, bool]:
    """Return (document text in the prompt, is_langextract_prompt)."""
    if "\nTEXT:\n" in prompt:
        return prompt.rsplit("\nTEXT:\n", 1)[1], False
    # langextract renders examples then the target as the final "Q: ... A:" pair.
    tail = prompt.rsplit("Q: ", 1)[-1]
    return tail.rsplit("\nA:", 1)[0], True


class OracleStubModel(BaseModel):
    """Deterministic stand-in for a text model (no network, no weights)."""

    def __init__(self) -> None:
        """Create an uninitialized stub."""
        super().__init__(ModelConfig(name="oracle-stub", model_type=ModelType.TEXT))

    def initialize(self) -> None:
        """Mark the stub ready."""
        super().initialize()

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Return gold spans in the target text plus one fabricated entity as JSON.

        The JSON shape follows the baseline or langextract prompt format.
        An uninitialized or shutting-down model raises ``RuntimeError``.
        """
        self._enter_generate()
        try:
            target, lx_style = _target_text(prompt)
            found: list[tuple[str, str]] = []
            for case in CORPUS:
                for ent in case.gold:
                    pair = (ent.entity_class, ent.text)
                    if ent.text in target and pair not in found:
                        found.append(pair)
            found.append(FABRICATED)
            if lx_style:
                payload = {
                    "extractions": [{cls: text, f"{cls}_attributes": {}} for cls, text in found]
                }
                return "```json\n" + json.dumps(payload) + "\n```"
            return json.dumps({"extractions": [{"entity_class": c, "text": t} for c, t in found]})
        finally:
            self._exit_generate()

    def cleanup(self) -> None:
        """Mark the stub uninitialized; it holds no external resources."""
        self._initialized = False
