"""Extractors under evaluation.

- :class:`BaselineExtractor` — the project's current path:
  ``BaseModel.generate_structured`` with a Pydantic schema, one call per
  document, no grounding.
- :class:`LangExtractExtractor` — ``langextract.extract`` driven either by
  :class:`FileOrganizerLanguageModel` (an adapter over any project
  ``BaseModel``, so every provider we ship is usable) or by langextract's
  own Ollama provider (JSON-mode constrained decoding).

Both extractors receive the same task description and the same few-shot
example so the comparison isolates the extraction machinery, not the prompt
content. langextract is imported lazily; only this evaluation needs it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

import pydantic

from scripts.langextract_eval.corpus import CLASS_DESCRIPTIONS, EvalCase
from scripts.langextract_eval.scoring import CaseResult, Prediction

if TYPE_CHECKING:
    from file_organizer.models.base import BaseModel as FoBaseModel

TASK_DESCRIPTION = (
    "Extract named entities from the document. Use only these classes:\n"
    + "\n".join(f"- {name}: {desc}" for name, desc in CLASS_DESCRIPTIONS.items())
    + "\nCopy each entity's text exactly as it appears in the document. "
    "Do not paraphrase, normalize or invent entities. "
    "Return an empty list when there are none."
)

EXAMPLE_TEXT = (
    "PURCHASE ORDER PO-2231\nIssued 2023-11-02 by Tailwind Traders to Coho Winery.\n"
    "Approved by Ana Silva. Total: $640.00"
)
EXAMPLE_EXTRACTIONS: tuple[tuple[str, str], ...] = (
    ("document_type", "PURCHASE ORDER"),
    ("reference_id", "PO-2231"),
    ("date", "2023-11-02"),
    ("organization", "Tailwind Traders"),
    ("organization", "Coho Winery"),
    ("person", "Ana Silva"),
    ("amount", "$640.00"),
)


# ---------------------------------------------------------------------------
# Baseline: project generate_structured
# ---------------------------------------------------------------------------


class _Item(pydantic.BaseModel):
    entity_class: str
    text: str


class ExtractionSchema(pydantic.BaseModel):
    """Structured-output schema for the baseline extractor."""

    extractions: list[_Item]


def baseline_prompt(text: str) -> str:
    """Render the baseline prompt (task + one worked example + document)."""
    example = json.dumps(
        {"extractions": [{"entity_class": c, "text": t} for c, t in EXAMPLE_EXTRACTIONS]}
    )
    return (
        f"{TASK_DESCRIPTION}\n\nEXAMPLE TEXT:\n{EXAMPLE_TEXT}\n\n"
        f"EXAMPLE OUTPUT:\n{example}\n\nTEXT:\n{text}\n"
    )


class BaselineExtractor:
    """Current project approach: one structured-JSON call per document."""

    name = "baseline_generate_structured"

    def __init__(self, model: FoBaseModel, temperature: float, max_tokens: int) -> None:
        """Wrap an initialized project model."""
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def run(self, case: EvalCase) -> CaseResult:
        """Extract entities from ``case`` and time it."""
        t0 = time.perf_counter()
        try:
            parsed = self._model.generate_structured(
                baseline_prompt(case.text),
                schema=ExtractionSchema,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception as exc:  # scored as a failed case, never fatal
            return CaseResult(case.case_id, [], time.perf_counter() - t0, 1, repr(exc))
        assert isinstance(parsed, ExtractionSchema)
        preds = [Prediction(i.entity_class, i.text) for i in parsed.extractions]
        return CaseResult(case.case_id, preds, time.perf_counter() - t0, 1)


# ---------------------------------------------------------------------------
# langextract
# ---------------------------------------------------------------------------


def _lx() -> Any:
    try:
        import langextract
    except ImportError as exc:  # pragma: no cover - exercised manually
        raise SystemExit(
            'langextract is not installed. Install the eval extra: pip install -e ".[eval]"'
        ) from exc
    return langextract


def make_adapter(model: FoBaseModel, temperature: float, max_tokens: int) -> Any:
    """Return a langextract ``BaseLanguageModel`` backed by a project model.

    The class is built lazily so importing this module never needs
    langextract.
    """
    from langextract.core import exceptions as lx_exceptions
    from langextract.core.base_model import BaseLanguageModel
    from langextract.core.types import ScoredOutput

    class FileOrganizerLanguageModel(BaseLanguageModel):
        """Routes langextract inference through ``file_organizer`` models."""

        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def infer(
            self, batch_prompts: Sequence[str], **kwargs: Any
        ) -> Iterator[Sequence[ScoredOutput]]:
            for prompt in batch_prompts:
                self.calls += 1
                try:
                    text = model.generate(prompt, temperature=temperature, max_tokens=max_tokens)
                except Exception as exc:
                    raise lx_exceptions.InferenceRuntimeError(
                        f"file_organizer model error: {exc}", original=exc
                    ) from exc
                yield [ScoredOutput(score=1.0, output=text)]

    return FileOrganizerLanguageModel()


def make_native_ollama(model_id: str, temperature: float, url: str | None) -> Any:
    """Return langextract's built-in Ollama provider wrapped with a call counter."""
    from langextract.core.base_model import BaseLanguageModel
    from langextract.core.types import ScoredOutput
    from langextract.providers.ollama import OllamaLanguageModel

    inner = OllamaLanguageModel(
        model_id=model_id,
        model_url=url or "http://localhost:11434",
        temperature=temperature,
    )

    class CountingOllama(BaseLanguageModel):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        @property
        def requires_fence_output(self) -> bool:
            # JSON-mode decoding emits raw JSON, never fenced blocks.
            return False

        def infer(
            self, batch_prompts: Sequence[str], **kwargs: Any
        ) -> Iterator[Sequence[ScoredOutput]]:
            for prompt in batch_prompts:
                self.calls += 1
                yield from inner.infer([prompt], **kwargs)

    return CountingOllama()


class LangExtractExtractor:
    """``langextract.extract`` over a supplied langextract language model."""

    def __init__(
        self,
        name: str,
        lx_model: Any,
        *,
        max_char_buffer: int,
        extraction_passes: int,
        suppress_parse_errors: bool,
        context_window_chars: int | None = None,
    ) -> None:
        """Configure chunking, passes and resolver strictness."""
        self.name = name
        self._model = lx_model
        self._max_char_buffer = max_char_buffer
        self._passes = extraction_passes
        self._suppress = suppress_parse_errors
        self._context_window_chars = context_window_chars
        lx = _lx()
        self._examples = [
            lx.data.ExampleData(
                text=EXAMPLE_TEXT,
                extractions=[lx.data.Extraction(c, t) for c, t in EXAMPLE_EXTRACTIONS],
            )
        ]

    def run(self, case: EvalCase) -> CaseResult:
        """Extract entities from ``case`` and time it."""
        lx = _lx()
        calls_before = self._model.calls
        t0 = time.perf_counter()
        try:
            doc = lx.extract(
                case.text,
                prompt_description=TASK_DESCRIPTION,
                examples=self._examples,
                model=self._model,
                fence_output=self._model.requires_fence_output,
                use_schema_constraints=False,
                max_char_buffer=self._max_char_buffer,
                extraction_passes=self._passes,
                context_window_chars=self._context_window_chars,
                batch_length=1,
                max_workers=1,
                show_progress=False,
                fetch_urls=False,
                resolver_params={"suppress_parse_errors": self._suppress},
            )
        except Exception as exc:  # scored as a failed case, never fatal
            return CaseResult(
                case.case_id,
                [],
                time.perf_counter() - t0,
                self._model.calls - calls_before,
                repr(exc),
            )
        preds = []
        for ext in doc.extractions or []:
            ci = ext.char_interval
            preds.append(
                Prediction(
                    ext.extraction_class,
                    ext.extraction_text,
                    ci.start_pos if ci else None,
                    ci.end_pos if ci else None,
                    ext.alignment_status.value if ext.alignment_status else None,
                )
            )
        return CaseResult(
            case.case_id, preds, time.perf_counter() - t0, self._model.calls - calls_before
        )
