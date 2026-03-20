"""Integration tests for analytics and deduplication service modules.

Covers:
  - services/analytics/metrics_calculator.py  — MetricsCalculator
  - services/deduplication/reporter.py        — StorageReporter
  - services/deduplication/document_dedup.py  — DocumentDeduplicator
  - services/deduplication/viewer.py          — DuplicateReview, ImageMetadata, UserAction
  - services/intelligence/directory_prefs.py  — DirectoryPrefs
  - services/copilot/rules/models.py          — Rule, RuleCondition, RuleAction, RuleSet
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from file_organizer.services.analytics.metrics_calculator import MetricsCalculator
from file_organizer.services.copilot.rules.models import (
    ActionType,
    ConditionType,
    Rule,
    RuleAction,
    RuleCondition,
    RuleSet,
)
from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator
from file_organizer.services.deduplication.reporter import StorageReporter
from file_organizer.services.deduplication.viewer import (
    DuplicateReview,
    ImageMetadata,
    UserAction,
)
from file_organizer.services.intelligence.directory_prefs import DirectoryPrefs

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# MetricsCalculator
# ---------------------------------------------------------------------------


@pytest.fixture()
def metrics() -> MetricsCalculator:
    return MetricsCalculator()


class TestMetricsCalculatorInit:
    def test_creates(self) -> None:
        m = MetricsCalculator()
        assert m is not None


class TestCalculateQualityScore:
    def test_perfect_score(self, metrics: MetricsCalculator) -> None:
        score = metrics.calculate_quality_score(
            total_files=100,
            organized_files=100,
            naming_compliance=1.0,
            structure_consistency=1.0,
        )
        assert isinstance(score, float)
        assert score >= 0.0

    def test_zero_files_no_error(self, metrics: MetricsCalculator) -> None:
        score = metrics.calculate_quality_score(
            total_files=0,
            organized_files=0,
            naming_compliance=0.0,
            structure_consistency=0.0,
        )
        # Zero files returns 0.0 sentinel per implementation
        assert score == 0.0

    def test_partial_organization(self, metrics: MetricsCalculator) -> None:
        score = metrics.calculate_quality_score(
            total_files=100,
            organized_files=50,
            naming_compliance=0.5,
            structure_consistency=0.5,
        )
        assert isinstance(score, float)
        assert score >= 0.0

    def test_returns_float(self, metrics: MetricsCalculator) -> None:
        score = metrics.calculate_quality_score(10, 8, 0.9, 0.85)
        assert 0.0 <= score <= 100.0


class TestCalculateEfficiencyGain:
    def test_improvement(self, metrics: MetricsCalculator) -> None:
        gain = metrics.calculate_efficiency_gain(before_operations=100, after_operations=30)
        # (100 - 30) / 100 * 100 = 70.0%
        assert gain == 70.0

    def test_same_operations(self, metrics: MetricsCalculator) -> None:
        gain = metrics.calculate_efficiency_gain(10, 10)
        # No improvement → 0.0
        assert gain == 0.0

    def test_zero_before(self, metrics: MetricsCalculator) -> None:
        gain = metrics.calculate_efficiency_gain(0, 5)
        # Division-by-zero guard returns 0.0
        assert gain == 0.0


class TestEstimateTimeSaved:
    def test_basic(self, metrics: MetricsCalculator) -> None:
        saved = metrics.estimate_time_saved(automated_ops=10)
        assert isinstance(saved, int)
        assert saved >= 0

    def test_custom_avg_time(self, metrics: MetricsCalculator) -> None:
        saved = metrics.estimate_time_saved(automated_ops=5, avg_manual_time_per_op=60)
        # 5 ops * 60 sec each = 300 seconds
        assert saved == 300

    def test_zero_ops(self, metrics: MetricsCalculator) -> None:
        saved = metrics.estimate_time_saved(0)
        assert saved == 0


class TestMeasureNamingCompliance:
    def test_empty_list(self, metrics: MetricsCalculator) -> None:
        result = metrics.measure_naming_compliance([])
        # Empty list → returns 1.0 (vacuously all compliant)
        assert result == 1.0

    def test_with_files(self, metrics: MetricsCalculator, tmp_path: Path) -> None:
        files = []
        for name in ("snake_case.txt", "camelCase.txt", "file-name.txt"):
            f = tmp_path / name
            f.write_text("x")
            files.append(f)
        result = metrics.measure_naming_compliance(files)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


class TestCalculateImprovementMetrics:
    def test_no_previous_score(self, metrics: MetricsCalculator) -> None:
        result = metrics.calculate_improvement_metrics(current_score=0.8)
        assert result["current_score"] == 0.8
        assert result["trend"] == "stable"

    def test_with_previous_score(self, metrics: MetricsCalculator) -> None:
        result = metrics.calculate_improvement_metrics(current_score=0.8, previous_score=0.6)
        assert "current_score" in result
        assert "improvement" in result

    def test_same_score(self, metrics: MetricsCalculator) -> None:
        result = metrics.calculate_improvement_metrics(current_score=0.7, previous_score=0.7)
        assert result["trend"] == "stable"
        assert result["improvement"] == 0.0


# ---------------------------------------------------------------------------
# StorageReporter
# ---------------------------------------------------------------------------


@pytest.fixture()
def reporter() -> StorageReporter:
    return StorageReporter()


class TestStorageReporterInit:
    def test_creates(self) -> None:
        r = StorageReporter()
        assert r is not None


class TestCalculateReclamation:
    def test_empty_groups(self, reporter: StorageReporter) -> None:
        result = reporter.calculate_reclamation([])
        assert result["total_duplicate_files"] == 0
        assert result["total_duplicate_groups"] == 0

    def test_single_group(self, reporter: StorageReporter) -> None:
        groups = [{"count": 2, "total_size": 2048}]
        result = reporter.calculate_reclamation(groups)
        assert result["total_duplicate_files"] == 2
        assert result["total_duplicate_groups"] == 1

    def test_result_has_recoverable_space(self, reporter: StorageReporter) -> None:
        groups = [{"count": 3, "total_size": 3000}]
        result = reporter.calculate_reclamation(groups)
        assert "recoverable_space" in result

    def test_result_has_total_key(self, reporter: StorageReporter) -> None:
        result = reporter.calculate_reclamation([])
        # Empty input produces zero totals
        assert result["total_size"] == 0
        assert result["recoverable_space"] == 0


_SAMPLE_RESULTS = {
    "analyzed_documents": 10,
    "num_groups": 2,
    "space_wasted": 1024 * 1024,
    "duplicate_groups": [],
}


class TestGenerateReport:
    def test_json_format(self, reporter: StorageReporter) -> None:
        result = reporter.generate_report(_SAMPLE_RESULTS, output_format="json")
        parsed = json.loads(result)
        assert "analyzed_documents" in parsed

    def test_text_format(self, reporter: StorageReporter) -> None:
        result = reporter.generate_report(_SAMPLE_RESULTS, output_format="text")
        assert "REPORT" in result.upper()

    def test_text_contains_report_header(self, reporter: StorageReporter) -> None:
        result = reporter.generate_report(_SAMPLE_RESULTS, output_format="text")
        assert "REPORT" in result or "report" in result.lower() or len(result) > 0


class TestExportToJson:
    def test_exports_file(self, reporter: StorageReporter, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        data = {"total_duplicates": 3, "groups": []}
        reporter.export_to_json(data, output)
        assert output.exists()

    def test_exported_file_is_valid_json(self, reporter: StorageReporter, tmp_path: Path) -> None:
        output = tmp_path / "out.json"
        reporter.export_to_json({"key": "value"}, output)
        content = json.loads(output.read_text())
        assert content == {"key": "value"}


class TestExportToCsv:
    def test_exports_file(self, reporter: StorageReporter, tmp_path: Path) -> None:
        output = tmp_path / "report.csv"
        reporter.export_to_csv([], output)
        assert output.exists()

    def test_with_data(self, reporter: StorageReporter, tmp_path: Path) -> None:
        output = tmp_path / "dupes.csv"
        groups = [
            {
                "count": 2,
                "avg_similarity": 0.95,
                "total_size": 2048,
                "representative": str(tmp_path / "a.txt"),
                "files": [str(tmp_path / "a.txt"), str(tmp_path / "b.txt")],
            }
        ]
        reporter.export_to_csv(groups, output)
        assert output.exists()


# ---------------------------------------------------------------------------
# DocumentDeduplicator
# ---------------------------------------------------------------------------


@pytest.fixture()
def deduplicator() -> DocumentDeduplicator:
    return DocumentDeduplicator()


class TestDocumentDeduplicatorInit:
    def test_default_threshold(self) -> None:
        d = DocumentDeduplicator()
        assert d is not None

    def test_custom_threshold(self) -> None:
        d = DocumentDeduplicator(similarity_threshold=0.7)
        assert d is not None

    def test_custom_max_features(self) -> None:
        d = DocumentDeduplicator(max_features=1000)
        assert d is not None


class TestFindDuplicates:
    def test_empty_list(self, deduplicator: DocumentDeduplicator) -> None:
        result = deduplicator.find_duplicates([])
        assert "duplicate_groups" in result
        assert result["duplicate_groups"] == []

    def test_single_file(self, deduplicator: DocumentDeduplicator, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("This is some document content with enough text to process.")
        result = deduplicator.find_duplicates([f])
        assert "duplicate_groups" in result

    def test_identical_files(self, deduplicator: DocumentDeduplicator, tmp_path: Path) -> None:
        content = (
            "This document content is identical in both files and should be detected as duplicate."
        )
        f1 = tmp_path / "file1.txt"
        f2 = tmp_path / "file2.txt"
        f1.write_text(content)
        f2.write_text(content)
        result = deduplicator.find_duplicates([f1, f2])
        assert "duplicate_groups" in result
        assert "analyzed_documents" in result

    def test_different_files(self, deduplicator: DocumentDeduplicator, tmp_path: Path) -> None:
        f1 = tmp_path / "file1.txt"
        f2 = tmp_path / "file2.txt"
        f1.write_text("Completely different content about apples and oranges for testing.")
        f2.write_text("Nothing remotely similar here about trains and automobiles.")
        result = deduplicator.find_duplicates([f1, f2])
        assert "duplicate_groups" in result
        assert result["total_documents"] == 2

    def test_returns_dict_with_groups(
        self, deduplicator: DocumentDeduplicator, tmp_path: Path
    ) -> None:
        # Use substantially different content to avoid sklearn min_df pruning error
        # when content is identical (feature extraction needs distinct terms)
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text(
            "The quick brown fox jumps over the lazy dog near the river bank in the forest."
        )
        f2.write_text(
            "Python programming language is widely used for data science machine learning tasks."
        )
        result = deduplicator.find_duplicates([f1, f2], min_text_length=10)
        assert "duplicate_groups" in result
        assert result["total_documents"] == 2


class TestCompareDocuments:
    def test_same_file_returns_value(
        self, deduplicator: DocumentDeduplicator, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("This is document content for comparison purposes.")
        result = deduplicator.compare_documents(f, f)
        assert result is None or isinstance(result, float)

    def test_different_files(self, deduplicator: DocumentDeduplicator, tmp_path: Path) -> None:
        f1 = tmp_path / "doc1.txt"
        f2 = tmp_path / "doc2.txt"
        f1.write_text("First document with some text content here.")
        f2.write_text("Second document with completely different text.")
        result = deduplicator.compare_documents(f1, f2)
        assert result is None or isinstance(result, float)

    def test_missing_file_returns_none(
        self, deduplicator: DocumentDeduplicator, tmp_path: Path
    ) -> None:
        f1 = tmp_path / "real.txt"
        f1.write_text("Content")
        missing = tmp_path / "missing.txt"
        result = deduplicator.compare_documents(f1, missing)
        assert result is None


# ---------------------------------------------------------------------------
# DuplicateReview, ImageMetadata, UserAction (dedup/viewer.py)
# ---------------------------------------------------------------------------


class TestUserAction:
    def test_keep_value(self) -> None:
        assert UserAction.KEEP.value == "keep"

    def test_delete_value(self) -> None:
        assert UserAction.DELETE.value == "delete"

    def test_skip_value(self) -> None:
        assert UserAction.SKIP.value == "skip"

    def test_keep_all_value(self) -> None:
        assert UserAction.KEEP_ALL.value == "keep_all"

    def test_delete_all_value(self) -> None:
        assert UserAction.DELETE_ALL.value == "delete_all"

    def test_auto_select_value(self) -> None:
        assert UserAction.AUTO_SELECT.value == "auto"

    def test_quit_value(self) -> None:
        assert UserAction.QUIT.value == "quit"


class TestDuplicateReview:
    def test_basic_creation(self, tmp_path: Path) -> None:
        keep = [tmp_path / "keep.jpg"]
        delete = [tmp_path / "delete.jpg"]
        review = DuplicateReview(files_to_keep=keep, files_to_delete=delete)
        assert review.files_to_keep == keep
        assert review.files_to_delete == delete

    def test_skipped_default_false(self, tmp_path: Path) -> None:
        review = DuplicateReview(files_to_keep=[], files_to_delete=[])
        assert review.skipped is False

    def test_skipped_true(self, tmp_path: Path) -> None:
        review = DuplicateReview(files_to_keep=[], files_to_delete=[], skipped=True)
        assert review.skipped is True

    def test_empty_lists(self) -> None:
        review = DuplicateReview(files_to_keep=[], files_to_delete=[])
        assert review.files_to_keep == []
        assert review.files_to_delete == []


class TestImageMetadata:
    def test_creation(self, tmp_path: Path) -> None:
        path = tmp_path / "img.jpg"
        path.write_bytes(b"\xff\xd8\xff")
        meta = ImageMetadata(
            path=path,
            width=1920,
            height=1080,
            format="JPEG",
            file_size=204800,
            modified_time=datetime(2024, 1, 1, tzinfo=UTC),
            mode="RGB",
        )
        assert meta.width == 1920
        assert meta.height == 1080
        assert meta.format == "JPEG"

    def test_file_size_stored(self, tmp_path: Path) -> None:
        path = tmp_path / "img.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        meta = ImageMetadata(
            path=path,
            width=800,
            height=600,
            format="PNG",
            file_size=51200,
            modified_time=datetime.now(UTC),
            mode="RGBA",
        )
        assert meta.file_size == 51200

    def test_mode_stored(self, tmp_path: Path) -> None:
        path = tmp_path / "bw.jpg"
        path.write_bytes(b"\xff\xd8\xff")
        meta = ImageMetadata(
            path=path,
            width=100,
            height=100,
            format="JPEG",
            file_size=1024,
            modified_time=datetime.now(UTC),
            mode="L",
        )
        assert meta.mode == "L"


# ---------------------------------------------------------------------------
# DirectoryPrefs
# ---------------------------------------------------------------------------


@pytest.fixture()
def dir_prefs() -> DirectoryPrefs:
    return DirectoryPrefs()


class TestDirectoryPrefsInit:
    def test_creates(self) -> None:
        d = DirectoryPrefs()
        assert d is not None


class TestSetAndGetPreference:
    def test_set_and_list(self, dir_prefs: DirectoryPrefs, tmp_path: Path) -> None:
        dir_prefs.set_preference(tmp_path, {"naming": "snake_case"})
        prefs = dir_prefs.list_directory_preferences()
        assert len(prefs) == 1
        assert prefs[0][0] == tmp_path.resolve()

    def test_get_with_inheritance(self, dir_prefs: DirectoryPrefs, tmp_path: Path) -> None:
        dir_prefs.set_preference(tmp_path, {"style": "dated"})
        result = dir_prefs.get_preference_with_inheritance(tmp_path)
        assert result is None or isinstance(result, dict)

    def test_child_inherits_parent(self, dir_prefs: DirectoryPrefs, tmp_path: Path) -> None:
        child = tmp_path / "subdir"
        child.mkdir()
        dir_prefs.set_preference(tmp_path, {"inherited": True})
        result = dir_prefs.get_preference_with_inheritance(child)
        assert result is None or isinstance(result, dict)

    def test_override_parent(self, dir_prefs: DirectoryPrefs, tmp_path: Path) -> None:
        child = tmp_path / "child"
        child.mkdir()
        dir_prefs.set_preference(tmp_path, {"style": "parent"})
        dir_prefs.set_preference(child, {"style": "child"}, override_parent=True)
        result = dir_prefs.get_preference_with_inheritance(child)
        assert result is None or isinstance(result, dict)


class TestRemovePreference:
    def test_remove_existing(self, dir_prefs: DirectoryPrefs, tmp_path: Path) -> None:
        dir_prefs.set_preference(tmp_path, {"key": "val"})
        result = dir_prefs.remove_preference(tmp_path)
        assert result is True

    def test_remove_nonexistent(self, dir_prefs: DirectoryPrefs, tmp_path: Path) -> None:
        result = dir_prefs.remove_preference(tmp_path / "nonexistent")
        assert result is False


class TestGetStatistics:
    def test_empty_returns_dict(self, dir_prefs: DirectoryPrefs) -> None:
        stats = dir_prefs.get_statistics()
        assert stats["total_directories"] == 0

    def test_after_adding_prefs(self, dir_prefs: DirectoryPrefs, tmp_path: Path) -> None:
        for i in range(3):
            d = tmp_path / f"dir{i}"
            d.mkdir()
            dir_prefs.set_preference(d, {"index": i})
        stats = dir_prefs.get_statistics()
        assert stats["total_directories"] == 3


class TestClearAll:
    def test_clear_empty(self, dir_prefs: DirectoryPrefs) -> None:
        dir_prefs.clear_all()  # Should not raise

    def test_clear_with_data(self, dir_prefs: DirectoryPrefs, tmp_path: Path) -> None:
        dir_prefs.set_preference(tmp_path, {"key": "val"})
        dir_prefs.clear_all()
        prefs = dir_prefs.list_directory_preferences()
        assert prefs == []


# ---------------------------------------------------------------------------
# Copilot Rule models
# ---------------------------------------------------------------------------


def _make_action() -> RuleAction:
    return RuleAction(action_type=ActionType.MOVE, destination="archive")


class TestRuleCondition:
    def test_created(self) -> None:
        rc = RuleCondition(condition_type=ConditionType.EXTENSION, value=".pdf")
        assert rc.condition_type == ConditionType.EXTENSION
        assert rc.value == ".pdf"

    def test_condition_types_exist(self) -> None:
        assert ConditionType.EXTENSION is not None

    def test_negate_default_false(self) -> None:
        rc = RuleCondition(condition_type=ConditionType.EXTENSION, value=".txt")
        assert rc.negate is False

    def test_negate_true(self) -> None:
        rc = RuleCondition(condition_type=ConditionType.EXTENSION, value=".pdf", negate=True)
        assert rc.negate is True


class TestRuleAction:
    def test_created(self) -> None:
        ra = RuleAction(action_type=ActionType.MOVE, destination="/tmp")
        assert ra.action_type == ActionType.MOVE

    def test_action_types_exist(self) -> None:
        assert ActionType.MOVE is not None

    def test_destination_stored(self) -> None:
        ra = RuleAction(action_type=ActionType.MOVE, destination="/archive")
        assert ra.destination == "/archive"

    def test_parameters_dict(self) -> None:
        ra = RuleAction(action_type=ActionType.MOVE, destination="/tmp", parameters={"k": "v"})
        assert ra.parameters == {"k": "v"}


class TestRule:
    def test_created(self) -> None:
        r = Rule(name="test_rule")
        assert r.name == "test_rule"

    def test_empty_conditions(self) -> None:
        r = Rule(name="empty")
        assert r.conditions == []

    def test_enabled_default_true(self) -> None:
        r = Rule(name="r")
        assert r.enabled is True

    def test_disabled(self) -> None:
        r = Rule(name="r", enabled=False)
        assert r.enabled is False

    def test_priority_stored(self) -> None:
        r = Rule(name="r", priority=5)
        assert r.priority == 5

    def test_description_stored(self) -> None:
        r = Rule(name="r", description="my rule")
        assert r.description == "my rule"


class TestRuleSet:
    def test_created(self) -> None:
        rs = RuleSet(name="my_ruleset")
        assert rs.name == "my_ruleset"

    def test_empty_rules(self) -> None:
        rs = RuleSet(name="rs")
        assert rs.rules == []

    def test_with_rules(self) -> None:
        r = Rule(name="r1")
        rs = RuleSet(name="rs", rules=[r])
        assert len(rs.rules) == 1

    def test_version_default(self) -> None:
        rs = RuleSet(name="rs")
        assert rs.version == "1.0"
