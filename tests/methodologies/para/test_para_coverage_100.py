"""Gap-filling tests to bring all PARA methodology modules to 100% coverage.

Targets uncovered branches in:
- detection/heuristics.py: import guard, double-checked locking, file content edges,
  JSON parse failure
- ai/feedback.py: weight adjustment mid-range acceptance, directory rejection ratio,
  events without extension/directory
- ai/suggestion_engine.py: metadata scoring implicit else branch

Issue: #1017
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.methodologies.para.ai.feedback import (
    FeedbackEvent,
    PatternLearner,
)
from file_organizer.methodologies.para.ai.suggestion_engine import (
    MetadataFeatures,
    _score_metadata_features,
)
from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import HeuristicWeights
from file_organizer.methodologies.para.detection.heuristics import AIHeuristic

_HEURISTICS_MODULE = "file_organizer.methodologies.para.detection.heuristics"


# =========================================================================
# detection/heuristics.py — import guard (lines 24-26)
# =========================================================================


@pytest.mark.unit
class TestOllamaImportGuard:
    """Cover the ``except ImportError`` branch for the ollama import (lines 24-26)."""

    def test_ollama_import_error_sets_flag_false(self) -> None:
        """When ollama is not installed, OLLAMA_AVAILABLE is False and
        ollama is set to None (lines 24-26)."""
        module_name = _HEURISTICS_MODULE
        # Save and remove ollama from sys.modules so the import fails
        saved_ollama = sys.modules.pop("ollama", None)
        saved_heuristics = sys.modules.pop(module_name, None)

        # Block the import of ollama
        import builtins

        original_import = builtins.__import__

        def _blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "ollama":
                raise ImportError("mocked: no ollama")
            return original_import(name, *args, **kwargs)

        try:
            builtins.__import__ = _blocked_import  # type: ignore[assignment]
            mod = importlib.import_module(module_name)
            assert mod.OLLAMA_AVAILABLE is False
            assert mod.ollama is None
        finally:
            builtins.__import__ = original_import  # type: ignore[assignment]
            # Restore original modules
            if saved_heuristics is not None:
                sys.modules[module_name] = saved_heuristics
            if saved_ollama is not None:
                sys.modules["ollama"] = saved_ollama


# =========================================================================
# detection/heuristics.py — double-checked locking (line 494)
# =========================================================================


@pytest.mark.unit
class TestEnsureClientDoubleCheckedLocking:
    """Cover the re-check inside the lock (line 494)."""

    def test_second_thread_sees_cached_result(self) -> None:
        """When _available is set by another thread before lock acquired,
        the re-check returns immediately (line 494)."""
        h = AIHeuristic(weight=0.10)
        h._available = None  # force entry into _ensure_client

        class _SimulateConcurrentLock:
            """A context-manager lock that simulates another thread setting
            _available before the body of the ``with`` block runs."""

            def __enter__(self) -> bool:
                # Simulate another thread completing init while we waited
                h._available = True
                return True

            def __exit__(self, *args: object) -> None:
                pass

        h._init_lock = _SimulateConcurrentLock()  # type: ignore[assignment]

        result = h._ensure_client()
        assert result is True

    def test_ollama_unavailable_inside_lock(self) -> None:
        """When OLLAMA_AVAILABLE is False, _ensure_client sets _available=False
        and returns False (lines 497-498)."""
        h = AIHeuristic(weight=0.10)
        h._available = None

        with patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", False):
            result = h._ensure_client()

        assert result is False
        assert h._available is False

    def test_successful_client_init(self) -> None:
        """When Ollama is available and client.list() succeeds, _available=True (line 506)."""
        h = AIHeuristic(weight=0.10)
        h._available = None

        mock_client = MagicMock()
        mock_client.list.return_value = []

        with (
            patch(f"{_HEURISTICS_MODULE}.OLLAMA_AVAILABLE", True),
            patch(f"{_HEURISTICS_MODULE}.ollama") as mock_ollama,
        ):
            mock_ollama.Client.return_value = mock_client
            result = h._ensure_client()

        assert result is True
        assert h._available is True


# =========================================================================
# detection/heuristics.py — _read_file_content edge cases
# =========================================================================


@pytest.mark.unit
class TestReadFileContentEdges:
    """Cover branches in AIHeuristic._read_file_content."""

    def _make_heuristic(self) -> AIHeuristic:
        h = AIHeuristic(weight=0.10)
        h._client = MagicMock()
        h._available = True
        return h

    def test_empty_utf8_content_falls_through(self, tmp_path: Path) -> None:
        """When file decodes to whitespace-only content, fallback path is used
        (branch 563->569)."""
        empty_file = tmp_path / "blank.txt"
        empty_file.write_text("   \n\t  \n")

        h = self._make_heuristic()
        result = h._extract_content(empty_file, None)

        assert "[Binary or unreadable file: blank.txt]" in result

    def test_empty_content_with_metadata(self, tmp_path: Path) -> None:
        """Fallback path includes metadata when provided."""
        empty_file = tmp_path / "blank.txt"
        empty_file.write_text("   ")

        h = self._make_heuristic()
        result = h._extract_content(empty_file, {"size": "1024"})

        assert "[Binary or unreadable file: blank.txt]" in result
        assert "size: 1024" in result

    def test_invalid_json_response_returns_none(self) -> None:
        """When LLM response contains invalid JSON, _parse_response returns None
        (lines 620-621)."""
        h = self._make_heuristic()
        result = h._parse_response("{this is not valid json}")
        assert result is None


# =========================================================================
# ai/feedback.py — adjust_weights mid-range acceptance (line 441->447)
# =========================================================================


@pytest.mark.unit
class TestFeedbackWeightAdjustment:
    """Cover partial branches in PatternLearner.adjust_weights."""

    @staticmethod
    def _make_events(
        count: int,
        accepted_ratio: float,
        *,
        with_directory: bool = True,
        dir_rejection_ratio: float = 0.0,
    ) -> list[FeedbackEvent]:
        """Build a list of FeedbackEvent with controlled acceptance/directory ratios."""
        events: list[FeedbackEvent] = []
        accepted_count = int(count * accepted_ratio)

        for i in range(count):
            is_accepted = i < accepted_count
            cat = PARACategory.PROJECT if is_accepted else PARACategory.RESOURCE
            parent_dir = "docs" if with_directory else ""

            # For rejected events, control the directory ratio
            if not is_accepted and dir_rejection_ratio > 0:
                # Give dir to a fraction of rejections
                rejected_index = i - accepted_count
                total_rejected = count - accepted_count
                if rejected_index < int(total_rejected * dir_rejection_ratio):
                    parent_dir = "projects"
                else:
                    parent_dir = ""

            events.append(
                FeedbackEvent(
                    file_path=Path(f"/{parent_dir}/file{i}.txt")
                    if parent_dir
                    else Path(f"/file{i}.txt"),
                    suggested=PARACategory.PROJECT,
                    actual=cat,
                    confidence=0.8,
                    accepted=is_accepted,
                    file_extension=".txt",
                    parent_directory=parent_dir,
                )
            )
        return events

    def test_mid_range_acceptance_no_weight_change(self) -> None:
        """When 0.5 <= acceptance_rate <= 0.8, neither low nor high branch is taken
        (partial 441->447)."""
        learner = PatternLearner(min_occurrences=2)
        events = self._make_events(10, 0.7, with_directory=False)  # 70% acceptance

        weights = learner.adjust_weights(events)

        # Should get default weights (normalized) since mid-range
        assert isinstance(weights, HeuristicWeights)
        assert weights.temporal == pytest.approx(0.25, abs=0.01)
        assert weights.content == pytest.approx(0.35, abs=0.01)
        assert weights.structural == pytest.approx(0.30, abs=0.01)
        assert weights.ai == pytest.approx(0.10, abs=0.01)

    def test_low_dir_rejection_ratio_no_structural_penalty(self) -> None:
        """When dir_rejections <= 60% of rejections, structural is not penalized
        (partial 450->456)."""
        learner = PatternLearner(min_occurrences=2)
        # Low acceptance (< 0.5) with low dir rejection ratio (< 60%)
        events = self._make_events(
            10,
            0.3,
            with_directory=False,
            dir_rejection_ratio=0.3,  # only 30% of rejections have directories
        )

        weights = learner.adjust_weights(events)

        assert isinstance(weights, HeuristicWeights)
        assert weights.temporal == pytest.approx(0.25, abs=0.01)
        assert weights.content == pytest.approx(0.30, abs=0.01)
        assert weights.structural == pytest.approx(0.35, abs=0.01)
        assert weights.ai == pytest.approx(0.10, abs=0.01)


# =========================================================================
# ai/feedback.py — events without extension/directory (lines 488, 521)
# =========================================================================


@pytest.mark.unit
class TestFeedbackPatternLearningEdges:
    """Cover partial branches in _learn_extension_patterns and _learn_directory_patterns."""

    def test_events_without_extension_are_skipped(self) -> None:
        """Events with empty file_extension are skipped in _learn_extension_patterns
        (partial 488->487)."""
        learner = PatternLearner(min_occurrences=1)

        events = [
            FeedbackEvent(
                file_path=Path("/noext"),
                suggested=PARACategory.PROJECT,
                actual=PARACategory.RESOURCE,
                confidence=0.8,
                accepted=False,
                file_extension="",  # no extension
                parent_directory="docs",
            ),
        ]

        rules = learner._learn_extension_patterns(events)
        assert rules == []

    def test_events_without_directory_are_skipped(self) -> None:
        """Events with empty parent_directory are skipped in _learn_directory_patterns
        (partial 521->520)."""
        learner = PatternLearner(min_occurrences=1)

        events = [
            FeedbackEvent(
                file_path=Path("/file.txt"),
                suggested=PARACategory.PROJECT,
                actual=PARACategory.RESOURCE,
                confidence=0.8,
                accepted=False,
                file_extension=".txt",
                parent_directory="",  # no directory
            ),
        ]

        rules = learner._learn_directory_patterns(events)
        assert rules == []


# =========================================================================
# ai/suggestion_engine.py — metadata scoring branch (line 92->95)
# =========================================================================


@pytest.mark.unit
class TestMetadataScoringBranch:
    """Cover the partial branch where days_mod > 180 evaluates to False
    after the elif chain (line 92->95)."""

    def test_days_mod_in_area_range_no_archive_boost(self) -> None:
        """When 30 <= days_mod <= 180, AREA gets boosted but not ARCHIVE,
        and we still evaluate the access_frequency condition at line 95."""
        scores: dict[PARACategory, float] = dict.fromkeys(PARACategory, 0.0)

        features = MetadataFeatures(
            days_since_modified=90,  # in 30-180 range -> AREA branch
            access_frequency=0.5,  # 0.2 <= x <= 0.7 -> neither access branch
        )

        _score_metadata_features(features, scores)

        assert scores[PARACategory.AREA] == pytest.approx(0.05)
        assert scores[PARACategory.ARCHIVE] == pytest.approx(0.0)
        assert scores[PARACategory.PROJECT] == pytest.approx(0.0)

    def test_days_mod_area_range_with_low_access_no_archive(self) -> None:
        """When 30 <= days_mod <= 180 and low access frequency but days_mod <= 90,
        ARCHIVE is not boosted by the access branch."""
        scores: dict[PARACategory, float] = dict.fromkeys(PARACategory, 0.0)

        features = MetadataFeatures(
            days_since_modified=60,  # in 30-180 range
            access_frequency=0.1,  # < 0.2, but days_mod=60 < 90 -> no archive
        )

        _score_metadata_features(features, scores)

        assert scores[PARACategory.AREA] == pytest.approx(0.05)
        assert scores[PARACategory.ARCHIVE] == pytest.approx(0.0)

    def test_days_mod_area_range_with_low_access_and_old(self) -> None:
        """When 30 <= days_mod <= 180 and low access frequency with days_mod > 90,
        both AREA and ARCHIVE get boosts."""
        scores: dict[PARACategory, float] = dict.fromkeys(PARACategory, 0.0)

        features = MetadataFeatures(
            days_since_modified=120,  # in 30-180 range AND > 90
            access_frequency=0.1,  # < 0.2
        )

        _score_metadata_features(features, scores)

        assert scores[PARACategory.AREA] == pytest.approx(0.05)
        assert scores[PARACategory.ARCHIVE] == pytest.approx(0.1)

    def test_days_mod_nan_skips_all_temporal_branches(self) -> None:
        """When days_since_modified is NaN, all comparisons are False so no
        temporal scoring is applied (covers 92->95 False branch)."""
        scores: dict[PARACategory, float] = dict.fromkeys(PARACategory, 0.0)

        features = MetadataFeatures(
            days_since_modified=float("nan"),
            access_frequency=0.5,  # mid-range, no access branch either
        )

        _score_metadata_features(features, scores)

        # NaN fails all comparisons, so no category gets a temporal boost
        assert scores[PARACategory.PROJECT] == pytest.approx(0.0)
        assert scores[PARACategory.AREA] == pytest.approx(0.0)
        assert scores[PARACategory.ARCHIVE] == pytest.approx(0.0)
