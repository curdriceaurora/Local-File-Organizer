"""Tests for AIHeuristic — Ollama-based PARA classification.

All tests mock the ollama dependency so no running Ollama instance is required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import AIHeuristicConfig
from file_organizer.methodologies.para.detection.heuristics import (
    AIHeuristic,
    HeuristicEngine,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEURISTICS_MODULE = "file_organizer.methodologies.para.detection.heuristics"


def _make_ollama_response(scores: dict[str, float], reasoning: str = "test") -> dict[str, Any]:
    """Build a fake ollama generate() response dict."""
    payload = {**scores, "reasoning": reasoning}
    return {"response": json.dumps(payload)}


def _make_heuristic(*, available: bool = True) -> tuple[AIHeuristic, MagicMock]:
    """Create an AIHeuristic with a pre-configured mock client.

    Returns:
        (heuristic, mock_client) tuple.
    """
    h = AIHeuristic(weight=0.10)
    mock_client = MagicMock()
    h._client = mock_client
    h._available = available
    return h, mock_client


# ---------------------------------------------------------------------------
# Tests: unavailability paths
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestAIHeuristicUnavailable:
    """Tests for graceful degradation when Ollama is not available."""

    def test_ollama_not_installed(self, tmp_path: Path) -> None:
        """When the ollama package is not importable, return zero scores."""
        h = AIHeuristic(weight=0.10)
        test_file = tmp_path / "notes.txt"
        test_file.write_text("project deadline tomorrow")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", False):
            result = h.evaluate(test_file)

        assert result.overall_confidence == 0.0
        assert result.recommended_category is None
        assert result.needs_manual_review is True
        assert result.metadata["ai_analysis"] == "ollama_not_installed"
        assert result.abstained is True
        for score in result.scores.values():
            assert score.score == 0.0

    def test_ollama_unavailable_connection_error(self, tmp_path: Path) -> None:
        """When Ollama server is unreachable, return zero scores."""
        h = AIHeuristic(weight=0.10)
        test_file = tmp_path / "notes.txt"
        test_file.write_text("some content")

        # Force _available to None so _ensure_client runs, then make it fail
        h._available = None
        with (
            patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True),
            patch(f"{_HEURISTICS_MODULE}.ollama") as mock_ollama,
        ):
            mock_ollama.Client.return_value.list.side_effect = ConnectionError("refused")
            result = h.evaluate(test_file)

        assert result.metadata["ai_analysis"] == "ollama_unavailable"
        assert result.overall_confidence == 0.0
        assert result.abstained is True

    def test_generate_exception_returns_zero(self, tmp_path: Path) -> None:
        """When generate() raises, return zero scores with ollama_error."""
        h, mock_client = _make_heuristic()
        mock_client.generate.side_effect = RuntimeError("model not found")
        test_file = tmp_path / "notes.txt"
        test_file.write_text("content")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            result = h.evaluate(test_file)

        mock_client.generate.assert_called_once()
        assert result.metadata["ai_analysis"] == "ollama_error"
        assert result.overall_confidence == 0.0
        assert result.abstained is True


# ---------------------------------------------------------------------------
# Tests: successful classification
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestAIHeuristicClassification:
    """Tests for successful LLM-based PARA classification."""

    def test_successful_classification(self, tmp_path: Path) -> None:
        """Valid JSON response produces correct CategoryScore mapping."""
        h, mock_client = _make_heuristic()
        scores = {"project": 0.7, "area": 0.1, "resource": 0.15, "archive": 0.05}
        mock_client.generate.return_value = _make_ollama_response(scores, "deadline soon")
        test_file = tmp_path / "proposal.txt"
        test_file.write_text("Project proposal with deadline next week")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            result = h.evaluate(test_file)

        mock_client.generate.assert_called_once()
        assert result.metadata["ai_analysis"] == "complete"
        assert result.recommended_category == PARACategory.PROJECT
        # Scores are normalised — project should be highest
        assert result.scores[PARACategory.PROJECT].score > result.scores[PARACategory.AREA].score
        assert result.overall_confidence > 0.0
        # Reasoning should appear in the top-scoring category's signals
        top_signals = result.scores[PARACategory.PROJECT].signals
        assert any("deadline soon" in s for s in top_signals)

    def test_malformed_response_fallback(self, tmp_path: Path) -> None:
        """Garbage LLM output produces zero scores with parse_error."""
        h, mock_client = _make_heuristic()
        mock_client.generate.return_value = {"response": "I cannot classify this file."}
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            result = h.evaluate(test_file)

        mock_client.generate.assert_called_once()
        assert result.metadata["ai_analysis"] == "parse_error"
        assert result.overall_confidence == 0.0
        assert result.abstained is True

    def test_json_with_markdown_fences(self, tmp_path: Path) -> None:
        """Parser correctly strips markdown code fences from response."""
        h, mock_client = _make_heuristic()
        json_body = json.dumps(
            {"project": 0.1, "area": 0.6, "resource": 0.2, "archive": 0.1, "reasoning": "ongoing"}
        )
        fenced = f"```json\n{json_body}\n```"
        mock_client.generate.return_value = {"response": fenced}
        test_file = tmp_path / "budget.xlsx"
        test_file.write_bytes(bytes(range(256)))  # invalid UTF-8; decoded with replacement chars

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            result = h.evaluate(test_file)

        mock_client.generate.assert_called_once()
        assert result.metadata["ai_analysis"] == "complete"
        assert result.recommended_category == PARACategory.AREA

    def test_score_normalization(self, tmp_path: Path) -> None:
        """Scores that do not sum to 1.0 are normalised."""
        h, mock_client = _make_heuristic()
        # Scores sum to 2.0
        scores = {"project": 0.8, "area": 0.6, "resource": 0.4, "archive": 0.2}
        mock_client.generate.return_value = _make_ollama_response(scores)
        test_file = tmp_path / "readme.md"
        test_file.write_text("# README")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            result = h.evaluate(test_file)

        total = sum(s.score for s in result.scores.values())
        assert abs(total - 1.0) < 0.01

    def test_confidence_damping(self, tmp_path: Path) -> None:
        """Overall confidence is damped by the _CONFIDENCE_DAMPING factor."""
        h, mock_client = _make_heuristic()
        scores = {"project": 0.9, "area": 0.05, "resource": 0.03, "archive": 0.02}
        mock_client.generate.return_value = _make_ollama_response(scores)
        test_file = tmp_path / "sprint.md"
        test_file.write_text("Sprint planning")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            result = h.evaluate(test_file)

        # After normalisation max_score = 0.9/1.0 = 0.9, damped = 0.9 * 0.8 = 0.72
        assert result.overall_confidence == pytest.approx(0.72, abs=0.05)


# ---------------------------------------------------------------------------
# Tests: content extraction
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestAIHeuristicContent:
    """Tests for file content extraction."""

    def test_binary_file_uses_metadata(self, tmp_path: Path) -> None:
        """Binary files fall back to path/metadata description in prompt."""
        h, mock_client = _make_heuristic()
        scores = {"project": 0.1, "area": 0.1, "resource": 0.7, "archive": 0.1}
        mock_client.generate.return_value = _make_ollama_response(scores)
        test_file = tmp_path / "image.png"
        # PNG signature (0x89 is invalid UTF-8) + null bytes (>30% control chars)
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            result = h.evaluate(test_file, metadata={"type": "image", "size": "2MB"})

        mock_client.generate.assert_called_once()
        assert result.metadata["ai_analysis"] == "complete"
        # Verify the prompt used the binary fallback marker (not raw mojibake)
        call_args = mock_client.generate.call_args
        prompt = call_args.kwargs.get("prompt", "")
        assert "[Binary or unreadable file: image.png]" in prompt
        assert "type: image" in prompt

    def test_utf8_text_not_treated_as_binary(self, tmp_path: Path) -> None:
        """Valid UTF-8 text with multibyte characters must not be misclassified as binary."""
        h, mock_client = _make_heuristic()
        mock_client.generate.return_value = _make_ollama_response(
            {"project": 0.4, "area": 0.3, "resource": 0.2, "archive": 0.1}
        )
        test_file = tmp_path / "notes.txt"
        test_file.write_text("日本語の会議メモ", encoding="utf-8")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            h.evaluate(test_file)

        mock_client.generate.assert_called_once()
        prompt = mock_client.generate.call_args.kwargs["prompt"]
        assert "[Binary or unreadable file:" not in prompt
        assert "日本語の会議メモ" in prompt


# ---------------------------------------------------------------------------
# Tests: config propagation
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestAIHeuristicConfig:
    """Tests for configuration propagation."""

    def test_config_propagation(self, tmp_path: Path) -> None:
        """Custom config values are passed to ollama generate()."""
        config = AIHeuristicConfig(
            model="llama3:8b",
            temperature=0.1,
            max_tokens=100,
        )
        h = AIHeuristic(weight=0.10, config=config)
        mock_client = MagicMock()
        h._client = mock_client
        h._available = True

        scores = {"project": 0.25, "area": 0.25, "resource": 0.25, "archive": 0.25}
        mock_client.generate.return_value = _make_ollama_response(scores)
        test_file = tmp_path / "doc.txt"
        test_file.write_text("test content")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            h.evaluate(test_file)

        call_kwargs = mock_client.generate.call_args
        assert call_kwargs.kwargs["model"] == "llama3:8b"
        assert call_kwargs.kwargs["options"]["temperature"] == 0.1
        assert call_kwargs.kwargs["options"]["num_predict"] == 100
        assert call_kwargs.kwargs["system"] == AIHeuristic._SYSTEM_MESSAGE


# ---------------------------------------------------------------------------
# Tests: HeuristicEngine integration
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestAIHeuristicEngineIntegration:
    """Tests for AIHeuristic integration with HeuristicEngine."""

    def test_engine_with_ai_enabled(self, tmp_path: Path) -> None:
        """HeuristicEngine includes AI heuristic when enable_ai=True."""
        test_file = tmp_path / "project_plan.txt"
        test_file.write_text("Sprint 1 deliverables and deadlines")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", False):
            engine = HeuristicEngine(
                enable_temporal=True,
                enable_content=True,
                enable_structural=True,
                enable_ai=True,
            )
            result = engine.evaluate(test_file)

        # AI heuristic should be present but return zero scores (ollama not installed)
        ai_heuristics = [h for h in engine.heuristics if isinstance(h, AIHeuristic)]
        assert len(ai_heuristics) == 1
        assert ai_heuristics[0].weight == 0.10
        # Engine should still produce a result from the other heuristics
        assert result is not None

    def test_engine_passes_ai_config(self) -> None:
        """HeuristicEngine passes ai_config to AIHeuristic."""
        config = AIHeuristicConfig(model="custom:model")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", False):
            engine = HeuristicEngine(enable_ai=True, ai_config=config)

        ai_heuristics = [h for h in engine.heuristics if isinstance(h, AIHeuristic)]
        assert len(ai_heuristics) == 1
        assert ai_heuristics[0].config.model == "custom:model"

    def test_abstained_ai_does_not_dilute_scores(self, tmp_path: Path) -> None:
        """When AI abstains (Ollama unavailable), its 0.10 weight is excluded
        from the denominator so other heuristic scores are not scaled down."""
        test_file = tmp_path / "project_brief.txt"
        test_file.write_text("Sprint 1 deliverables and deadlines")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", False):
            engine_with_ai = HeuristicEngine(
                enable_temporal=True,
                enable_content=True,
                enable_structural=True,
                enable_ai=True,
            )
            engine_without_ai = HeuristicEngine(
                enable_temporal=True,
                enable_content=True,
                enable_structural=True,
                enable_ai=False,
            )
            result_with = engine_with_ai.evaluate(test_file)
            result_without = engine_without_ai.evaluate(test_file)

        # Scores must be identical — abstained AI must not reduce other scores
        for cat in result_with.scores:
            assert result_with.scores[cat].score == pytest.approx(
                result_without.scores[cat].score, abs=1e-9
            ), f"Score mismatch for {cat}: abstained AI diluted result"


# ---------------------------------------------------------------------------
# Tests: system/user message split
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestAIHeuristicPromptSplit:
    """Tests that generate() uses separate system and user messages."""

    def test_system_kwarg_contains_para_instructions(self, tmp_path: Path) -> None:
        """generate() is called with system kwarg containing static PARA text."""
        h, mock_client = _make_heuristic()
        scores = {"project": 0.5, "area": 0.2, "resource": 0.2, "archive": 0.1}
        mock_client.generate.return_value = _make_ollama_response(scores)
        test_file = tmp_path / "doc.txt"
        test_file.write_text("some content")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            h.evaluate(test_file)

        call_kwargs = mock_client.generate.call_args.kwargs
        assert "system" in call_kwargs
        system = call_kwargs["system"]
        assert "PARA methodology" in system
        assert "PROJECT" in system
        assert "AREA" in system
        assert "RESOURCE" in system
        assert "ARCHIVE" in system
        assert "{file_path}" not in system
        assert "{content}" not in system

    def test_prompt_kwarg_contains_only_file_specific_content(self, tmp_path: Path) -> None:
        """generate() prompt kwarg contains file context, not PARA instructions."""
        h, mock_client = _make_heuristic()
        scores = {"project": 0.5, "area": 0.2, "resource": 0.2, "archive": 0.1}
        mock_client.generate.return_value = _make_ollama_response(scores)
        test_file = tmp_path / "report.txt"
        test_file.write_text("quarterly revenue figures")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            h.evaluate(test_file)

        call_kwargs = mock_client.generate.call_args.kwargs
        prompt = call_kwargs["prompt"]
        assert "report.txt" in prompt
        assert "quarterly revenue figures" in prompt
        assert "PARA methodology" not in prompt
        assert "You are a file organization assistant" not in prompt

    def test_engine_integration_system_prompt_split(self, tmp_path: Path) -> None:
        """HeuristicEngine passes system+prompt split through full evaluation pipeline."""
        test_file = tmp_path / "sprint_plan.txt"
        test_file.write_text("Sprint 2 deliverables")
        scores = {"project": 0.7, "area": 0.1, "resource": 0.15, "archive": 0.05}

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            engine = HeuristicEngine(enable_ai=True)
            ai_h = next(h for h in engine.heuristics if isinstance(h, AIHeuristic))
            mock_client = MagicMock()
            mock_client.generate.return_value = _make_ollama_response(scores)
            ai_h._client = mock_client
            ai_h._available = True

            result = engine.evaluate(test_file)

        assert result is not None
        call_kwargs = mock_client.generate.call_args.kwargs
        assert "system" in call_kwargs
        assert "PROJECT" in call_kwargs["system"]
        assert "sprint_plan.txt" in call_kwargs["prompt"]

    def test_system_message_contains_valid_json_example(self) -> None:
        """_SYSTEM_MESSAGE JSON example uses single braces, not escaped doubles."""
        assert "{{" not in AIHeuristic._SYSTEM_MESSAGE
        assert "}}" not in AIHeuristic._SYSTEM_MESSAGE
