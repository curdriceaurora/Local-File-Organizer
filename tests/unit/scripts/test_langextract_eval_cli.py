"""Unit tests for evaluation orchestration that do not need the eval extra."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.langextract_eval import __main__ as evaluation
from scripts.langextract_eval.corpus import CORPUS, EvalCase
from scripts.langextract_eval.scoring import CaseResult, Prediction

pytestmark = pytest.mark.unit


def test_case_selection_preserves_corpus_order_and_rejects_unknown_ids() -> None:
    requested = "long_vendor_report, invoice_plain,invoice_plain"
    selected = evaluation._select_cases(requested)

    assert [case.case_id for case in selected] == ["invoice_plain", "long_vendor_report"]
    with pytest.raises(SystemExit, match=r"unknown case_id\(s\): missing, other"):
        evaluation._select_cases("other,missing")


def test_missing_eval_extra_stops_before_model_initialization(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(evaluation, "_version", lambda _name: None)

    def unexpected_model(_args: object) -> None:
        pytest.fail("model initialized without the eval extra")

    monkeypatch.setattr(evaluation, "_make_project_model", unexpected_model)

    assert evaluation.main(["--backend", "stub"]) == 3
    assert "langextract is not installed" in capsys.readouterr().err


def test_build_extractors_forwards_langextract_options(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.langextract_eval import extractors

    model = object()
    adapter = object()
    constructed: list[tuple[str, object, dict[str, object]]] = []

    monkeypatch.setattr(extractors, "make_adapter", lambda *_args: adapter)

    def capture(name: str, lm: object, **options: object) -> object:
        constructed.append((name, lm, options))
        return object()

    monkeypatch.setattr(extractors, "LangExtractExtractor", capture)
    args = evaluation._parse_args(
        [
            "--backend",
            "stub",
            "--extractors",
            "baseline,lx-adapter",
            "--max-char-buffer",
            "300",
            "--passes",
            "2",
            "--context-window-chars",
            "100",
            "--suppress-parse-errors",
        ]
    )

    built = evaluation._build_extractors(args, model)

    assert len(built) == 2
    assert built[0].name == evaluation.BASELINE_NAME
    assert constructed == [
        (
            "langextract_adapter",
            adapter,
            {
                "max_char_buffer": 300,
                "extraction_passes": 2,
                "suppress_parse_errors": True,
                "context_window_chars": 100,
            },
        )
    ]


def test_main_warms_model_once_then_runs_all_repeats_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []

    class Model:
        def generate(self, prompt: str, **kwargs: object) -> str:
            assert prompt == "Reply with OK."
            assert kwargs == {"max_tokens": 4}
            events.append("warmup")
            return "OK"

        def safe_cleanup(self) -> None:
            events.append("cleanup")

    model = Model()

    class Extractor:
        name = evaluation.BASELINE_NAME

        def run(self, case: EvalCase) -> CaseResult:
            events.append(case.case_id)
            return CaseResult(
                case.case_id,
                [Prediction(g.entity_class, g.text) for g in case.gold],
                0.25,
                1,
            )

    monkeypatch.setattr(evaluation, "_version", lambda _name: "test")
    monkeypatch.setattr(evaluation, "_make_project_model", lambda _args: model)
    monkeypatch.setattr(evaluation, "_build_extractors", lambda _args, _model: [Extractor()])
    out_dir = tmp_path / "run"

    assert (
        evaluation.main(
            [
                "--backend",
                "stub",
                "--cases",
                "invoice_plain,long_vendor_report",
                "--repeats",
                "2",
                "--extractors",
                "baseline",
                "--output-dir",
                str(out_dir),
            ]
        )
        == 0
    )

    assert events == [
        "warmup",
        "invoice_plain",
        "long_vendor_report",
        "invoice_plain",
        "long_vendor_report",
        "cleanup",
    ]
    payload = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    assert (payload["meta"]["cases"], payload["meta"]["repeats"]) == (2, 2)
    assert len(payload["results"][evaluation.BASELINE_NAME]) == 4
    assert payload["scores"][0]["llm_calls"] == 4


def test_main_cleans_up_when_extractor_setup_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cleaned_up: list[bool] = []

    class Model:
        def generate(self, _prompt: str, **_kwargs: object) -> str:
            return "OK"

        def safe_cleanup(self) -> None:
            cleaned_up.append(True)

    monkeypatch.setattr(evaluation, "_version", lambda _name: "test")
    monkeypatch.setattr(evaluation, "_make_project_model", lambda _args: Model())

    def fail_setup(_args: object, _model: object) -> None:
        raise RuntimeError("extractor setup failed")

    monkeypatch.setattr(evaluation, "_build_extractors", fail_setup)

    with pytest.raises(RuntimeError, match="extractor setup failed"):
        evaluation.main(["--backend", "stub", "--output-dir", str(tmp_path)])
    assert cleaned_up == [True]


def test_rescore_drops_stale_case_present_in_only_one_extractor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case = CORPUS[0]
    valid = {
        "case_id": case.case_id,
        "predictions": [{"entity_class": case.gold[0].entity_class, "text": case.gold[0].text}],
        "seconds": 0.1,
        "llm_calls": 1,
        "error": None,
    }
    stale = {**valid, "case_id": "retired_case"}
    saved = tmp_path / "saved.json"
    saved.write_text(
        json.dumps(
            {
                "meta": {
                    "started_utc": "2026-09-25T00:00:00+00:00",
                    "backend": "stub",
                    "model": "oracle-stub",
                    "cases": 2,
                    "repeats": 1,
                    "temperature": 0.0,
                    "max_char_buffer": 1000,
                    "passes": 1,
                    "suppress_parse_errors": False,
                    "versions": {"langextract": "test"},
                },
                "results": {
                    evaluation.BASELINE_NAME: [valid, stale],
                    "langextract_adapter": [valid],
                },
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "rescored"

    assert evaluation.rescore(saved, out_dir) == 0

    assert "retired_case" in capsys.readouterr().err
    result = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    assert {
        name: [item["case_id"] for item in rows] for name, rows in result["results"].items()
    } == {
        evaluation.BASELINE_NAME: [case.case_id],
        "langextract_adapter": [case.case_id],
    }
    assert all(score["cases"] == 1 for score in result["scores"])
    assert len(result["comparisons"]) == 2  # raw and grounded adapter scores
    assert (
        len(json.loads(saved.read_text(encoding="utf-8"))["results"][evaluation.BASELINE_NAME]) == 2
    )
