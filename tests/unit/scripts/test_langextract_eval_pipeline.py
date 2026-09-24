"""langextract-backed checks for the evaluation harness (needs the eval extra)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.langextract_eval.corpus import CORPUS
from scripts.langextract_eval.scoring import score_extractor
from scripts.langextract_eval.stub import FABRICATED, OracleStubModel

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _require_langextract() -> None:
    pytest.importorskip("langextract")


@pytest.fixture
def stub_model() -> OracleStubModel:
    model = OracleStubModel()
    model.initialize()
    return model


class TestAdapterPipeline:
    def test_grounding_via_adapter(self, stub_model: OracleStubModel) -> None:
        from scripts.langextract_eval.extractors import LangExtractExtractor, make_adapter

        lm = make_adapter(stub_model, temperature=0.0, max_tokens=512)
        extractor = LangExtractExtractor(
            "lx", lm, max_char_buffer=1000, extraction_passes=1, suppress_parse_errors=False
        )
        results = [extractor.run(c) for c in CORPUS]

        assert all(r.error is None for r in results), [r.error for r in results if r.error]
        long_case = next(r for r in results if r.case_id == "long_vendor_report")
        assert long_case.llm_calls > 1, "long document should be chunked"

        score = score_extractor("lx", CORPUS, results)
        assert score.offset_accuracy == 1.0
        fabricated = [
            p for r in results for p in r.predictions if (p.entity_class, p.text) == FABRICATED
        ]
        assert fabricated
        # langextract cannot ground a span that is not in the text.
        assert all(p.char_start is None and p.alignment is None for p in fabricated)

    def test_model_errors_are_scored_not_raised(self, stub_model: OracleStubModel) -> None:
        from scripts.langextract_eval.extractors import LangExtractExtractor, make_adapter

        stub_model.safe_cleanup()  # generate() now raises
        lm = make_adapter(stub_model, temperature=0.0, max_tokens=512)
        extractor = LangExtractExtractor(
            "lx", lm, max_char_buffer=1000, extraction_passes=1, suppress_parse_errors=False
        )
        result = extractor.run(CORPUS[0])
        assert result.error is not None
        assert result.predictions == []


class TestCli:
    def test_stub_run_writes_reports(self, tmp_path: Path) -> None:
        from scripts.langextract_eval.__main__ import main

        out = tmp_path / "run"
        code = main(
            [
                "--backend",
                "stub",
                "--extractors",
                "baseline,lx-adapter,lx-native",
                "--cases",
                "invoice_plain,long_vendor_report",
                "--output-dir",
                str(out),
            ]
        )
        assert code == 0
        payload = json.loads((out / "results.json").read_text(encoding="utf-8"))
        # lx-native is dropped for non-Ollama backends.
        assert [s["name"] for s in payload["scores"]] == [
            "baseline_generate_structured",
            "langextract_adapter",
            "langextract_adapter+grounded",
        ]
        assert payload["meta"]["versions"]["langextract"]
        assert "Stub run" in (out / "report.md").read_text(encoding="utf-8")

    def test_rescore_reproduces_scores(self, tmp_path: Path) -> None:
        from scripts.langextract_eval.__main__ import main

        run = tmp_path / "run"
        assert (
            main(["--backend", "stub", "--cases", "invoice_plain", "--output-dir", str(run)]) == 0
        )
        first = json.loads((run / "results.json").read_text(encoding="utf-8"))["scores"]
        names = [s["name"] for s in first]
        assert "langextract_adapter+grounded" in names

        again = tmp_path / "again"
        code = main(["--rescore", str(run / "results.json"), "--output-dir", str(again)])
        assert code == 0
        assert json.loads((again / "results.json").read_text(encoding="utf-8"))["scores"] == first

    def test_unknown_case_is_rejected(self, tmp_path: Path) -> None:
        from scripts.langextract_eval.__main__ import main

        with pytest.raises(SystemExit, match="unknown case_id"):
            main(["--backend", "stub", "--cases", "nope", "--output-dir", str(tmp_path)])
