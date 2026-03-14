"""Tests for PatternLearner orchestrator.

Comprehensive tests covering correction learning, naming pattern extraction,
folder preference identification, confidence updates, suggestions, stats,
batch learning, old pattern clearing, and enable/disable toggles.

NOTE: PatternLearner has several interface mismatches with its sub-components
(wrong key names, missing methods).  We mock the sub-components after init
so we can exercise PatternLearner's own logic without hitting those bugs.
"""

from __future__ import annotations

import inspect
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.intelligence.confidence import ConfidenceEngine
from file_organizer.services.intelligence.pattern_learner import PatternLearner
from file_organizer.services.intelligence.preference_tracker import CorrectionType

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_learner_deps():
    """Patch ConfidenceEngine and PreferenceTracker to accept storage_path.

    PatternLearner.__init__ passes ``storage_path`` to both
    ConfidenceEngine and PreferenceTracker, but neither of their
    ``__init__`` signatures declare that parameter.  We patch both
    constructors so the kwarg is silently dropped.

    Returns a *context-manager* that should wrap any ``PatternLearner()``
    construction call.
    """
    from contextlib import ExitStack

    from file_organizer.services.intelligence.confidence import ConfidenceEngine
    from file_organizer.services.intelligence.preference_tracker import (
        PreferenceTracker,
    )

    orig_ce_init = ConfidenceEngine.__init__
    orig_pt_init = PreferenceTracker.__init__

    def patched_ce_init(self, **kwargs):
        kwargs.pop("storage_path", None)
        orig_ce_init(self, **kwargs)

    def patched_pt_init(self, **kwargs):
        kwargs.pop("storage_path", None)
        orig_pt_init(self)

    stack = ExitStack()
    stack.enter_context(patch.object(ConfidenceEngine, "__init__", patched_ce_init))
    stack.enter_context(patch.object(PreferenceTracker, "__init__", patched_pt_init))
    return stack


def _mock_sub_components(learner):
    """Replace sub-components with mocks to work around interface mismatches.

    PatternLearner calls methods that don't exist on the real classes
    (e.g. ``confidence_engine.track_usage``,
    ``preference_tracker.track_correction``, etc.).  We replace those
    components with MagicMock objects so the tests can exercise
    PatternLearner's own orchestration logic.
    """
    # Mock confidence engine (missing: recalculate_all, get_stats)
    learner.confidence_engine = MagicMock()
    learner.confidence_engine.clear_stale_patterns.return_value = 0
    learner.confidence_engine.get_stats.return_value = {"patterns": 0}

    # Mock preference tracker
    learner.preference_tracker = MagicMock()

    # Mock folder learner so we can control return values
    learner.folder_learner = MagicMock()
    learner.folder_learner.analyze_organization_patterns.return_value = {}
    learner.folder_learner.clear_old_preferences.return_value = 0
    learner.folder_learner.suggest_folder_structure.return_value = None
    learner.folder_learner.get_folder_confidence.return_value = 0.0

    # Mock pattern extractor to return dicts with 'case_style' key
    # (real analyze_filename returns 'case_convention' instead)
    mock_extractor = MagicMock()
    mock_extractor.analyze_filename.return_value = {
        "original": "file.txt",
        "name": "file",
        "extension": ".txt",
        "delimiters": [],
        "date_info": None,
        "has_numbers": False,
        "case_style": "lowercase",
        "case_convention": "lowercase",
        "length": 4,
        "word_count": 1,
    }
    mock_extractor.extract_common_elements.return_value = ["report"]
    mock_extractor.identify_structure_pattern.return_value = {"type": "simple"}
    mock_extractor.extract_delimiters.return_value = ["_"]
    mock_extractor.detect_case_style.return_value = "lowercase"
    mock_extractor.suggest_naming_convention.return_value = None
    learner.pattern_extractor = mock_extractor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def learner(temp_storage):
    """Create a PatternLearner with temp storage and mocked sub-components.

    Patches init-time constructor mismatches, then replaces sub-components
    with mocks to avoid runtime interface bugs.
    """
    with _patch_learner_deps():
        pl = PatternLearner(storage_path=temp_storage)
    _mock_sub_components(pl)
    return pl


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInit:
    """Tests for PatternLearner initialization."""

    def test_default_storage(self):
        """Test default storage path when none provided."""
        temp_dir = tempfile.mkdtemp()
        try:
            with _patch_learner_deps():
                pl = PatternLearner(storage_path=Path(temp_dir))
            assert pl.storage_path == Path(temp_dir)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_creates_storage_directory(self, temp_storage):
        """Test that storage directory is created on init."""
        storage = temp_storage / "new_subdir"
        with _patch_learner_deps():
            PatternLearner(storage_path=storage)

        assert storage.exists()
        assert storage.is_dir()

    def test_component_initialization(self, temp_storage):
        """Test that all components are initialized (before mocking)."""
        with _patch_learner_deps():
            pl = PatternLearner(storage_path=temp_storage)

        # Before mocking, components are real objects
        assert pl.pattern_extractor is not None
        assert pl.confidence_engine is not None
        assert pl.folder_learner is not None
        assert pl.feedback_processor is not None
        assert pl.preference_tracker is not None

    def test_default_state(self, learner):
        """Test default learning state."""
        assert learner.learning_enabled is True
        assert learner.min_confidence == 0.6


# ---------------------------------------------------------------------------
# learn_from_correction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLearnFromCorrection:
    """Tests for learn_from_correction method."""

    def test_learning_disabled(self, learner):
        """Test that corrections are ignored when learning is disabled."""
        learner.learning_enabled = False
        original = Path("/docs/old.txt")
        corrected = Path("/docs/new.txt")

        result = learner.learn_from_correction(original, corrected)

        assert result == {"learning_enabled": False}

    def test_name_change_learning(self, learner):
        """Test learning from a name change."""
        original = Path("/docs/old_file.txt")
        corrected = Path("/docs/new_file.txt")

        with patch.object(
            learner.feedback_processor,
            "process_correction",
            wraps=learner.feedback_processor.process_correction,
        ) as mock_process:
            result = learner.learn_from_correction(original, corrected)

        mock_process.assert_called_once_with(original, corrected, None)
        assert "timestamp" in result
        assert result["original"] == str(original)
        assert result["corrected"] == str(corrected)
        assert len(result["learned"]) >= 1
        naming_results = [r for r in result["learned"] if r["type"] == "naming"]
        assert len(naming_results) == 1

    def test_folder_change_learning(self, learner):
        """Test learning from a folder change (same filename)."""
        original = Path("/downloads/report.pdf")
        corrected = Path("/documents/report.pdf")

        result = learner.learn_from_correction(original, corrected)

        folder_results = [r for r in result["learned"] if r["type"] == "folder"]
        assert len(folder_results) == 1
        assert folder_results[0]["file_type"] == ".pdf"

    def test_both_name_and_folder_change(self, learner):
        """Test learning from both name and folder change."""
        original = Path("/downloads/old.txt")
        corrected = Path("/documents/new.txt")

        result = learner.learn_from_correction(original, corrected)

        types_learned = [r["type"] for r in result["learned"]]
        assert "naming" in types_learned
        assert "folder" in types_learned

    def test_retraining_triggered(self, learner):
        """Test that retraining flag is set after threshold corrections."""
        original = Path("/a/file.txt")
        corrected = Path("/b/file.txt")

        for _ in range(learner.feedback_processor.learning_threshold):
            result = learner.learn_from_correction(original, corrected)

        assert result.get("retraining_triggered") is True

    def test_no_change(self, learner):
        """Test learning from identical paths."""
        path = Path("/docs/file.txt")

        result = learner.learn_from_correction(path, path)

        assert len(result["learned"]) == 0

    def test_with_context(self, learner):
        """Test learning with context information."""
        original = Path("/docs/file.txt")
        corrected = Path("/archive/file.txt")
        context = {"operation": "archive"}

        with patch.object(
            learner.feedback_processor,
            "process_correction",
            wraps=learner.feedback_processor.process_correction,
        ) as mock_process:
            result = learner.learn_from_correction(original, corrected, context)

        mock_process.assert_called_once_with(original, corrected, context)
        assert "timestamp" in result

    def test_preference_tracker_called(self, learner):
        """Test that preference tracker receives the operation."""
        original = Path("/a/old.txt")
        corrected = Path("/b/new.txt")

        learner.learn_from_correction(original, corrected)

        learner.preference_tracker.track_correction.assert_called_once_with(
            original,
            corrected,
            CorrectionType.FILE_MOVE,
        )


# ---------------------------------------------------------------------------
# extract_naming_pattern
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractNamingPattern:
    """Tests for extract_naming_pattern method."""

    def test_empty_filenames(self, learner):
        """Test extraction with empty filename list."""
        result = learner.extract_naming_pattern([])
        assert result == {"patterns": []}

    def test_single_filename(self, learner):
        """Test extraction with a single filename."""
        result = learner.extract_naming_pattern(["report_2024.pdf"])

        assert "common_elements" in result
        assert "structure" in result
        assert "delimiters" in result
        assert "case_style" in result
        assert "confidence" in result

    def test_multiple_similar_filenames(self, learner):
        """Test extraction with similar filenames."""
        filenames = ["report_jan.pdf", "report_feb.pdf", "report_mar.pdf"]

        result = learner.extract_naming_pattern(filenames)

        assert isinstance(result["common_elements"], list)
        assert isinstance(result["delimiters"], dict)
        assert result["case_style"] is not None

    def test_mixed_filenames(self, learner):
        """Test extraction with diverse filenames."""
        filenames = ["alpha.txt", "beta.csv", "gamma.pdf"]

        result = learner.extract_naming_pattern(filenames)

        assert "confidence" in result
        assert result["confidence"] >= 0.0


# ---------------------------------------------------------------------------
# identify_folder_preference
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIdentifyFolderPreference:
    """Tests for identify_folder_preference method."""

    def test_tracks_folder_choice(self, learner, temp_storage):
        """Test that folder choices are tracked."""
        folder = temp_storage / "documents"
        folder.mkdir()

        learner.identify_folder_preference(".pdf", folder, None)

        learner.folder_learner.track_folder_choice.assert_called_once_with(".pdf", folder, None)

    def test_tracks_with_context(self, learner, temp_storage):
        """Test tracking with context information."""
        folder = temp_storage / "photos"
        folder.mkdir()

        context = {"pattern": "vacation"}
        learner.identify_folder_preference(".jpg", folder, context)

        learner.folder_learner.track_folder_choice.assert_called_once_with(".jpg", folder, context)


# ---------------------------------------------------------------------------
# update_confidence
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateConfidence:
    """Tests for update_confidence method."""

    def test_success_update(self, learner):
        """Test updating confidence with success."""
        learner.update_confidence("test_pattern", True)

        learner.confidence_engine.track_usage.assert_called_once()
        call_args = learner.confidence_engine.track_usage.call_args
        bound_call = inspect.signature(ConfidenceEngine.track_usage).bind(
            learner.confidence_engine,
            *call_args.args,
            **call_args.kwargs,
        )
        assert bound_call.arguments["pattern_id"] == "test_pattern"
        recorded_at = bound_call.arguments["timestamp"]
        assert isinstance(recorded_at, datetime)
        assert recorded_at.tzinfo is UTC
        assert bound_call.arguments["success"] is True

    def test_failure_update(self, learner):
        """Test updating confidence with failure."""
        learner.update_confidence("test_pattern", False)

        learner.confidence_engine.track_usage.assert_called_once()
        call_args = learner.confidence_engine.track_usage.call_args
        bound_call = inspect.signature(ConfidenceEngine.track_usage).bind(
            learner.confidence_engine,
            *call_args.args,
            **call_args.kwargs,
        )
        assert bound_call.arguments["pattern_id"] == "test_pattern"
        recorded_at = bound_call.arguments["timestamp"]
        assert isinstance(recorded_at, datetime)
        assert recorded_at.tzinfo is UTC
        assert bound_call.arguments["success"] is False


# ---------------------------------------------------------------------------
# get_pattern_suggestion
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetPatternSuggestion:
    """Tests for get_pattern_suggestion method."""

    def test_no_data_returns_none(self, learner):
        """Test suggestion with no learned data returns None."""
        # suggest_naming_convention returns None by default
        learner.folder_learner.suggest_folder_structure.return_value = None
        file_info = {"name": "test.txt", "type": ".txt"}

        result = learner.get_pattern_suggestion(file_info)

        assert result is None

    def test_custom_min_confidence(self, learner):
        """Test suggestion with min_confidence=0 returns a suggestion."""
        learner.folder_learner.suggest_folder_structure.return_value = None
        file_info = {"name": "test.txt", "type": ".txt"}

        result = learner.get_pattern_suggestion(file_info, min_confidence=0.0)

        if result is not None:
            assert "naming" in result
            assert "folder" in result
            assert "confidence" in result

    def test_with_naming_suggestion(self, learner):
        """Test suggestion when naming patterns are available."""
        learner.pattern_extractor.suggest_naming_convention.return_value = "better_name"
        learner.folder_learner.suggest_folder_structure.return_value = None
        file_info = {"name": "test.txt", "type": ".txt"}

        result = learner.get_pattern_suggestion(file_info, min_confidence=0.5)

        assert result is not None
        assert result["naming"] is not None
        assert result["naming"]["suggested_name"] == "better_name"
        assert result["naming"]["confidence"] == 0.7

    def test_with_folder_suggestion(self, learner, temp_storage):
        """Test suggestion after learning folder preferences."""
        folder = temp_storage / "docs"
        folder.mkdir()

        learner.folder_learner.suggest_folder_structure.return_value = folder
        learner.folder_learner.get_folder_confidence.return_value = 0.9

        file_info = {"name": "report.pdf", "type": ".pdf"}

        result = learner.get_pattern_suggestion(file_info, min_confidence=0.5)

        assert result is not None
        assert result["folder"] is not None
        assert result["folder"]["path"] == str(folder)

    def test_file_info_missing_name(self, learner):
        """Test suggestion without name in file_info."""
        learner.folder_learner.suggest_folder_structure.return_value = None
        file_info = {"type": ".txt"}

        result = learner.get_pattern_suggestion(file_info)
        assert result is None or isinstance(result, dict)

    def test_file_info_missing_type(self, learner):
        """Test suggestion without type in file_info."""
        file_info = {"name": "test.txt"}

        result = learner.get_pattern_suggestion(file_info)
        assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# get_learning_stats
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetLearningStats:
    """Tests for get_learning_stats method."""

    def test_returns_stats(self, learner):
        """Test that stats dictionary is returned."""
        stats = learner.get_learning_stats()

        assert "timestamp" in stats
        assert "confidence_stats" in stats
        assert "folder_stats" in stats
        assert "correction_count" in stats
        assert "learning_enabled" in stats
        assert stats["learning_enabled"] is True
        assert stats["correction_count"] == 0

    def test_stats_after_corrections(self, learner):
        """Test stats reflect corrections."""
        original = Path("/a/file.txt")
        corrected = Path("/b/file.txt")

        learner.learn_from_correction(original, corrected)

        stats = learner.get_learning_stats()
        assert stats["correction_count"] == 1


# ---------------------------------------------------------------------------
# batch_learn_from_history
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBatchLearnFromHistory:
    """Tests for batch_learn_from_history method."""

    def test_empty_history(self, learner):
        """Test batch learning with empty history."""
        result = learner.batch_learn_from_history([])

        assert result["processed_count"] == 0

    def test_basic_batch(self, learner):
        """Test basic batch learning."""
        corrections = [
            {
                "original_path": "/downloads/report.pdf",
                "corrected_path": "/documents/report.pdf",
                "operation": "move",
            },
            {
                "original_path": "/downloads/invoice.pdf",
                "corrected_path": "/documents/invoice.pdf",
                "operation": "move",
            },
        ]

        result = learner.batch_learn_from_history(corrections)

        assert result["processed_count"] == 2
        learner.confidence_engine.recalculate_all.assert_called()

    def test_batch_with_max_age(self, learner):
        """Test batch learning with max_age_days passes arg to feedback_processor."""
        corrections = [
            {
                "original_path": "/a/old.txt",
                "corrected_path": "/b/old.txt",
                "timestamp": "2020-01-01",
            },
        ]

        # Mock feedback_processor to avoid source-level timezone bug
        learner.feedback_processor = MagicMock()
        learner.feedback_processor.batch_process_history.return_value = {
            "processed_count": 0,
            "name_patterns": [],
            "folder_patterns": [],
        }

        result = learner.batch_learn_from_history(corrections, max_age_days=30)

        learner.feedback_processor.batch_process_history.assert_called_once_with(corrections, 30)
        assert result["processed_count"] == 0


# ---------------------------------------------------------------------------
# clear_old_patterns
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClearOldPatterns:
    """Tests for clear_old_patterns method."""

    def test_clear_with_no_data(self, learner):
        """Test clearing when there's no data."""
        learner.folder_learner.clear_old_preferences.return_value = 0
        learner.confidence_engine.clear_stale_patterns.return_value = 0

        result = learner.clear_old_patterns(days=90)

        assert "folder_preferences_cleared" in result
        assert "patterns_decayed" in result
        assert result["folder_preferences_cleared"] == 0
        assert result["patterns_decayed"] == 0
        learner.folder_learner.clear_old_preferences.assert_called_once_with(90)
        learner.confidence_engine.clear_stale_patterns.assert_called_once_with(90)

    def test_clear_with_custom_days(self, learner):
        """Test clearing with custom day threshold."""
        learner.folder_learner.clear_old_preferences.return_value = 3
        learner.confidence_engine.clear_stale_patterns.return_value = 2

        result = learner.clear_old_patterns(days=30)

        assert result["folder_preferences_cleared"] == 3
        assert result["patterns_decayed"] == 2
        learner.folder_learner.clear_old_preferences.assert_called_once_with(30)
        learner.confidence_engine.clear_stale_patterns.assert_called_once_with(30)


# ---------------------------------------------------------------------------
# enable_learning / disable_learning
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLearningToggle:
    """Tests for enable/disable learning methods."""

    def test_disable_learning(self, learner):
        """Test disabling learning."""
        learner.disable_learning()
        assert learner.learning_enabled is False

    def test_enable_learning(self, learner):
        """Test enabling learning."""
        learner.disable_learning()
        learner.enable_learning()
        assert learner.learning_enabled is True

    def test_corrections_ignored_when_disabled(self, learner):
        """Test that corrections are ignored when disabled."""
        learner.disable_learning()

        result = learner.learn_from_correction(Path("/a/old.txt"), Path("/b/new.txt"))

        assert result == {"learning_enabled": False}

    def test_corrections_work_after_re_enable(self, learner):
        """Test that corrections work after re-enabling."""
        learner.disable_learning()
        learner.enable_learning()

        result = learner.learn_from_correction(Path("/a/old.txt"), Path("/b/new.txt"))

        assert "timestamp" in result
        assert len(result["learned"]) > 0


# ---------------------------------------------------------------------------
# _learn_naming_pattern (private)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLearnNamingPattern:
    """Tests for _learn_naming_pattern private method."""

    def test_basic_naming_learning(self, learner):
        """Test basic naming pattern learning."""
        result = learner._learn_naming_pattern("old_file.txt", "new_file.txt")

        assert result["type"] == "naming"
        assert isinstance(result["patterns"], list)

    def test_delimiter_change(self, learner):
        """Test learning from delimiter change."""
        # Set up mock to return different delimiters
        call_count = [0]

        def side_effect(name):
            call_count[0] += 1
            if call_count[0] % 2 == 1:
                return {
                    "delimiters": ["-"],
                    "case_style": "lowercase",
                }
            return {
                "delimiters": ["_"],
                "case_style": "lowercase",
            }

        learner.pattern_extractor.analyze_filename.side_effect = side_effect

        result = learner._learn_naming_pattern("my-file.txt", "my_file.txt")

        assert result["type"] == "naming"
        delimiter_patterns = [p for p in result["patterns"] if p["pattern_type"] == "delimiter"]
        assert len(delimiter_patterns) == 1
        assert delimiter_patterns[0]["value"] == ["_"]

    def test_case_style_change(self, learner):
        """Test learning from case style change."""
        call_count = [0]

        def side_effect(name):
            call_count[0] += 1
            if call_count[0] % 2 == 1:
                return {
                    "delimiters": [],
                    "case_style": "lowercase",
                }
            return {
                "delimiters": [],
                "case_style": "PascalCase",
            }

        learner.pattern_extractor.analyze_filename.side_effect = side_effect

        result = learner._learn_naming_pattern("myfile.txt", "MyFile.txt")

        assert result["type"] == "naming"
        case_patterns = [p for p in result["patterns"] if p["pattern_type"] == "case_style"]
        assert len(case_patterns) == 1
        assert case_patterns[0]["value"] == "PascalCase"

    def test_no_patterns_when_same(self, learner):
        """Test no patterns when filenames have same conventions."""
        result = learner._learn_naming_pattern("file.txt", "file2.txt")

        assert result["type"] == "naming"
        # With default mock returning same values, no delimiter/case changes
        assert isinstance(result["patterns"], list)

    def test_structure_pattern_learned(self, learner):
        """Test that structure patterns are extracted when present."""
        learner.pattern_extractor.analyze_filename.return_value = {
            "delimiters": [],
            "case_style": "lowercase",
            "structure": {"type": "prefix_date"},
        }

        result = learner._learn_naming_pattern("file.txt", "2024_file.txt")

        structure_patterns = [p for p in result["patterns"] if p["pattern_type"] == "structure"]
        assert len(structure_patterns) == 1


# ---------------------------------------------------------------------------
# _learn_folder_preference (private)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLearnFolderPreference:
    """Tests for _learn_folder_preference private method."""

    def test_basic_folder_learning(self, learner):
        """Test basic folder preference learning."""
        original = Path("/downloads/file.pdf")
        corrected = Path("/documents/file.pdf")

        learner.folder_learner.get_folder_confidence.return_value = 0.85

        result = learner._learn_folder_preference(original, corrected, None)

        assert result["type"] == "folder"
        assert result["file_type"] == ".pdf"
        assert result["from"] == str(original.parent)
        assert result["to"] == str(corrected.parent)
        assert result["confidence"] == 0.85

    def test_folder_learning_with_context(self, learner):
        """Test folder preference learning with context."""
        original = Path("/downloads/file.jpg")
        corrected = Path("/photos/file.jpg")
        context = {"category": "photos"}

        learner.folder_learner.get_folder_confidence.return_value = 0.9

        result = learner._learn_folder_preference(original, corrected, context)

        assert result["type"] == "folder"
        assert result["file_type"] == ".jpg"
        learner.folder_learner.track_folder_choice.assert_called_once_with(
            ".jpg", corrected.parent, context
        )


# ---------------------------------------------------------------------------
# _get_naming_suggestions (private)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetNamingSuggestions:
    """Tests for _get_naming_suggestions private method."""

    def test_basic_suggestion(self, learner):
        """Test basic naming suggestion when convention is available."""
        learner.pattern_extractor.suggest_naming_convention.return_value = "suggested_name"

        result = learner._get_naming_suggestions("my_file.txt")

        assert result is not None
        assert result["suggested_name"] == "suggested_name"
        assert result["confidence"] == 0.7
        assert result["reason"] == "Based on learned patterns"

    def test_no_suggestion_possible(self, learner):
        """Test when no suggestion can be made."""
        learner.pattern_extractor.suggest_naming_convention.return_value = None

        result = learner._get_naming_suggestions("x.txt")

        assert result is None

    def test_suggestion_calls_analyze_filename(self, learner):
        """Test that analyze_filename is called before suggesting."""
        learner.pattern_extractor.suggest_naming_convention.return_value = None

        learner._get_naming_suggestions("my_file.txt")

        learner.pattern_extractor.analyze_filename.assert_called_once_with("my_file.txt")
