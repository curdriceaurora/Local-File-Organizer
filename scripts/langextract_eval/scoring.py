"""Scoring for extraction runs.

Pure functions with no langextract dependency so they are unit-testable in CI.

Metrics:

- **strict** match: same class and identical text after :func:`normalize`.
- **lenient** match: same class and one normalized text contains the other
  (credits "Acme Corp" vs "Acme Corp." or "Invoice #INV-4821" vs "INV-4821").
- **verbatim rate**: share of predictions whose text occurs in the source
  (after whitespace/case normalization). The complement is the hallucination
  rate — spans the model produced that are not in the document.
- **offset accuracy**: of predictions carrying character offsets, the share
  where ``text[start:end]`` normalizes to the predicted text.
"""

from __future__ import annotations

import re
import string
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from scripts.langextract_eval.corpus import ENTITY_CLASSES, EvalCase, GoldEntity

_WS = re.compile(r"\s+")
_EDGE_PUNCT = string.punctuation.replace("$", "").replace("%", "") + "“”‘’«»"


@dataclass(frozen=True)
class Prediction:
    """One extraction produced by an extractor."""

    entity_class: str
    text: str
    char_start: int | None = None
    char_end: int | None = None
    alignment: str | None = None


@dataclass
class CaseResult:
    """Raw output of one extractor on one case."""

    case_id: str
    predictions: list[Prediction]
    seconds: float
    llm_calls: int
    error: str | None = None


@dataclass
class ClassCounts:
    """True positive / false positive / false negative counts."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: ClassCounts) -> None:
        """Accumulate ``other`` into this counter."""
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    @property
    def precision(self) -> float:
        """TP / (TP + FP); 1.0 when nothing was predicted."""
        denom = self.tp + self.fp
        return self.tp / denom if denom else 1.0

    @property
    def recall(self) -> float:
        """TP / (TP + FN); 1.0 when nothing was expected."""
        denom = self.tp + self.fn
        return self.tp / denom if denom else 1.0

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall."""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class ExtractorScore:
    """Aggregate metrics for one extractor across the corpus."""

    name: str
    strict: ClassCounts = field(default_factory=ClassCounts)
    lenient: ClassCounts = field(default_factory=ClassCounts)
    per_class: dict[str, ClassCounts] = field(default_factory=dict)
    predictions: int = 0
    verbatim: int = 0
    with_offsets: int = 0
    offsets_correct: int = 0
    alignment_counts: dict[str, int] = field(default_factory=dict)
    cases: int = 0
    failed_cases: list[str] = field(default_factory=list)
    seconds: float = 0.0
    llm_calls: int = 0

    @property
    def verbatim_rate(self) -> float:
        """Share of predictions found verbatim in the source text."""
        return self.verbatim / self.predictions if self.predictions else 1.0

    @property
    def offset_accuracy(self) -> float | None:
        """Share of offset-carrying predictions whose span matches the text."""
        return self.offsets_correct / self.with_offsets if self.with_offsets else None

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable summary."""

        def counts(c: ClassCounts) -> dict[str, float | int]:
            return {
                "tp": c.tp,
                "fp": c.fp,
                "fn": c.fn,
                "precision": round(c.precision, 4),
                "recall": round(c.recall, 4),
                "f1": round(c.f1, 4),
            }

        return {
            "name": self.name,
            "strict": counts(self.strict),
            "lenient": counts(self.lenient),
            "per_class_strict": {k: counts(v) for k, v in sorted(self.per_class.items())},
            "predictions": self.predictions,
            "verbatim_rate": round(self.verbatim_rate, 4),
            "offset_coverage": round(self.with_offsets / self.predictions, 4)
            if self.predictions
            else None,
            "offset_accuracy": None
            if self.offset_accuracy is None
            else round(self.offset_accuracy, 4),
            "alignment_counts": dict(sorted(self.alignment_counts.items())),
            "cases": self.cases,
            "failed_cases": self.failed_cases,
            "seconds_total": round(self.seconds, 3),
            "seconds_per_case": round(self.seconds / self.cases, 3) if self.cases else None,
            "llm_calls": self.llm_calls,
        }


def normalize(text: str) -> str:
    """Casefold, collapse whitespace and trim edge punctuation/quotes."""
    return _WS.sub(" ", text).strip().strip(_EDGE_PUNCT).strip().casefold()


def _strict_eq(pred: str, gold: str) -> bool:
    return normalize(pred) == normalize(gold)


def _lenient_eq(pred: str, gold: str) -> bool:
    p, g = normalize(pred), normalize(gold)
    return bool(p) and bool(g) and (p in g or g in p)


def match_counts(
    preds: Sequence[Prediction],
    gold: Sequence[GoldEntity],
    eq: Callable[[str, str], bool],
) -> dict[str, ClassCounts]:
    """Greedy one-to-one matching of predictions to gold, per class.

    Duplicate predictions of the same entity count as false positives, so an
    extractor cannot inflate recall by repeating itself.
    """
    out: dict[str, ClassCounts] = {}
    unmatched_gold = list(gold)
    for pred in preds:
        counts = out.setdefault(pred.entity_class, ClassCounts())
        hit = next(
            (
                g
                for g in unmatched_gold
                if g.entity_class == pred.entity_class and eq(pred.text, g.text)
            ),
            None,
        )
        if hit is None:
            counts.fp += 1
        else:
            counts.tp += 1
            unmatched_gold.remove(hit)
    for g in unmatched_gold:
        out.setdefault(g.entity_class, ClassCounts()).fn += 1
    return out


def in_source(pred_text: str, source: str) -> bool:
    """Whether ``pred_text`` occurs in ``source`` modulo case and whitespace."""
    needle = _WS.sub(" ", pred_text).strip().casefold()
    return bool(needle) and needle in _WS.sub(" ", source).casefold()


def offset_ok(pred: Prediction, source: str) -> bool:
    """Whether the prediction's character span reproduces its text."""
    if pred.char_start is None or pred.char_end is None:
        return False
    return normalize(source[pred.char_start : pred.char_end]) == normalize(pred.text)


def grounded_only(results: Iterable[CaseResult]) -> list[CaseResult]:
    """Keep only predictions langextract aligned to a source span.

    Models what production code would do with langextract output: drop
    anything that could not be located in the document.
    """
    return [
        CaseResult(
            r.case_id,
            [p for p in r.predictions if p.char_start is not None],
            r.seconds,
            r.llm_calls,
            r.error,
        )
        for r in results
    ]


def score_extractor(
    name: str, cases: Iterable[EvalCase], results: Iterable[CaseResult]
) -> ExtractorScore:
    """Aggregate :class:`CaseResult` objects into an :class:`ExtractorScore`."""
    by_id = {c.case_id: c for c in cases}
    score = ExtractorScore(name=name, per_class={k: ClassCounts() for k in ENTITY_CLASSES})
    for res in results:
        case = by_id[res.case_id]
        score.cases += 1
        score.seconds += res.seconds
        score.llm_calls += res.llm_calls
        if res.error is not None:
            score.failed_cases.append(res.case_id)
        for cls, counts in match_counts(res.predictions, case.gold, _strict_eq).items():
            score.strict.add(counts)
            score.per_class.setdefault(cls, ClassCounts()).add(counts)
        for counts in match_counts(res.predictions, case.gold, _lenient_eq).values():
            score.lenient.add(counts)
        for pred in res.predictions:
            score.predictions += 1
            score.verbatim += in_source(pred.text, case.text)
            key = pred.alignment or "none"
            score.alignment_counts[key] = score.alignment_counts.get(key, 0) + 1
            if pred.char_start is not None and pred.char_end is not None:
                score.with_offsets += 1
                score.offsets_correct += offset_ok(pred, case.text)
    return score
