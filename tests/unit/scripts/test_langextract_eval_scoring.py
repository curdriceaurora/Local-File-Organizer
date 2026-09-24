"""Unit tests for the langextract evaluation corpus, scoring and baseline path.

None of these need langextract installed; see
test_langextract_eval_pipeline.py for the langextract-backed checks.
"""

from __future__ import annotations

import pytest

from scripts.langextract_eval.corpus import CORPUS, ENTITY_CLASSES, GoldEntity, validate_corpus
from scripts.langextract_eval.extractors import BaselineExtractor
from scripts.langextract_eval.scoring import (
    CaseResult,
    ClassCounts,
    Prediction,
    grounded_only,
    in_source,
    match_counts,
    normalize,
    offset_ok,
    score_extractor,
)
from scripts.langextract_eval.stub import FABRICATED, OracleStubModel

pytestmark = pytest.mark.unit


def _strict(p: str, g: str) -> bool:
    return normalize(p) == normalize(g)


class TestCorpus:
    def test_corpus_is_valid(self) -> None:
        assert validate_corpus() == []

    def test_every_class_has_gold(self) -> None:
        present = {e.entity_class for c in CORPUS for e in c.gold}
        assert present == set(ENTITY_CLASSES)

    def test_corpus_exercises_chunking_and_empty_docs(self) -> None:
        # langextract's default max_char_buffer is 1000 chars.
        assert any(len(c.text) > 1000 for c in CORPUS)
        assert any(not c.gold for c in CORPUS)

    def test_validate_flags_bad_spans(self) -> None:
        bad = CORPUS[0].__class__("x", "plain_text", "abc", (GoldEntity("person", "zzz"),))
        assert validate_corpus((bad,)) == ["x: gold span 'zzz' not in text"]


class TestNormalizeAndMatch:
    def test_normalize(self) -> None:
        assert normalize("  Acme   Corp. ") == "acme corp"
        assert normalize("$8,500.00") == "$8,500.00"
        assert normalize('"Tenant"') == "tenant"

    def test_duplicates_are_false_positives(self) -> None:
        gold = [GoldEntity("organization", "Acme Corp")]
        preds = [Prediction("organization", "Acme Corp"), Prediction("organization", "acme corp")]
        counts = match_counts(preds, gold, _strict)
        assert (counts["organization"].tp, counts["organization"].fp) == (1, 1)

    def test_class_mismatch_is_fp_and_fn(self) -> None:
        gold = [GoldEntity("person", "Acme Corp")]
        counts = match_counts([Prediction("organization", "Acme Corp")], gold, _strict)
        assert counts["organization"].fp == 1
        assert counts["person"].fn == 1

    def test_class_counts_edges(self) -> None:
        empty = ClassCounts()
        assert (empty.precision, empty.recall) == (1.0, 1.0)
        assert ClassCounts(tp=0, fp=1, fn=1).f1 == 0.0

    def test_in_source_and_offsets(self) -> None:
        src = "Bill to:  Globex\nIndustries"
        assert in_source("globex industries", src)
        assert not in_source("Initech", src)
        assert offset_ok(Prediction("organization", "Globex", 10, 16), src)
        assert not offset_ok(Prediction("organization", "Globex", 0, 4), src)
        assert not offset_ok(Prediction("organization", "Globex"), src)


class TestScoreExtractor:
    def test_lenient_credits_containment(self) -> None:
        case = CORPUS[0]  # invoice_plain
        preds = [Prediction("reference_id", "Invoice #INV-4821")]
        score = score_extractor("x", [case], [CaseResult(case.case_id, preds, 1.0, 1)])
        assert score.strict.tp == 0
        assert score.lenient.tp == 1
        assert score.verbatim_rate == 1.0

    def test_errors_are_recorded_and_gold_counts_as_missed(self) -> None:
        case = CORPUS[0]
        res = CaseResult(case.case_id, [], 2.0, 1, error="boom")
        score = score_extractor("x", [case], [res])
        assert score.failed_cases == [case.case_id]
        assert score.strict.fn == len(case.gold)
        assert score.to_dict()["seconds_per_case"] == 2.0


class TestGroundedOnly:
    def test_drops_unaligned_predictions_only(self) -> None:
        case = CORPUS[0]
        res = CaseResult(
            case.case_id,
            [
                Prediction("organization", "Acme Corp", 42, 51, "match_exact"),
                Prediction("person", "Ana Silva"),  # unaligned: not in the text
            ],
            1.0,
            1,
        )
        (kept,) = grounded_only([res])
        assert [p.text for p in kept.predictions] == ["Acme Corp"]
        assert (kept.case_id, kept.seconds, kept.llm_calls) == (case.case_id, 1.0, 1)


class TestBaselineWithStub:
    def test_baseline_end_to_end(self) -> None:
        model = OracleStubModel()
        model.initialize()
        extractor = BaselineExtractor(model, temperature=0.0, max_tokens=512)
        results = [extractor.run(c) for c in CORPUS]
        model.safe_cleanup()

        assert all(r.error is None for r in results)
        score = score_extractor(extractor.name, CORPUS, results)
        # Oracle returns every gold span, so recall is perfect ...
        assert score.strict.recall == 1.0
        # ... and the one fabricated entity per call is never in the source.
        fabricated = sum(
            1 for r in results for p in r.predictions if (p.entity_class, p.text) == FABRICATED
        )
        assert fabricated == len(CORPUS)
        assert score.predictions - score.verbatim == fabricated
