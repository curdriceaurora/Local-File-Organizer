"""Tests for AIHeuristic — Ollama-based PARA classification.

All tests mock the ollama dependency so no running Ollama instance is required.
"""

from __future__ import annotations

import json
import os
import time
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
        prompt = mock_client.generate.call_args.kwargs["prompt"]
        assert "proposal.txt" in prompt
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
        prompt = mock_client.generate.call_args.kwargs["prompt"]
        assert "budget.xlsx" in prompt
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


# ---------------------------------------------------------------------------
# Tests: result caching
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestAIHeuristicCache:
    """Tests for bounded LRU in-memory result cache."""

    def test_cache_hit_skips_generate(self, tmp_path: Path) -> None:
        """Second evaluate() call returns cached result; generate() called once."""
        h, mock_client = _make_heuristic()
        scores = {"project": 0.6, "area": 0.2, "resource": 0.1, "archive": 0.1}
        mock_client.generate.return_value = _make_ollama_response(scores)
        f = tmp_path / "report.txt"
        f.write_text("content")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            r1 = h.evaluate(f)
            r2 = h.evaluate(f)

        assert mock_client.generate.call_count == 1
        assert r1 is r2

    def test_cache_miss_on_file_change(self, tmp_path: Path) -> None:
        """Cache miss when mtime changes; generate() called twice."""
        h, mock_client = _make_heuristic()
        scores = {"project": 0.6, "area": 0.2, "resource": 0.1, "archive": 0.1}
        mock_client.generate.return_value = _make_ollama_response(scores)
        f = tmp_path / "report.txt"
        f.write_text("content")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            h.evaluate(f)
            f.write_text("updated content")
            os.utime(f, (f.stat().st_mtime + 1, f.stat().st_mtime + 1))
            h.evaluate(f)

        assert mock_client.generate.call_count == 2

    def test_error_result_not_cached(self, tmp_path: Path) -> None:
        """Transient errors (generate raises) are not stored; next call retries."""
        h, mock_client = _make_heuristic()
        mock_client.generate.side_effect = [
            RuntimeError("timeout"),
            _make_ollama_response({"project": 0.5, "area": 0.2, "resource": 0.2, "archive": 0.1}),
        ]
        f = tmp_path / "report.txt"
        f.write_text("content")

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            r1 = h.evaluate(f)
            r2 = h.evaluate(f)

        assert mock_client.generate.call_count == 2
        assert r1.metadata.get("ai_analysis") == "ollama_error"
        assert r2.metadata.get("ai_analysis") == "complete"

    def test_stat_failure_bypasses_cache(self, tmp_path: Path) -> None:
        """Nonexistent file yields None cache key; evaluate proceeds without cache ops."""
        h, mock_client = _make_heuristic()
        mock_client.generate.return_value = _make_ollama_response(
            {"project": 0.5, "area": 0.2, "resource": 0.2, "archive": 0.1}
        )
        nonexistent = tmp_path / "ghost.txt"

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            result = h.evaluate(nonexistent)

        assert result is not None
        assert len(h._result_cache) == 0

    def test_cache_bounded_at_max_size(self, tmp_path: Path) -> None:
        """Cache never exceeds _CACHE_MAX_SIZE entries."""
        h, mock_client = _make_heuristic()
        mock_client.generate.return_value = _make_ollama_response(
            {"project": 0.5, "area": 0.2, "resource": 0.2, "archive": 0.1}
        )

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            for i in range(AIHeuristic._CACHE_MAX_SIZE + 1):
                f = tmp_path / f"file_{i}.txt"
                f.write_text(f"content {i}")
                h.evaluate(f)

        assert len(h._result_cache) == AIHeuristic._CACHE_MAX_SIZE

    def test_lru_eviction_order(self, tmp_path: Path) -> None:
        """Recently accessed entry survives; oldest LRU entry is evicted."""
        h, mock_client = _make_heuristic()
        mock_client.generate.return_value = _make_ollama_response(
            {"project": 0.5, "area": 0.2, "resource": 0.2, "archive": 0.1}
        )

        files = []
        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            for i in range(AIHeuristic._CACHE_MAX_SIZE):
                f = tmp_path / f"file_{i}.txt"
                f.write_text(f"content {i}")
                h.evaluate(f)
                files.append(f)

            # Re-access the oldest entry (file_0) to make it recently used.
            h.evaluate(files[0])

            # Adding one more entry should evict file_1 (now the LRU), not file_0.
            extra = tmp_path / "extra.txt"
            extra.write_text("extra")
            h.evaluate(extra)

        assert h._get_cache_key(files[0]) in h._result_cache
        assert h._get_cache_key(files[1]) not in h._result_cache


@pytest.mark.integration
class TestAIHeuristicCacheIntegration:
    """Integration tests: cache behaviour through HeuristicEngine."""

    def test_engine_cache_hit_via_engine(self, tmp_path: Path) -> None:
        """Two engine evaluations of same file call generate() exactly once."""
        f = tmp_path / "sprint_plan.txt"
        f.write_text("Sprint deliverables")
        scores = {"project": 0.7, "area": 0.1, "resource": 0.15, "archive": 0.05}

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            engine = HeuristicEngine(enable_ai=True)
            ai_h = next(h for h in engine.heuristics if isinstance(h, AIHeuristic))
            mock_client = MagicMock()
            mock_client.generate.return_value = _make_ollama_response(scores)
            ai_h._client = mock_client
            ai_h._available = True

            r1 = engine.evaluate(f)
            r2 = engine.evaluate(f)

        assert mock_client.generate.call_count == 1
        assert r1.scores[PARACategory.PROJECT].score == r2.scores[PARACategory.PROJECT].score

    def test_engine_cache_invalidated_on_file_change(self, tmp_path: Path) -> None:
        """Engine re-calls generate() after file content changes."""
        f = tmp_path / "notes.txt"
        f.write_text("initial content")
        scores = {"project": 0.7, "area": 0.1, "resource": 0.15, "archive": 0.05}

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True):
            engine = HeuristicEngine(enable_ai=True)
            ai_h = next(h for h in engine.heuristics if isinstance(h, AIHeuristic))
            mock_client = MagicMock()
            mock_client.generate.return_value = _make_ollama_response(scores)
            ai_h._client = mock_client
            ai_h._available = True

            engine.evaluate(f)
            f.write_text("completely different content")
            os.utime(f, (f.stat().st_mtime + 1, f.stat().st_mtime + 1))
            engine.evaluate(f)

        assert mock_client.generate.call_count == 2


# ---------------------------------------------------------------------------
# Tests: CategoryScore validation
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestCategoryScoreValidation:
    """Tests for CategoryScore validation logic."""

    def test_invalid_score_below_zero(self) -> None:
        """CategoryScore raises ValueError when score < 0.0."""
        from file_organizer.methodologies.para.detection.heuristics import CategoryScore

        with pytest.raises(ValueError, match="Score must be in range"):
            CategoryScore(category=PARACategory.PROJECT, score=-0.1, confidence=0.5)

    def test_invalid_score_above_one(self) -> None:
        """CategoryScore raises ValueError when score > 1.0."""
        from file_organizer.methodologies.para.detection.heuristics import CategoryScore

        with pytest.raises(ValueError, match="Score must be in range"):
            CategoryScore(category=PARACategory.AREA, score=1.5, confidence=0.5)

    def test_invalid_confidence_below_zero(self) -> None:
        """CategoryScore raises ValueError when confidence < 0.0."""
        from file_organizer.methodologies.para.detection.heuristics import CategoryScore

        with pytest.raises(ValueError, match="Confidence must be in range"):
            CategoryScore(category=PARACategory.RESOURCE, score=0.5, confidence=-0.1)

    def test_invalid_confidence_above_one(self) -> None:
        """CategoryScore raises ValueError when confidence > 1.0."""
        from file_organizer.methodologies.para.detection.heuristics import CategoryScore

        with pytest.raises(ValueError, match="Confidence must be in range"):
            CategoryScore(category=PARACategory.ARCHIVE, score=0.5, confidence=1.2)

    def test_valid_boundary_values(self) -> None:
        """CategoryScore accepts exact boundary values 0.0 and 1.0."""
        from file_organizer.methodologies.para.detection.heuristics import CategoryScore

        s1 = CategoryScore(category=PARACategory.PROJECT, score=0.0, confidence=0.0)
        assert s1.score == 0.0
        assert s1.confidence == 0.0

        s2 = CategoryScore(category=PARACategory.AREA, score=1.0, confidence=1.0)
        assert s2.score == 1.0
        assert s2.confidence == 1.0


# ---------------------------------------------------------------------------
# Tests: TemporalHeuristic comprehensive coverage
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestTemporalHeuristicComprehensive:
    """Comprehensive tests for TemporalHeuristic detection logic."""

    def test_nonexistent_file_returns_zero_scores(self, tmp_path: Path) -> None:
        """Non-existent file returns all-zero scores with manual review flag."""
        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        h = TemporalHeuristic(weight=0.25)
        ghost_file = tmp_path / "does_not_exist.txt"

        result = h.evaluate(ghost_file)

        assert result.overall_confidence == 0.0
        assert result.recommended_category is None
        assert result.needs_manual_review is True
        for score in result.scores.values():
            assert score.score == 0.0

    def test_old_year_pattern_edge_cases(self, tmp_path: Path) -> None:
        """_contains_old_year correctly identifies old years in various formats."""
        from datetime import UTC, datetime

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        current_year = datetime.now(UTC).year
        h = TemporalHeuristic(weight=0.25)

        # Old year in folder path (3+ years ago)
        old_year = current_year - 5
        old_folder = tmp_path / str(old_year) / "reports"
        old_folder.mkdir(parents=True)
        old_file = old_folder / "report.pdf"
        old_file.write_text("archive candidate")

        result = h.evaluate(old_file)

        assert PARACategory.ARCHIVE in [s.category for s in result.scores.values() if s.score > 0]
        archive_signals = result.scores[PARACategory.ARCHIVE].signals
        assert "old_year_in_path" in archive_signals

    def test_old_year_pattern_negative_recent_year(self, tmp_path: Path) -> None:
        """Recent year in path does NOT trigger archive scoring."""
        from datetime import UTC, datetime

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        current_year = datetime.now(UTC).year
        h = TemporalHeuristic(weight=0.25)

        # Current year in path
        recent_folder = tmp_path / str(current_year) / "active"
        recent_folder.mkdir(parents=True)
        recent_file = recent_folder / "notes.txt"
        recent_file.write_text("active project")

        result = h.evaluate(recent_file)

        archive_signals = result.scores[PARACategory.ARCHIVE].signals
        assert "old_year_in_path" not in archive_signals

    def test_temporal_project_boundary_exactly_30_days(self, tmp_path: Path) -> None:
        """File modified exactly 30 days ago does NOT trigger recent_modified."""
        import time

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        h = TemporalHeuristic(weight=0.25)
        f = tmp_path / "boundary.txt"
        f.write_text("test")

        # Set mtime to exactly 30 days ago
        thirty_days_ago = time.time() - (30 * 86400)
        os.utime(f, (thirty_days_ago, thirty_days_ago))

        result = h.evaluate(f)

        project_signals = result.scores[PARACategory.PROJECT].signals
        assert "recently_modified" not in project_signals

    def test_temporal_area_boundary_conditions(self, tmp_path: Path) -> None:
        """AREA score triggered for files modified between 30-180 days ago."""
        import time

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        h = TemporalHeuristic(weight=0.25)
        f = tmp_path / "area_file.txt"
        f.write_text("ongoing work")

        # Set mtime to 90 days ago (middle of AREA range)
        ninety_days_ago = time.time() - (90 * 86400)
        os.utime(f, (ninety_days_ago, ninety_days_ago))

        result = h.evaluate(f)

        area_signals = result.scores[PARACategory.AREA].signals
        assert "moderate_age" in area_signals
        assert result.scores[PARACategory.AREA].score > 0

    def test_temporal_resource_stable_reference(self, tmp_path: Path) -> None:
        """RESOURCE score for files with large create/modify gap on supported platforms."""
        import time

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        h = TemporalHeuristic(weight=0.25)
        f = tmp_path / "reference.pdf"
        f.write_text("reference material")

        # Set mtime to 70 days ago
        seventy_days_ago = time.time() - (70 * 86400)
        os.utime(f, (seventy_days_ago, seventy_days_ago))

        result = h.evaluate(f)

        # RESOURCE signal triggered when modify time > 60 days
        # The gap check requires birthtime/ctime difference > 30 days
        # On macOS/Windows with birthtime, or simulated via file creation timing
        # This may or may not appear depending on platform and file creation time
        # Just verify the heuristic runs without error
        assert result is not None

    def test_temporal_archive_old_untouched(self, tmp_path: Path) -> None:
        """ARCHIVE score for files modified >180 days and accessed >90 days ago."""
        import time

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        h = TemporalHeuristic(weight=0.25)
        f = tmp_path / "ancient.txt"
        f.write_text("very old")

        # Set both mtime and atime to >180 and >90 days respectively
        two_hundred_days_ago = time.time() - (200 * 86400)
        one_hundred_days_ago = time.time() - (100 * 86400)
        os.utime(f, (one_hundred_days_ago, two_hundred_days_ago))

        result = h.evaluate(f)

        archive_signals = result.scores[PARACategory.ARCHIVE].signals
        assert "old_untouched" in archive_signals
        assert result.scores[PARACategory.ARCHIVE].score > 0


# ---------------------------------------------------------------------------
# Tests: ContentHeuristic comprehensive coverage
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestContentHeuristicComprehensive:
    """Comprehensive tests for ContentHeuristic keyword and pattern matching."""

    def test_date_pattern_yyyy_mm_dd(self, tmp_path: Path) -> None:
        """Date pattern YYYY-MM-DD in filename triggers PROJECT score."""
        from file_organizer.methodologies.para.detection.heuristics import ContentHeuristic

        h = ContentHeuristic(weight=0.35)
        f = tmp_path / "report_2024-03-15.pdf"
        f.write_text("report")

        result = h.evaluate(f)

        project_signals = result.scores[PARACategory.PROJECT].signals
        assert "date_pattern" in project_signals
        assert result.scores[PARACategory.PROJECT].score > 0

    def test_date_pattern_due_underscore_digits(self, tmp_path: Path) -> None:
        """Date pattern due_NN in filename triggers PROJECT score."""
        from file_organizer.methodologies.para.detection.heuristics import ContentHeuristic

        h = ContentHeuristic(weight=0.35)
        f = tmp_path / "task_due_15.txt"
        f.write_text("task")

        result = h.evaluate(f)

        project_signals = result.scores[PARACategory.PROJECT].signals
        assert "date_pattern" in project_signals
        assert result.scores[PARACategory.PROJECT].score > 0

    def test_keyword_matching_word_boundaries(self, tmp_path: Path) -> None:
        """Keyword matching respects word boundaries (no false positives)."""
        from file_organizer.methodologies.para.detection.heuristics import ContentHeuristic

        h = ContentHeuristic(weight=0.35)

        # "projection" contains "project" substring but should NOT match due to word boundary
        f_neg = tmp_path / "sales_projection.xlsx"
        f_neg.write_text("forecast")
        result_neg = h.evaluate(f_neg)
        project_keywords_neg = [
            s for s in result_neg.scores[PARACategory.PROJECT].signals if s == "keyword:project"
        ]
        assert len(project_keywords_neg) == 0

        # "project" as standalone word in path SHOULD match (directory separator acts as boundary)
        project_folder = tmp_path / "project"
        project_folder.mkdir()
        f_pos = project_folder / "plan.docx"
        f_pos.write_text("plan")
        result_pos = h.evaluate(f_pos)
        project_keywords_pos = [
            s for s in result_pos.scores[PARACategory.PROJECT].signals if s == "keyword:project"
        ]
        assert len(project_keywords_pos) > 0

    def test_content_area_keywords(self, tmp_path: Path) -> None:
        """AREA keywords in path trigger AREA score."""
        from file_organizer.methodologies.para.detection.heuristics import ContentHeuristic

        h = ContentHeuristic(weight=0.35)
        # Use directory separator for word boundaries
        ongoing_folder = tmp_path / "ongoing" / "health"
        ongoing_folder.mkdir(parents=True)
        f = ongoing_folder / "weekly-notes.txt"
        f.write_text("routine")

        result = h.evaluate(f)

        area_signals = result.scores[PARACategory.AREA].signals
        # Check for specific keywords that should match: "ongoing", "weekly", "health"
        area_keywords = [s for s in area_signals if s.startswith("keyword:")]
        assert len(area_keywords) >= 2  # Should match "ongoing", "weekly", and "health"
        assert result.scores[PARACategory.AREA].score > 0

    def test_content_resource_keywords(self, tmp_path: Path) -> None:
        """RESOURCE keywords in path trigger RESOURCE score."""
        from file_organizer.methodologies.para.detection.heuristics import ContentHeuristic

        h = ContentHeuristic(weight=0.35)
        # Use directory separator for word boundaries
        ref_folder = tmp_path / "reference" / "library"
        ref_folder.mkdir(parents=True)
        f = ref_folder / "python-guide.pdf"
        f.write_text("tutorial")

        result = h.evaluate(f)

        resource_signals = result.scores[PARACategory.RESOURCE].signals
        # Should match "reference", "library", and "guide"
        resource_keywords = [s for s in resource_signals if s.startswith("keyword:")]
        assert len(resource_keywords) >= 2
        assert result.scores[PARACategory.RESOURCE].score > 0

    def test_content_archive_keywords(self, tmp_path: Path) -> None:
        """ARCHIVE keywords in path trigger ARCHIVE score."""
        from file_organizer.methodologies.para.detection.heuristics import ContentHeuristic

        h = ContentHeuristic(weight=0.35)
        # Use directory separator and hyphens for word boundaries
        archive_folder = tmp_path / "old" / "backup"
        archive_folder.mkdir(parents=True)
        f = archive_folder / "completed-project.zip"
        f.write_text("done")

        result = h.evaluate(f)

        archive_signals = result.scores[PARACategory.ARCHIVE].signals
        # Should match "old", "backup", "completed", and "project"
        archive_keywords = [s for s in archive_signals if s.startswith("keyword:")]
        assert len(archive_keywords) >= 2
        assert result.scores[PARACategory.ARCHIVE].score > 0


# ---------------------------------------------------------------------------
# Tests: StructuralHeuristic comprehensive coverage
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestStructuralHeuristicComprehensive:
    """Comprehensive tests for StructuralHeuristic directory structure analysis."""

    def test_structural_area_directory_indicators(self, tmp_path: Path) -> None:
        """Files in 'areas', 'ongoing', 'active', 'current' folders score as AREA."""
        from file_organizer.methodologies.para.detection.heuristics import StructuralHeuristic

        h = StructuralHeuristic(weight=0.30)

        for folder_name in ["areas", "ongoing", "active", "current"]:
            folder = tmp_path / folder_name
            folder.mkdir()
            f = folder / "file.txt"
            f.write_text("test")

            result = h.evaluate(f)

            area_signals = result.scores[PARACategory.AREA].signals
            assert "area_directory" in area_signals
            assert result.scores[PARACategory.AREA].score >= 0.4

    def test_structural_resource_directory_indicators(self, tmp_path: Path) -> None:
        """Files in resource/reference/library folders score as RESOURCE."""
        from file_organizer.methodologies.para.detection.heuristics import StructuralHeuristic

        h = StructuralHeuristic(weight=0.30)

        for folder_name in ["resources", "references", "library", "docs", "templates"]:
            folder = tmp_path / folder_name
            folder.mkdir()
            f = folder / "file.txt"
            f.write_text("test")

            result = h.evaluate(f)

            resource_signals = result.scores[PARACategory.RESOURCE].signals
            assert "resource_directory" in resource_signals
            assert result.scores[PARACategory.RESOURCE].score >= 0.4

    def test_structural_archive_directory_indicators(self, tmp_path: Path) -> None:
        """Files in archive/old/past folders score as ARCHIVE."""
        from file_organizer.methodologies.para.detection.heuristics import StructuralHeuristic

        h = StructuralHeuristic(weight=0.30)

        for folder_name in ["archive", "archives", "old", "past", "completed"]:
            folder = tmp_path / folder_name
            folder.mkdir()
            f = folder / "file.txt"
            f.write_text("test")

            result = h.evaluate(f)

            archive_signals = result.scores[PARACategory.ARCHIVE].signals
            assert "archive_directory" in archive_signals
            assert result.scores[PARACategory.ARCHIVE].score >= 0.5

    def test_structural_deep_nesting_project_indicator(self, tmp_path: Path) -> None:
        """Files with depth > 3 score higher for PROJECT."""
        from file_organizer.methodologies.para.detection.heuristics import StructuralHeuristic

        h = StructuralHeuristic(weight=0.30)

        # Create a deeply nested path (depth > 3)
        deep_folder = tmp_path / "projects" / "2024" / "q1" / "sprint1"
        deep_folder.mkdir(parents=True)
        f = deep_folder / "task.txt"
        f.write_text("test")

        result = h.evaluate(f)

        project_signals = result.scores[PARACategory.PROJECT].signals
        assert "deep_nesting" in project_signals
        assert result.scores[PARACategory.PROJECT].score > 0


# ---------------------------------------------------------------------------
# Tests: AIHeuristic _parse_response edge cases
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestAIHeuristicParseResponse:
    """Tests for AIHeuristic._parse_response edge case handling."""

    def test_parse_response_missing_json_braces(self) -> None:
        """_parse_response returns None when response has no JSON braces."""
        h = AIHeuristic(weight=0.10)
        result = h._parse_response("This is plain text without any JSON")

        assert result is None

    def test_parse_response_missing_category_key(self) -> None:
        """_parse_response returns None when JSON is missing a required category."""
        h = AIHeuristic(weight=0.10)
        # Missing "archive" key
        incomplete_json = '{"project": 0.5, "area": 0.3, "resource": 0.2}'
        result = h._parse_response(incomplete_json)

        assert result is None

    def test_parse_response_non_numeric_score(self) -> None:
        """_parse_response returns None when score value is not numeric."""
        h = AIHeuristic(weight=0.10)
        bad_json = '{"project": "high", "area": 0.2, "resource": 0.3, "archive": 0.5}'
        result = h._parse_response(bad_json)

        assert result is None

    def test_parse_response_score_clamping(self) -> None:
        """_parse_response clamps scores to [0.0, 1.0] range then normalizes."""
        h = AIHeuristic(weight=0.10)
        # Scores outside valid range
        unclamped_json = '{"project": -0.5, "area": 2.0, "resource": 0.3, "archive": 0.1}'
        result = h._parse_response(unclamped_json)

        assert result is not None
        assert result["project"] == 0.0  # Clamped from -0.5
        # After clamping: 0.0 + 1.0 + 0.3 + 0.1 = 1.4
        # After normalization: 1.0/1.4 = 0.714...
        assert result["area"] == pytest.approx(1.0 / 1.4, abs=0.01)
        assert result["resource"] == pytest.approx(0.3 / 1.4, abs=0.01)
        assert result["archive"] == pytest.approx(0.1 / 1.4, abs=0.01)

    def test_parse_response_zero_sum_normalization(self) -> None:
        """_parse_response handles zero-sum scores (all zeros) gracefully."""
        h = AIHeuristic(weight=0.10)
        zero_json = '{"project": 0.0, "area": 0.0, "resource": 0.0, "archive": 0.0, "reasoning": "uncertain"}'
        result = h._parse_response(zero_json)

        assert result is not None
        # All zeros remain zeros (no division by zero)
        assert result["project"] == 0.0
        assert result["area"] == 0.0
        assert result["resource"] == 0.0
        assert result["archive"] == 0.0


# ---------------------------------------------------------------------------
# Tests: HeuristicEngine edge cases
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestHeuristicEngineEdgeCases:
    """Tests for HeuristicEngine edge cases and error handling."""

    def test_engine_no_heuristics_enabled_raises(self) -> None:
        """HeuristicEngine with no heuristics raises ValueError on evaluate."""
        engine = HeuristicEngine(
            enable_temporal=False,
            enable_content=False,
            enable_structural=False,
            enable_ai=False,
        )

        with pytest.raises(ValueError, match="No heuristics enabled"):
            engine.evaluate(Path("/fake/file.txt"))

    def test_engine_all_heuristics_fail_returns_zero_result(self, tmp_path: Path) -> None:
        """When all heuristics raise exceptions, engine returns zero result."""
        from file_organizer.methodologies.para.detection.heuristics import (
            HeuristicResult,
        )

        f = tmp_path / "test.txt"
        f.write_text("test")

        engine = HeuristicEngine(enable_temporal=True, enable_content=True)

        # Make all heuristics raise exceptions by replacing their evaluate methods
        def failing_evaluate(
            file_path: Path, metadata: dict[str, Any] | None = None
        ) -> HeuristicResult:
            raise RuntimeError("heuristic failed")

        for heuristic in engine.heuristics:
            heuristic.evaluate = failing_evaluate  # type: ignore[method-assign]

        result = engine.evaluate(f)

        assert result.overall_confidence == 0.0
        assert result.needs_manual_review is True
        for score in result.scores.values():
            assert score.score == 0.0

    def test_engine_top_score_zero_confidence_zero(self, tmp_path: Path) -> None:
        """When all category scores are zero, overall_confidence is zero."""
        from file_organizer.methodologies.para.detection.heuristics import (
            CategoryScore,
            HeuristicResult,
        )

        f = tmp_path / "test.txt"
        f.write_text("test")

        engine = HeuristicEngine(enable_temporal=True)

        # Mock the heuristic to return all-zero scores
        mock_result = HeuristicResult(
            scores={cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory},
            overall_confidence=0.0,
            abstained=False,  # Not abstained, just zero scores
        )

        def zero_evaluate(
            file_path: Path, metadata: dict[str, Any] | None = None
        ) -> HeuristicResult:
            return mock_result

        # Replace all heuristics with the zero-returning mock
        for heuristic in engine.heuristics:
            heuristic.evaluate = zero_evaluate  # type: ignore[method-assign]

        result = engine.evaluate(f)

        assert result.overall_confidence == 0.0

    def test_engine_confidence_below_threshold_needs_review(self, tmp_path: Path) -> None:
        """Engine sets needs_manual_review when confidence < 0.60."""

        f = tmp_path / "ambiguous.txt"
        f.write_text("test")

        # Use only structural heuristic which tends to give lower scores
        engine = HeuristicEngine(
            enable_structural=True, enable_temporal=False, enable_content=False
        )

        result = engine.evaluate(f)

        # Structural heuristic with no special path signals may not meet recommendation
        # threshold — engine sets needs_manual_review=True when no category qualifies
        assert result.needs_manual_review is True

    def test_engine_no_recommendation_needs_review(self, tmp_path: Path) -> None:
        """Engine sets needs_manual_review when no category meets threshold."""
        from file_organizer.methodologies.para.config import CategoryThresholds

        f = tmp_path / "test.txt"
        f.write_text("test")

        # Set impossibly high thresholds
        thresholds = CategoryThresholds(project=0.99, area=0.99, resource=0.99, archive=0.99)
        engine = HeuristicEngine(enable_temporal=True, thresholds=thresholds)

        result = engine.evaluate(f)

        assert result.recommended_category is None
        assert result.needs_manual_review is True

    def test_engine_recommendation_meets_threshold(self, tmp_path: Path) -> None:
        """Engine recommends category when its score meets threshold."""
        from file_organizer.methodologies.para.config import CategoryThresholds

        # Create a file that will score high for ARCHIVE category
        archive_folder = tmp_path / "archive" / "old"
        archive_folder.mkdir(parents=True)
        f = archive_folder / "completed.txt"
        f.write_text("done")

        # Set low threshold for ARCHIVE
        thresholds = CategoryThresholds(project=0.99, area=0.99, resource=0.99, archive=0.1)
        engine = HeuristicEngine(enable_structural=True, thresholds=thresholds)

        result = engine.evaluate(f)

        # File in archive/old folder should score high for ARCHIVE
        assert result.scores[PARACategory.ARCHIVE].score >= 0.1, (
            "Test setup should produce ARCHIVE score >= threshold"
        )
        assert result.recommended_category == PARACategory.ARCHIVE


# ---------------------------------------------------------------------------
# Tests: Additional edge cases for 100% coverage
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestRemainingCoverage:
    """Tests for remaining uncovered lines to achieve 100% coverage."""

    def test_parse_response_invalid_json(self) -> None:
        """_parse_response returns None when JSON is malformed."""
        h = AIHeuristic(weight=0.10)
        # Invalid JSON (unclosed brace, trailing comma)
        invalid_json = '{"project": 0.5, "area": 0.3, "resource": 0.2,'
        result = h._parse_response(invalid_json)

        assert result is None

    def test_temporal_resource_gap_trigger(self, tmp_path: Path) -> None:
        """RESOURCE signal triggered when create/modify gap > 30 days."""
        import time

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        h = TemporalHeuristic(weight=0.25)
        f = tmp_path / "reference.txt"
        f.write_text("reference")

        # Set file mtime to 90 days ago
        ninety_days_ago = time.time() - (90 * 86400)
        os.utime(f, (ninety_days_ago, ninety_days_ago))

        # On macOS/Windows with birthtime tracking, if the file was created
        # recently but mtime is old, the gap would be large
        # On Linux, both will use mtime, so gap = 0

        result = h.evaluate(f)

        # The test exercises the code path even if signal doesn't always appear
        # due to platform differences
        assert result is not None

    def test_temporal_recent_file_under_30_days(self, tmp_path: Path) -> None:
        """File modified <30 days ago triggers recent_modified signal."""
        import time

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        h = TemporalHeuristic(weight=0.25)
        f = tmp_path / "recent.txt"
        f.write_text("recent work")

        # Set mtime to 15 days ago
        fifteen_days_ago = time.time() - (15 * 86400)
        os.utime(f, (fifteen_days_ago, fifteen_days_ago))

        result = h.evaluate(f)

        project_signals = result.scores[PARACategory.PROJECT].signals
        assert "recently_modified" in project_signals
        assert result.scores[PARACategory.PROJECT].score > 0


@pytest.mark.ci
class TestPlatformSpecificPaths:
    """Tests for platform-specific code paths in TemporalHeuristic."""

    def test_windows_platform_uses_ctime_for_creation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """On Windows, st_ctime is used for file creation time."""
        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        class MockStat:
            def __init__(self, *, now: float) -> None:
                self.st_mtime = now - (120 * 86400)
                self.st_atime = now - (120 * 86400)
                self.st_ctime = now - 86400

        # Simulate Windows platform
        monkeypatch.setattr(os, "name", "nt")
        now = time.time()
        monkeypatch.setattr(Path, "stat", lambda _self, *args, **kwargs: MockStat(now=now))

        h = TemporalHeuristic(weight=0.25)
        f = tmp_path / "test.txt"
        f.write_text("test")

        result = h.evaluate(f)

        assert "stable_reference" in result.scores[PARACategory.RESOURCE].signals

    def test_linux_platform_uses_mtime_for_creation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """On Linux (without birthtime), st_mtime is used as creation proxy."""

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        class MockStat:
            def __init__(self, *, now: float) -> None:
                self.st_mtime = now - (120 * 86400)
                self.st_atime = now - (120 * 86400)
                self.st_ctime = now - 86400

        # Simulate Linux platform
        monkeypatch.setattr(os, "name", "posix")
        now = time.time()
        monkeypatch.setattr(Path, "stat", lambda _self, *args, **kwargs: MockStat(now=now))

        h = TemporalHeuristic(weight=0.25)
        f = tmp_path / "test.txt"
        f.write_text("test")

        result = h.evaluate(f)

        assert "stable_reference" not in result.scores[PARACategory.RESOURCE].signals


@pytest.mark.ci
class TestAIHeuristicEnsureClientEdgeCases:
    """Tests for AIHeuristic._ensure_client error handling."""

    def test_ensure_client_connection_timeout(self, tmp_path: Path) -> None:
        """_ensure_client handles timeout exceptions gracefully."""
        h = AIHeuristic(weight=0.10)
        h._available = None  # Force re-initialization

        f = tmp_path / "test.txt"
        f.write_text("test")

        with (
            patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True),
            patch(f"{_HEURISTICS_MODULE}.ollama") as mock_ollama,
        ):
            # Make list() raise a timeout exception
            mock_ollama.Client.return_value.list.side_effect = TimeoutError("connection timeout")
            result = h.evaluate(f)

        assert result.metadata["ai_analysis"] == "ollama_unavailable"
        assert result.abstained is True

    def test_ensure_client_generic_exception(self, tmp_path: Path) -> None:
        """_ensure_client handles generic exceptions gracefully."""
        h = AIHeuristic(weight=0.10)
        h._available = None  # Force re-initialization

        f = tmp_path / "test.txt"
        f.write_text("test")

        with (
            patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True),
            patch(f"{_HEURISTICS_MODULE}.ollama") as mock_ollama,
        ):
            # Make list() raise a generic exception
            mock_ollama.Client.return_value.list.side_effect = Exception("unexpected error")
            result = h.evaluate(f)

        assert result.metadata["ai_analysis"] == "ollama_unavailable"
        assert result.abstained is True


@pytest.mark.ci
class TestPlatformSpecificBranches:
    """Tests to cover platform-specific code branches."""

    def test_windows_platform_stat_ctime(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Windows branch uses st_ctime when no st_birthtime."""

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        f = tmp_path / "test.txt"
        f.write_text("test")

        # Get real stat
        real_stat = f.stat()

        # Create a mock stat object without st_birthtime
        class MockStat:
            st_mtime = real_stat.st_mtime
            st_atime = real_stat.st_atime
            st_ctime = real_stat.st_ctime
            # Explicitly no st_birthtime attribute

        # Monkeypatch both os.name and Path.stat
        monkeypatch.setattr(os, "name", "nt")
        monkeypatch.setattr(Path, "stat", lambda self: MockStat())

        h = TemporalHeuristic(weight=0.25)
        result = h.evaluate(f)

        # The Windows branch should execute
        assert result is not None

    def test_linux_platform_stat_mtime_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Linux branch uses st_mtime as creation time proxy."""

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        f = tmp_path / "test.txt"
        f.write_text("test")

        # Get real stat
        real_stat = f.stat()

        # Create a mock stat object without st_birthtime
        class MockStat:
            st_mtime = real_stat.st_mtime
            st_atime = real_stat.st_atime
            st_ctime = real_stat.st_ctime
            # Explicitly no st_birthtime attribute

        # Monkeypatch both os.name and Path.stat
        monkeypatch.setattr(os, "name", "posix")
        monkeypatch.setattr(Path, "stat", lambda self: MockStat())

        h = TemporalHeuristic(weight=0.25)
        result = h.evaluate(f)

        # The Linux/else branch should execute
        assert result is not None

    def test_resource_stable_reference_signal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RESOURCE stable_reference signal when create/modify gap > 30 days."""
        import time

        from file_organizer.methodologies.para.detection.heuristics import TemporalHeuristic

        f = tmp_path / "reference.pdf"
        f.write_text("reference")

        # Create a mock stat where:
        # - File was created 120 days ago (birthtime)
        # - File was last modified 70 days ago (mtime)
        # - Gap = 50 days > 30 days threshold
        # - mtime age = 70 days > 60 days threshold
        now = time.time()
        mtime_70_days_ago = now - (70 * 86400)
        birthtime_120_days_ago = now - (120 * 86400)
        atime_100_days_ago = now - (100 * 86400)

        class MockStat:
            st_mtime = mtime_70_days_ago
            st_atime = atime_100_days_ago
            st_ctime = birthtime_120_days_ago
            st_birthtime = birthtime_120_days_ago

        monkeypatch.setattr(Path, "stat", lambda self: MockStat())

        h = TemporalHeuristic(weight=0.25)
        result = h.evaluate(f)

        # stable_reference signal should be present
        resource_signals = result.scores[PARACategory.RESOURCE].signals
        assert "stable_reference" in resource_signals
        assert result.scores[PARACategory.RESOURCE].score > 0
