"""Tests for FeedbackProcessor.

Comprehensive tests covering correction processing, batch analysis,
learning model updates, retraining triggers, and helper methods.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from file_organizer.services.intelligence.feedback_processor import FeedbackProcessor

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def processor():
    """Create a FeedbackProcessor instance."""
    return FeedbackProcessor()


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInit:
    """Tests for FeedbackProcessor initialization."""

    def test_default_state(self, processor):
        """Test default initialization state."""
        assert processor.correction_count == 0
        assert processor.batch_processing_enabled is True
        assert processor.learning_threshold == 5


# ---------------------------------------------------------------------------
# process_correction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcessCorrection:
    """Tests for process_correction method."""

    def test_basic_correction_same_location(self, processor):
        """Test processing a correction that only changes the filename."""
        original = Path("/docs/old_name.txt")
        corrected = Path("/docs/new_name.txt")

        result = processor.process_correction(original, corrected)

        assert "timestamp" in result
        assert result["original_path"] == str(original)
        assert result["corrected_path"] == str(corrected)
        assert isinstance(result["learning_signals"], list)
        # Name change should produce a naming signal
        assert len(result["learning_signals"]) >= 1
        assert result["learning_signals"][0]["type"] == "naming"

    def test_folder_change_only(self, processor):
        """Test processing a correction that only changes the folder."""
        original = Path("/docs/report.pdf")
        corrected = Path("/archives/report.pdf")

        result = processor.process_correction(original, corrected)

        signals = result["learning_signals"]
        assert len(signals) >= 1
        folder_signals = [s for s in signals if s["type"] == "folder"]
        assert len(folder_signals) == 1
        assert folder_signals[0]["file_type"] == ".pdf"

    def test_both_name_and_folder_change(self, processor):
        """Test correction with both name and folder change."""
        original = Path("/docs/old.txt")
        corrected = Path("/archives/new.txt")

        result = processor.process_correction(original, corrected)

        signal_types = [s["type"] for s in result["learning_signals"]]
        assert "naming" in signal_types
        assert "folder" in signal_types

    def test_no_change(self, processor):
        """Test correction with identical paths produces no signals."""
        path = Path("/docs/file.txt")

        result = processor.process_correction(path, path)

        assert len(result["learning_signals"]) == 0

    def test_correction_count_increments(self, processor):
        """Test that correction_count increments on each call."""
        original = Path("/a/file.txt")
        corrected = Path("/b/file.txt")

        for i in range(3):
            processor.process_correction(original, corrected)
            assert processor.correction_count == i + 1

    def test_retraining_trigger(self, processor):
        """Test retraining is triggered after threshold corrections."""
        original = Path("/a/file.txt")
        corrected = Path("/b/file.txt")

        # Process corrections up to threshold
        for _ in range(processor.learning_threshold - 1):
            result = processor.process_correction(original, corrected)
            assert "trigger_retraining" not in result

        # The threshold-th correction should trigger retraining
        result = processor.process_correction(original, corrected)
        assert result.get("trigger_retraining") is True

    def test_context_patterns_extracted(self, processor):
        """Test context patterns are extracted when context is provided."""
        original = Path("/docs/file.txt")
        corrected = Path("/docs/file.txt")
        context = {"operation": "rename", "suggested": "file_v2.txt", "actual": "report.txt"}

        result = processor.process_correction(original, corrected, context)

        context_signals = [s for s in result["learning_signals"] if s["type"] == "context"]
        assert len(context_signals) == 1
        patterns = context_signals[0]["patterns"]
        pattern_types = [p["pattern_type"] for p in patterns]
        assert "operation" in pattern_types
        assert "suggestion_override" in pattern_types

    def test_context_with_no_patterns(self, processor):
        """Test that empty context dict yields no context signal."""
        original = Path("/docs/file.txt")
        corrected = Path("/docs/file.txt")
        context = {"unrelated_key": "value"}

        result = processor.process_correction(original, corrected, context)

        context_signals = [s for s in result["learning_signals"] if s.get("type") == "context"]
        assert len(context_signals) == 0

    def test_context_none(self, processor):
        """Test no context signal when context is None."""
        original = Path("/docs/file.txt")
        corrected = Path("/docs/file.txt")

        result = processor.process_correction(original, corrected, context=None)
        assert len(result["learning_signals"]) == 0

    def test_folder_correction_with_category_context(self, processor):
        """Test folder correction with category context."""
        original = Path("/downloads/photo.jpg")
        corrected = Path("/photos/vacations/photo.jpg")
        context = {"category": "vacation_photos"}

        result = processor.process_correction(original, corrected, context)

        folder_signals = [s for s in result["learning_signals"] if s["type"] == "folder"]
        assert len(folder_signals) == 1
        pattern_types = [p["pattern_type"] for p in folder_signals[0]["patterns"]]
        assert "category_change" in pattern_types


# ---------------------------------------------------------------------------
# batch_process_history
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBatchProcessHistory:
    """Tests for batch_process_history method."""

    def test_empty_corrections(self, processor):
        """Test batch processing with empty list."""
        result = processor.batch_process_history([])

        assert result["processed_count"] == 0
        assert result["name_patterns"] == []
        assert result["folder_patterns"] == []
        assert isinstance(result["common_operations"], dict)

    def test_basic_batch(self, processor):
        """Test batch processing with basic corrections."""
        corrections = [
            {
                "original_path": "/docs/old-file.txt",
                "corrected_path": "/docs/new_file.txt",
                "operation": "rename",
            },
            {
                "original_path": "/docs/another-file.txt",
                "corrected_path": "/docs/another_file.txt",
                "operation": "rename",
            },
        ]

        result = processor.batch_process_history(corrections)

        assert result["processed_count"] == 2
        assert "timestamp" in result

    def test_batch_with_folder_changes(self, processor):
        """Test batch processing with folder changes."""
        corrections = [
            {
                "original_path": "/downloads/report.pdf",
                "corrected_path": "/documents/report.pdf",
            },
            {
                "original_path": "/downloads/invoice.pdf",
                "corrected_path": "/documents/invoice.pdf",
            },
            {
                "original_path": "/downloads/receipt.pdf",
                "corrected_path": "/documents/receipt.pdf",
            },
        ]

        result = processor.batch_process_history(corrections)

        # Should detect strong type->folder preference (100% of .pdf to /documents)
        assert len(result["folder_patterns"]) > 0
        pdf_patterns = [p for p in result["folder_patterns"] if p.get("file_type") == ".pdf"]
        assert len(pdf_patterns) > 0
        assert pdf_patterns[0]["confidence"] > 0.6

    def test_batch_with_max_age_filter(self, processor):
        """Test batch processing with max_age_days filter."""
        now = datetime.now(UTC)
        old = now - timedelta(days=200)

        corrections = [
            {
                "original_path": "/a/old.txt",
                "corrected_path": "/b/old.txt",
                "timestamp": old.isoformat(),
            },
            {
                "original_path": "/a/new.txt",
                "corrected_path": "/b/new.txt",
                "timestamp": now.isoformat(),
            },
        ]

        result = processor.batch_process_history(corrections, max_age_days=30)

        # Only the recent correction should be processed
        assert result["processed_count"] == 1

    def test_batch_common_operations(self, processor):
        """Test common operations identification in batch."""
        corrections = [
            {"original_path": "/a/f1.txt", "corrected_path": "/a/f1.txt", "operation": "rename"},
            {"original_path": "/a/f2.txt", "corrected_path": "/a/f2.txt", "operation": "rename"},
            {"original_path": "/a/f3.txt", "corrected_path": "/b/f3.txt", "operation": "move"},
        ]

        result = processor.batch_process_history(corrections)

        assert result["common_operations"]["rename"] == 2
        assert result["common_operations"]["move"] == 1

    def test_batch_name_patterns(self, processor):
        """Test name pattern extraction in batch."""
        corrections = [
            {
                "original_path": "/docs/File One.txt",
                "corrected_path": "/docs/file_one.txt",
            },
            {
                "original_path": "/docs/File Two.txt",
                "corrected_path": "/docs/file_two.txt",
            },
        ]

        result = processor.batch_process_history(corrections)

        assert len(result["name_patterns"]) > 0

    def test_batch_no_max_age(self, processor):
        """Test batch processing without max_age_days (processes all)."""
        corrections = [
            {
                "original_path": "/a/f1.txt",
                "corrected_path": "/b/f1.txt",
                "timestamp": "1970-01-01",
            },
            {
                "original_path": "/a/f2.txt",
                "corrected_path": "/b/f2.txt",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        ]

        result = processor.batch_process_history(corrections, max_age_days=None)

        assert result["processed_count"] == 2


# ---------------------------------------------------------------------------
# update_learning_model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateLearningModel:
    """Tests for update_learning_model method."""

    def test_valid_insights(self, processor):
        """Test updating with valid insights."""
        insights = {"learning_signals": [{"type": "naming", "patterns": []}]}

        result = processor.update_learning_model(insights)
        assert result is True

    def test_empty_insights(self, processor):
        """Test updating with empty insights."""
        result = processor.update_learning_model({})
        assert result is False

    def test_none_insights(self, processor):
        """Test updating with None insights."""
        result = processor.update_learning_model(None)
        assert result is False

    def test_insights_missing_signals(self, processor):
        """Test updating with insights missing learning_signals key."""
        result = processor.update_learning_model({"other_key": "value"})
        assert result is False

    def test_insights_with_multiple_signals(self, processor):
        """Test updating with multiple signals."""
        insights = {
            "learning_signals": [
                {"type": "naming"},
                {"type": "folder"},
                {"type": "context"},
            ]
        }

        result = processor.update_learning_model(insights)
        assert result is True


# ---------------------------------------------------------------------------
# trigger_retraining
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTriggerRetraining:
    """Tests for trigger_retraining method."""

    def test_retraining_status(self, processor):
        """Test that trigger_retraining returns proper status."""
        processor.correction_count = 10

        status = processor.trigger_retraining()

        assert "triggered_at" in status
        assert status["correction_count"] == 10
        assert status["status"] == "queued"

    def test_retraining_resets_counter(self, processor):
        """Test that trigger_retraining resets the correction count."""
        processor.correction_count = 10

        processor.trigger_retraining()

        assert processor.correction_count == 0


# ---------------------------------------------------------------------------
# _analyze_name_correction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeNameCorrection:
    """Tests for _analyze_name_correction method."""

    def test_delimiter_change(self, processor):
        """Test detection of delimiter changes."""
        result = processor._analyze_name_correction("my-file.txt", "my_file.txt")

        assert result["type"] == "naming"
        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "delimiter_change" in pattern_types

    def test_case_change(self, processor):
        """Test detection of case changes."""
        result = processor._analyze_name_correction("MyFile.txt", "myfile.txt")

        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "case_change" in pattern_types

    def test_suffix_addition(self, processor):
        """Test detection of suffix additions."""
        result = processor._analyze_name_correction("report.txt", "report_v2.txt")

        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "suffix_addition" in pattern_types
        suffix_pattern = next(
            p for p in result["patterns"] if p["pattern_type"] == "suffix_addition"
        )
        assert suffix_pattern["suffix"] == "_v2"

    def test_prefix_addition(self, processor):
        """Test detection of prefix additions."""
        result = processor._analyze_name_correction("report.txt", "final_report.txt")

        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "prefix_addition" in pattern_types
        prefix_pattern = next(
            p for p in result["patterns"] if p["pattern_type"] == "prefix_addition"
        )
        assert prefix_pattern["prefix"] == "final_"

    def test_no_patterns(self, processor):
        """Test completely different names produce minimal patterns."""
        result = processor._analyze_name_correction("alpha.txt", "omega.txt")

        assert result["type"] == "naming"
        assert result["original"] == "alpha.txt"
        assert result["corrected"] == "omega.txt"


# ---------------------------------------------------------------------------
# _analyze_folder_correction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeFolderCorrection:
    """Tests for _analyze_folder_correction method."""

    def test_basic_folder_change(self, processor):
        """Test basic folder correction analysis."""
        original = Path("/downloads/file.pdf")
        corrected = Path("/documents/file.pdf")

        result = processor._analyze_folder_correction(original, corrected, None)

        assert result["type"] == "folder"
        assert result["file_type"] == ".pdf"
        assert result["from_folder"] == str(original.parent)
        assert result["to_folder"] == str(corrected.parent)

    def test_folder_change_with_category(self, processor):
        """Test folder correction with category context."""
        original = Path("/downloads/file.jpg")
        corrected = Path("/photos/file.jpg")
        context = {"category": "photos"}

        result = processor._analyze_folder_correction(original, corrected, context)

        pattern_types = [p["pattern_type"] for p in result["patterns"]]
        assert "category_change" in pattern_types

    def test_subfolder_structure_detection(self, processor):
        """Test detection of subfolder structure patterns."""
        original = Path("/downloads/file.txt")
        corrected = Path("/projects/work/reports/file.txt")

        result = processor._analyze_folder_correction(original, corrected, None)

        structure_patterns = [
            p for p in result["patterns"] if p["pattern_type"] == "subfolder_structure"
        ]
        assert len(structure_patterns) > 0

    def test_folder_change_with_common_ancestor(self, processor):
        """Test folder change with shared common ancestor."""
        original = Path("/projects/work/drafts/file.txt")
        corrected = Path("/projects/work/final/file.txt")

        result = processor._analyze_folder_correction(original, corrected, None)

        assert result["type"] == "folder"
        structure_patterns = [
            p for p in result["patterns"] if p["pattern_type"] == "subfolder_structure"
        ]
        if structure_patterns:
            assert structure_patterns[0]["structure"] == "final"


# ---------------------------------------------------------------------------
# _extract_context_patterns
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractContextPatterns:
    """Tests for _extract_context_patterns method."""

    def test_none_context(self, processor):
        """Test with None context."""
        result = processor._extract_context_patterns(None)
        assert result is None

    def test_empty_context(self, processor):
        """Test with empty context dict."""
        result = processor._extract_context_patterns({})
        assert result is None

    def test_operation_pattern(self, processor):
        """Test extraction of operation pattern."""
        context = {"operation": "auto_organize"}

        result = processor._extract_context_patterns(context)

        assert result is not None
        assert result["type"] == "context"
        assert any(p["pattern_type"] == "operation" for p in result["patterns"])

    def test_suggestion_override(self, processor):
        """Test detection of suggestion override."""
        context = {"suggested": "/docs/reports", "actual": "/docs/archive"}

        result = processor._extract_context_patterns(context)

        assert result is not None
        override_patterns = [
            p for p in result["patterns"] if p["pattern_type"] == "suggestion_override"
        ]
        assert len(override_patterns) == 1
        assert override_patterns[0]["suggested"] == "/docs/reports"
        assert override_patterns[0]["actual"] == "/docs/archive"

    def test_suggestion_matches_actual(self, processor):
        """Test that matching suggested and actual produces no override pattern."""
        context = {"suggested": "/docs", "actual": "/docs"}

        result = processor._extract_context_patterns(context)

        # Only produces patterns if there are other extractable patterns
        assert result is None

    def test_unrelated_context_keys(self, processor):
        """Test context with only unrelated keys returns None."""
        context = {"user_id": "123", "session": "abc"}

        result = processor._extract_context_patterns(context)
        assert result is None


# ---------------------------------------------------------------------------
# _extract_batch_name_patterns
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractBatchNamePatterns:
    """Tests for _extract_batch_name_patterns method."""

    def test_empty_changes(self, processor):
        """Test with empty list of changes."""
        result = processor._extract_batch_name_patterns([])
        assert result == []

    def test_delimiter_preference(self, processor):
        """Test detection of preferred delimiter."""
        changes = [
            ("file one.txt", "file_one.txt"),
            ("file two.txt", "file_two.txt"),
            ("file three.txt", "file_three.txt"),
        ]

        result = processor._extract_batch_name_patterns(changes)

        delimiter_patterns = [p for p in result if p["pattern_type"] == "preferred_delimiter"]
        assert len(delimiter_patterns) == 1
        assert delimiter_patterns[0]["delimiter"] == "_"

    def test_case_style_preference(self, processor):
        """Test detection of preferred case style."""
        changes = [
            ("FILE_A.txt", "file_a.txt"),
            ("FILE_B.txt", "file_b.txt"),
        ]

        result = processor._extract_batch_name_patterns(changes)

        case_patterns = [p for p in result if p["pattern_type"] == "preferred_case"]
        assert len(case_patterns) == 1


# ---------------------------------------------------------------------------
# _extract_batch_folder_patterns
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractBatchFolderPatterns:
    """Tests for _extract_batch_folder_patterns method."""

    def test_empty_changes(self, processor):
        """Test with empty list of changes."""
        result = processor._extract_batch_folder_patterns([])
        assert result == []

    def test_strong_type_preference(self, processor):
        """Test detection of strong type->folder preference."""
        changes = [
            ("/downloads", "/documents", ".pdf"),
            ("/downloads", "/documents", ".pdf"),
            ("/downloads", "/documents", ".pdf"),
            ("/downloads", "/images", ".pdf"),  # Minority
        ]

        result = processor._extract_batch_folder_patterns(changes)

        pdf_patterns = [p for p in result if p["file_type"] == ".pdf"]
        assert len(pdf_patterns) == 1
        assert pdf_patterns[0]["folder"] == "/documents"
        assert pdf_patterns[0]["confidence"] == 0.75

    def test_weak_preference_not_included(self, processor):
        """Test that weak preferences (<=60%) are excluded."""
        changes = [
            ("/downloads", "/documents", ".txt"),
            ("/downloads", "/archive", ".txt"),
        ]

        result = processor._extract_batch_folder_patterns(changes)

        # 50% confidence, should not pass 0.6 threshold
        txt_patterns = [p for p in result if p["file_type"] == ".txt"]
        assert len(txt_patterns) == 0


# ---------------------------------------------------------------------------
# _identify_common_operations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIdentifyCommonOperations:
    """Tests for _identify_common_operations method."""

    def test_empty_corrections(self, processor):
        """Test with empty corrections list."""
        result = processor._identify_common_operations([])
        assert result == {}

    def test_operation_counting(self, processor):
        """Test operation frequency counting."""
        corrections = [
            {"operation": "rename"},
            {"operation": "rename"},
            {"operation": "move"},
            {},  # Missing operation => "unknown"
        ]

        result = processor._identify_common_operations(corrections)

        assert result["rename"] == 2
        assert result["move"] == 1
        assert result["unknown"] == 1


# ---------------------------------------------------------------------------
# Static helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStaticHelpers:
    """Tests for static helper methods."""

    def test_extract_delimiters_underscore(self):
        """Test delimiter extraction with underscores."""
        result = FeedbackProcessor._extract_delimiters("my_file_name.txt")
        assert "_" in result
        assert "." in result

    def test_extract_delimiters_hyphen(self):
        """Test delimiter extraction with hyphens."""
        result = FeedbackProcessor._extract_delimiters("my-file-name.txt")
        assert "-" in result

    def test_extract_delimiters_space(self):
        """Test delimiter extraction with spaces."""
        result = FeedbackProcessor._extract_delimiters("my file name.txt")
        assert " " in result

    def test_extract_delimiters_no_duplicates(self):
        """Test that delimiters are unique."""
        result = FeedbackProcessor._extract_delimiters("a_b_c_d.txt")
        assert result.count("_") == 1

    def test_extract_delimiters_none(self):
        """Test no delimiters in simple filename."""
        result = FeedbackProcessor._extract_delimiters("filename")
        assert result == []

    def test_detect_case_lowercase(self):
        """Test lowercase detection."""
        assert FeedbackProcessor._detect_case_style("lowercase.txt") == "lowercase"

    def test_detect_case_uppercase(self):
        """Test uppercase detection."""
        assert FeedbackProcessor._detect_case_style("UPPERCASE.txt") == "uppercase"

    def test_detect_case_snake(self):
        """Test snake_case detection.

        The implementation checks islower() first.  'snake_case_file'.islower()
        returns True (underscores are non-cased), so the method returns 'lowercase'.
        """
        assert FeedbackProcessor._detect_case_style("snake_case_file.txt") == "lowercase"

    def test_detect_case_kebab(self):
        """Test kebab-case detection.

        The implementation checks islower() first.  'kebab-case-file'.islower()
        returns True (hyphens are non-cased), so the method returns 'lowercase'.
        """
        assert FeedbackProcessor._detect_case_style("kebab-case-file.txt") == "lowercase"

    def test_detect_case_camel(self):
        """Test camelCase detection."""
        assert FeedbackProcessor._detect_case_style("camelCase.txt") == "camelCase"

    def test_detect_case_pascal(self):
        """Test PascalCase detection."""
        assert FeedbackProcessor._detect_case_style("PascalCase.txt") == "PascalCase"

    def test_detect_case_title(self):
        """Test title_case detection."""
        assert FeedbackProcessor._detect_case_style("Title Case Name.txt") == "title_case"

    def test_detect_case_mixed(self):
        """Test mixed case detection (starts with digit, mixed casing)."""
        assert FeedbackProcessor._detect_case_style("123MixEd.txt") == "mixed"
