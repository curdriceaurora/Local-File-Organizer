"""Unit tests for the evaluation extractors and model adapters."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from scripts.langextract_eval import extractors
from scripts.langextract_eval.corpus import CORPUS
from scripts.langextract_eval.scoring import Prediction

pytestmark = pytest.mark.unit


def test_baseline_forwards_prompt_schema_and_generation_options() -> None:
    case = CORPUS[0]
    calls: list[tuple[str, dict[str, Any]]] = []

    class Model:
        def generate_structured(self, prompt: str, **kwargs: Any) -> Any:
            calls.append((prompt, kwargs))
            return kwargs["schema"](
                extractions=[{"entity_class": "reference_id", "text": "INV-4821"}]
            )

    result = extractors.BaselineExtractor(Model(), temperature=0.25, max_tokens=128).run(case)

    assert result.case_id == case.case_id
    assert result.predictions == [Prediction("reference_id", "INV-4821")]
    assert result.error is None
    assert result.llm_calls == 1
    assert result.seconds >= 0
    assert len(calls) == 1
    prompt, options = calls[0]
    assert prompt.endswith(f"TEXT:\n{case.text}\n")
    assert "EXAMPLE OUTPUT:" in prompt
    assert options == {
        "schema": extractors.ExtractionSchema,
        "temperature": 0.25,
        "max_tokens": 128,
    }


def test_baseline_scores_model_failure_as_one_attempt() -> None:
    class Model:
        def generate_structured(self, _prompt: str, **_kwargs: Any) -> None:
            raise RuntimeError("backend unavailable")

    result = extractors.BaselineExtractor(Model(), temperature=0, max_tokens=32).run(CORPUS[0])

    assert result.predictions == []
    assert result.llm_calls == 1
    assert result.error == "RuntimeError('backend unavailable')"


def test_adapter_returns_one_scored_output_per_prompt_and_counts_calls() -> None:
    pytest.importorskip("langextract")
    calls: list[tuple[str, dict[str, Any]]] = []

    class Model:
        def generate(self, prompt: str, **kwargs: Any) -> str:
            calls.append((prompt, kwargs))
            return f"answer to {prompt}"

    adapter = extractors.make_adapter(Model(), temperature=0.1, max_tokens=64)
    batches = list(adapter.infer(["first", "second"]))

    assert [[item.output for item in batch] for batch in batches] == [
        ["answer to first"],
        ["answer to second"],
    ]
    assert all(item.score == 1.0 for batch in batches for item in batch)
    assert adapter.calls == 2
    assert calls == [
        ("first", {"temperature": 0.1, "max_tokens": 64}),
        ("second", {"temperature": 0.1, "max_tokens": 64}),
    ]


def test_adapter_wraps_model_failure_and_counts_attempt() -> None:
    pytest.importorskip("langextract")
    from langextract.core.exceptions import InferenceRuntimeError

    failure = ValueError("bad response")

    class Model:
        def generate(self, _prompt: str, **_kwargs: Any) -> str:
            raise failure

    adapter = extractors.make_adapter(Model(), temperature=0, max_tokens=64)

    with pytest.raises(InferenceRuntimeError, match="file_organizer model error") as raised:
        list(adapter.infer(["first"]))
    assert raised.value.__cause__ is failure
    assert adapter.calls == 1


def test_langextract_maps_offsets_and_forwards_chunk_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    model = SimpleNamespace(calls=3, requires_fence_output=True)

    def fake_extract(text: str, **kwargs: Any) -> Any:
        captured.update(kwargs)
        captured["text"] = text
        model.calls += 2
        return SimpleNamespace(
            extractions=[
                SimpleNamespace(
                    extraction_class="organization",
                    extraction_text="Acme Corp",
                    char_interval=SimpleNamespace(start_pos=0, end_pos=9),
                    alignment_status=SimpleNamespace(value="match_exact"),
                ),
                SimpleNamespace(
                    extraction_class="person",
                    extraction_text="Invented Person",
                    char_interval=None,
                    alignment_status=None,
                ),
            ]
        )

    fake_lx = SimpleNamespace(
        data=SimpleNamespace(
            ExampleData=lambda **kwargs: SimpleNamespace(**kwargs),
            Extraction=lambda *args: args,
        ),
        extract=fake_extract,
    )
    monkeypatch.setattr(extractors, "_lx", lambda: fake_lx)
    extractor = extractors.LangExtractExtractor(
        "adapter",
        model,
        max_char_buffer=300,
        extraction_passes=2,
        suppress_parse_errors=True,
        context_window_chars=100,
    )

    result = extractor.run(CORPUS[0])

    assert result.predictions == [
        Prediction("organization", "Acme Corp", 0, 9, "match_exact"),
        Prediction("person", "Invented Person"),
    ]
    assert result.llm_calls == 2
    assert result.error is None
    assert captured["text"] == CORPUS[0].text
    assert captured["model"] is model
    assert captured["prompt_description"] == extractors.TASK_DESCRIPTION
    assert len(captured["examples"]) == 1
    assert captured["fence_output"] is True
    assert captured["max_char_buffer"] == 300
    assert captured["extraction_passes"] == 2
    assert captured["context_window_chars"] == 100
    assert captured["resolver_params"] == {"suppress_parse_errors": True}
    assert captured["batch_length"] == captured["max_workers"] == 1
    assert captured["fetch_urls"] is False


def test_langextract_scores_failed_extraction_with_attempted_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(calls=4, requires_fence_output=False)

    def fail_extract(_text: str, **_kwargs: Any) -> None:
        model.calls += 1
        raise RuntimeError("invalid extraction")

    fake_lx = SimpleNamespace(
        data=SimpleNamespace(ExampleData=lambda **kwargs: kwargs, Extraction=lambda *args: args),
        extract=fail_extract,
    )
    monkeypatch.setattr(extractors, "_lx", lambda: fake_lx)
    extractor = extractors.LangExtractExtractor(
        "adapter", model, max_char_buffer=1000, extraction_passes=1, suppress_parse_errors=False
    )

    result = extractor.run(CORPUS[0])

    assert result.predictions == []
    assert result.llm_calls == 1
    assert result.error == "RuntimeError('invalid extraction')"


@pytest.mark.parametrize("url", [None, "http://ollama.example:11434"])
def test_native_ollama_forwards_configuration_and_counts_calls(
    monkeypatch: pytest.MonkeyPatch, url: str | None
) -> None:
    pytest.importorskip("langextract")
    from langextract.core.types import ScoredOutput
    from langextract.providers import ollama

    instances: list[Any] = []

    class NativeModel:
        def __init__(self, **kwargs: Any) -> None:
            self.options = kwargs
            self.prompts: list[tuple[list[str], dict[str, Any]]] = []
            instances.append(self)

        def infer(self, prompts: list[str], **kwargs: Any) -> Any:
            self.prompts.append((prompts, kwargs))
            yield [ScoredOutput(score=0.5, output=prompts[0])]

    monkeypatch.setattr(ollama, "OllamaLanguageModel", NativeModel)
    native = extractors.make_native_ollama("model-id", 0.2, url)
    batches = list(native.infer(["first", "second"], retry_count=1))

    assert instances[0].options == {
        "model_id": "model-id",
        "model_url": url or "http://localhost:11434",
        "temperature": 0.2,
    }
    assert instances[0].prompts == [
        (["first"], {"retry_count": 1}),
        (["second"], {"retry_count": 1}),
    ]
    assert [[item.output for item in batch] for batch in batches] == [["first"], ["second"]]
    assert native.calls == 2
    assert native.requires_fence_output is False
