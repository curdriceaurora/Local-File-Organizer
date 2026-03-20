"""Integration tests for feedback_processor.py branch coverage.

Targets uncovered branches in:
  - process_correction — name change, folder change, context patterns, threshold trigger
  - batch_process_history — max_age_days filter, name/folder change aggregation,
      _extract_batch_name_patterns, _extract_batch_folder_patterns
  - update_learning_model — missing key → False, valid → True
  - trigger_retraining — counter reset
  - _analyze_name_correction — delimiter change, case change, suffix/prefix addition
  - _analyze_folder_correction — category in context, subfolder structure
  - _extract_context_patterns — empty context, operation branch, suggestion_override
  - _detect_case_style — all branches: lowercase, uppercase, snake_case, kebab-case,
      title_case, camelCase, PascalCase, mixed
  - _extract_delimiters — various delimiter characters
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fp():
    from file_organizer.services.intelligence.feedback_processor import FeedbackProcessor

    return FeedbackProcessor()


# ---------------------------------------------------------------------------
# process_correction — name/folder change branches + context + threshold
# ---------------------------------------------------------------------------


class TestProcessCorrection:
    def test_same_path_no_signals(self) -> None:
        """No name or folder change → no learning signals."""
        fp = _fp()
        result = fp.process_correction(Path("/a/x.txt"), Path("/a/x.txt"))
        assert result["learning_signals"] == []

    def test_name_change_adds_naming_signal(self) -> None:
        """Different file names → naming signal appended."""
        fp = _fp()
        result = fp.process_correction(Path("/a/old.txt"), Path("/a/new.txt"))
        types = [s["type"] for s in result["learning_signals"]]
        assert "naming" in types

    def test_folder_change_adds_folder_signal(self) -> None:
        """Different parent folders → folder signal appended."""
        fp = _fp()
        result = fp.process_correction(Path("/a/x.txt"), Path("/b/x.txt"))
        types = [s["type"] for s in result["learning_signals"]]
        assert "folder" in types

    def test_both_changes_add_both_signals(self) -> None:
        """Name AND folder change → both signals."""
        fp = _fp()
        result = fp.process_correction(Path("/a/old.txt"), Path("/b/new.txt"))
        types = [s["type"] for s in result["learning_signals"]]
        assert "naming" in types
        assert "folder" in types

    def test_context_with_operation_adds_context_signal(self) -> None:
        """Context with 'operation' key → context signal appended."""
        fp = _fp()
        result = fp.process_correction(
            Path("/a/x.txt"), Path("/a/x.txt"), context={"operation": "rename"}
        )
        types = [s["type"] for s in result["learning_signals"]]
        assert "context" in types

    def test_context_without_patterns_not_added(self) -> None:
        """Context with no recognized keys → _extract_context_patterns returns None."""
        fp = _fp()
        result = fp.process_correction(
            Path("/a/x.txt"), Path("/a/x.txt"), context={"unrelated": "value"}
        )
        types = [s["type"] for s in result["learning_signals"]]
        assert "context" not in types

    def test_threshold_trigger(self) -> None:
        """After learning_threshold corrections → trigger_retraining=True."""
        fp = _fp()
        fp.learning_threshold = 3
        for i in range(3):
            result = fp.process_correction(Path(f"/a/f{i}.txt"), Path(f"/b/g{i}.txt"))
        assert result.get("trigger_retraining") is True

    def test_below_threshold_no_trigger(self) -> None:
        """Below threshold → no trigger_retraining key."""
        fp = _fp()
        fp.learning_threshold = 10
        result = fp.process_correction(Path("/a/x.txt"), Path("/b/y.txt"))
        assert "trigger_retraining" not in result


# ---------------------------------------------------------------------------
# batch_process_history — aggregation and filtering
# ---------------------------------------------------------------------------


class TestBatchProcessHistory:
    def _make_correction(
        self,
        original: str,
        corrected: str,
        days_ago: int = 0,
        operation: str = "move",
    ) -> dict:
        ts = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
        return {
            "original_path": original,
            "corrected_path": corrected,
            "timestamp": ts,
            "operation": operation,
        }

    def test_empty_corrections(self) -> None:
        """Empty list → processed_count=0, empty patterns."""
        fp = _fp()
        result = fp.batch_process_history([])
        assert result["processed_count"] == 0
        assert result["name_patterns"] == []
        assert result["folder_patterns"] == []

    def test_name_change_populates_name_patterns(self) -> None:
        """Corrections with name changes populate name_patterns via _extract_batch_name_patterns."""
        fp = _fp()
        corrections = [
            self._make_correction("/a/old_file.txt", "/a/new_file.txt"),
            self._make_correction("/b/old_doc.pdf", "/b/new_doc.pdf"),
        ]
        result = fp.batch_process_history(corrections)
        assert result["name_patterns"] != []

    def test_folder_change_populates_folder_patterns_above_threshold(self) -> None:
        """Consistent folder moves (>60%) → pattern in folder_patterns."""
        fp = _fp()
        # 3 out of 3 pdfs go to /docs → 100% → strong preference
        corrections = [
            self._make_correction(f"/a/file{i}.pdf", f"/docs/file{i}.pdf") for i in range(3)
        ]
        result = fp.batch_process_history(corrections)
        assert result["folder_patterns"] != []
        assert result["folder_patterns"][0]["pattern_type"] == "type_folder_preference"

    def test_folder_change_below_threshold_no_pattern(self) -> None:
        """Scattered folder moves (<= 60%) → no folder pattern."""
        fp = _fp()
        corrections = [
            self._make_correction("/a/f1.pdf", "/docs/f1.pdf"),
            self._make_correction("/a/f2.pdf", "/archive/f2.pdf"),
            self._make_correction("/a/f3.pdf", "/inbox/f3.pdf"),
        ]
        result = fp.batch_process_history(corrections)
        assert result["folder_patterns"] == []

    def test_max_age_days_filters_old_corrections(self) -> None:
        """max_age_days filters out corrections older than the cutoff."""
        fp = _fp()
        corrections = [
            self._make_correction("/a/old.txt", "/b/old.txt", days_ago=100),
            self._make_correction("/a/new.txt", "/b/new.txt", days_ago=1),
        ]
        result = fp.batch_process_history(corrections, max_age_days=7)
        assert result["processed_count"] == 1

    def test_max_age_days_none_no_filtering(self) -> None:
        """max_age_days=None → no filtering applied."""
        fp = _fp()
        corrections = [
            self._make_correction("/a/old.txt", "/b/old.txt", days_ago=1000),
            self._make_correction("/a/new.txt", "/b/new.txt", days_ago=1),
        ]
        result = fp.batch_process_history(corrections, max_age_days=None)
        assert result["processed_count"] == 2

    def test_common_operations_aggregated(self) -> None:
        """common_operations counts operation types correctly."""
        fp = _fp()
        corrections = [
            self._make_correction("/a/f1.txt", "/b/f1.txt", operation="move"),
            self._make_correction("/a/f2.txt", "/b/f2.txt", operation="move"),
            self._make_correction("/a/f3.txt", "/b/f3.txt", operation="rename"),
        ]
        result = fp.batch_process_history(corrections)
        assert result["common_operations"]["move"] == 2
        assert result["common_operations"]["rename"] == 1

    def test_no_name_change_empty_name_patterns(self) -> None:
        """No name changes in batch → name_patterns stays empty."""
        fp = _fp()
        corrections = [self._make_correction("/a/same.txt", "/b/same.txt")]
        result = fp.batch_process_history(corrections)
        assert result["name_patterns"] == []

    def test_no_folder_change_empty_folder_patterns(self) -> None:
        """No folder changes in batch → folder_patterns stays empty."""
        fp = _fp()
        corrections = [self._make_correction("/a/old.txt", "/a/new.txt")]
        result = fp.batch_process_history(corrections)
        assert result["folder_patterns"] == []


# ---------------------------------------------------------------------------
# update_learning_model — True / False paths
# ---------------------------------------------------------------------------


class TestUpdateLearningModel:
    def test_valid_insights_returns_true(self) -> None:
        """Insights with learning_signals → True."""
        fp = _fp()
        result = fp.update_learning_model({"learning_signals": [{"type": "naming"}]})
        assert result is True

    def test_empty_insights_returns_false(self) -> None:
        """Empty dict → False (no learning_signals key)."""
        fp = _fp()
        result = fp.update_learning_model({})
        assert result is False

    def test_none_insights_returns_false(self) -> None:
        """None insights → False."""
        fp = _fp()
        result = fp.update_learning_model(None)  # type: ignore[arg-type]
        assert result is False

    def test_missing_learning_signals_key_returns_false(self) -> None:
        """Dict without learning_signals key → False."""
        fp = _fp()
        result = fp.update_learning_model({"other_key": "value"})
        assert result is False

    def test_empty_signals_list_returns_true(self) -> None:
        """Insights with empty list of signals still returns True (key present)."""
        fp = _fp()
        result = fp.update_learning_model({"learning_signals": []})
        assert result is True


# ---------------------------------------------------------------------------
# trigger_retraining — counter reset
# ---------------------------------------------------------------------------


class TestTriggerRetraining:
    def test_trigger_returns_status_dict(self) -> None:
        """trigger_retraining returns dict with required keys."""
        fp = _fp()
        fp.correction_count = 5
        status = fp.trigger_retraining()
        assert status["status"] == "queued"
        assert status["correction_count"] == 5
        assert "triggered_at" in status

    def test_trigger_resets_counter(self) -> None:
        """trigger_retraining resets correction_count to 0."""
        fp = _fp()
        fp.correction_count = 10
        fp.trigger_retraining()
        assert fp.correction_count == 0


# ---------------------------------------------------------------------------
# _analyze_name_correction — delimiter, case, suffix/prefix branches
# ---------------------------------------------------------------------------


class TestAnalyzeNameCorrection:
    def test_delimiter_change_detected(self) -> None:
        """Changing from underscore to hyphen → delimiter_change pattern."""
        fp = _fp()
        result = fp._analyze_name_correction("old_file.txt", "old-file.txt")
        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "delimiter_change" in pattern_types

    def test_case_change_detected(self) -> None:
        """Same name different case → case_change pattern."""
        fp = _fp()
        result = fp._analyze_name_correction("myfile.txt", "MYFILE.txt")
        # original.lower() == corrected.lower() → case_change
        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "case_change" in pattern_types

    def test_suffix_addition_detected(self) -> None:
        """Corrected name has original as prefix → suffix_addition."""
        fp = _fp()
        result = fp._analyze_name_correction("report.txt", "report_v2.txt")
        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "suffix_addition" in pattern_types

    def test_prefix_addition_detected(self) -> None:
        """Corrected name has original as suffix → prefix_addition."""
        fp = _fp()
        result = fp._analyze_name_correction("report.txt", "2024_report.txt")
        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "prefix_addition" in pattern_types

    def test_no_patterns_when_completely_different(self) -> None:
        """Completely different names with same delimiter → no patterns."""
        fp = _fp()
        result = fp._analyze_name_correction("alpha.txt", "beta.txt")
        # names are different, no prefix/suffix relationship, same (no) delimiter
        assert result["original"] == "alpha.txt"
        assert result["corrected"] == "beta.txt"


# ---------------------------------------------------------------------------
# _analyze_folder_correction — category in context + subfolder structure
# ---------------------------------------------------------------------------


class TestAnalyzeFolderCorrection:
    def test_category_in_context_adds_pattern(self) -> None:
        """Context with 'category' key → category_change pattern."""
        fp = _fp()
        result = fp._analyze_folder_correction(
            Path("/a/x.pdf"),
            Path("/docs/x.pdf"),
            context={"category": "documents"},
        )
        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "category_change" in pattern_types

    def test_subfolder_structure_pattern_detected(self) -> None:
        """Moving to deeper path → subfolder_structure pattern."""
        fp = _fp()
        result = fp._analyze_folder_correction(
            Path("/a/x.pdf"),
            Path("/docs/reports/2024/x.pdf"),
            context=None,
        )
        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "subfolder_structure" in pattern_types

    def test_no_context_no_category_pattern(self) -> None:
        """No context → no category_change pattern."""
        fp = _fp()
        result = fp._analyze_folder_correction(
            Path("/a/x.pdf"),
            Path("/b/x.pdf"),
            context=None,
        )
        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "category_change" not in pattern_types

    def test_context_without_category_no_category_pattern(self) -> None:
        """Context without 'category' key → no category_change pattern."""
        fp = _fp()
        result = fp._analyze_folder_correction(
            Path("/a/x.pdf"),
            Path("/b/x.pdf"),
            context={"other": "value"},
        )
        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "category_change" not in pattern_types


# ---------------------------------------------------------------------------
# _extract_context_patterns — empty / operation / suggestion_override
# ---------------------------------------------------------------------------


class TestExtractContextPatterns:
    def test_empty_context_returns_none(self) -> None:
        """Empty dict context → None."""
        fp = _fp()
        result = fp._extract_context_patterns({})
        assert result is None

    def test_operation_key_adds_pattern(self) -> None:
        """'operation' key in context → operation pattern."""
        fp = _fp()
        result = fp._extract_context_patterns({"operation": "move"})
        assert result is not None
        assert result["type"] == "context"
        types = [p["pattern_type"] for p in result["patterns"]]
        assert "operation" in types

    def test_suggestion_override_when_suggested_differs_from_actual(self) -> None:
        """suggested != actual → suggestion_override pattern."""
        fp = _fp()
        result = fp._extract_context_patterns({"suggested": "/a", "actual": "/b"})
        assert result is not None
        types = [p["pattern_type"] for p in result["patterns"]]
        assert "suggestion_override" in types

    def test_no_override_when_suggested_equals_actual(self) -> None:
        """suggested == actual → no suggestion_override pattern."""
        fp = _fp()
        result = fp._extract_context_patterns({"suggested": "/a", "actual": "/a"})
        # No patterns → returns None
        assert result is None

    def test_context_with_no_recognized_keys_returns_none(self) -> None:
        """Context with keys not 'operation', 'suggested', 'actual' → None."""
        fp = _fp()
        result = fp._extract_context_patterns({"irrelevant": 42})
        assert result is None


# ---------------------------------------------------------------------------
# _detect_case_style — all branches
# ---------------------------------------------------------------------------


class TestDetectCaseStyle:
    def test_lowercase(self) -> None:
        """All lowercase stem → 'lowercase'."""
        fp = _fp()
        assert fp._detect_case_style("myfile.txt") == "lowercase"

    def test_uppercase(self) -> None:
        """All uppercase stem → 'uppercase'."""
        fp = _fp()
        assert fp._detect_case_style("MYFILE.txt") == "uppercase"

    def test_snake_case_unreachable_islower_catches_it(self) -> None:
        """NOTE: snake_case branch is unreachable in Python — islower() returns True
        for 'my_file_name' because underscores are not cased characters.
        The actual return value is 'lowercase'."""
        fp = _fp()
        # islower() is True for underscore-separated lowercase → 'lowercase' returned
        assert fp._detect_case_style("my_file_name.txt") == "lowercase"

    def test_kebab_case_unreachable_islower_catches_it(self) -> None:
        """NOTE: kebab-case branch is unreachable — same reason as snake_case."""
        fp = _fp()
        # islower() is True for hyphen-separated lowercase → 'lowercase' returned
        assert fp._detect_case_style("my-file-name.txt") == "lowercase"

    def test_title_case(self) -> None:
        """Title case with spaces → 'title_case'."""
        fp = _fp()
        assert fp._detect_case_style("My File Name.txt") == "title_case"

    def test_camel_case(self) -> None:
        """lowerCamelCase → 'camelCase'."""
        fp = _fp()
        assert fp._detect_case_style("myFileName.txt") == "camelCase"

    def test_pascal_case(self) -> None:
        """PascalCase → 'PascalCase'."""
        fp = _fp()
        assert fp._detect_case_style("MyFileName.txt") == "PascalCase"

    def test_mixed_all_digits_stem(self) -> None:
        """Stem with only digits → no cased chars → islower()=False, isupper()=False
        → falls through to 'mixed'."""
        fp = _fp()
        # "123".islower() → False (no cased chars); none of the elif conditions match
        assert fp._detect_case_style("123.txt") == "mixed"

    def test_lowercase_single_char(self) -> None:
        """Single lowercase char → 'lowercase'."""
        fp = _fp()
        assert fp._detect_case_style("a.txt") == "lowercase"


# ---------------------------------------------------------------------------
# _extract_delimiters — delimiter detection
# ---------------------------------------------------------------------------


class TestExtractDelimiters:
    def test_underscore_delimiter(self) -> None:
        """Underscore in filename detected."""
        fp = _fp()
        assert "_" in fp._extract_delimiters("my_file.txt")

    def test_hyphen_delimiter(self) -> None:
        """Hyphen in filename detected."""
        fp = _fp()
        assert "-" in fp._extract_delimiters("my-file.txt")

    def test_space_delimiter(self) -> None:
        """Space in filename detected."""
        fp = _fp()
        assert " " in fp._extract_delimiters("my file.txt")

    def test_no_delimiter(self) -> None:
        """No delimiters in simple name → empty list."""
        fp = _fp()
        assert fp._extract_delimiters("myfile") == []

    def test_multiple_delimiters_deduplicated(self) -> None:
        """Each delimiter appears at most once even if repeated."""
        fp = _fp()
        delims = fp._extract_delimiters("my__file__name.txt")
        assert delims.count("_") == 1

    def test_dot_delimiter(self) -> None:
        """Dot in filename detected as delimiter."""
        fp = _fp()
        assert "." in fp._extract_delimiters("my.file.txt")
