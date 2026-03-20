"""Integration tests for advanced intelligence services.

Covers:
  - services/intelligence/profile_exporter.py — ProfileExporter
  - services/intelligence/template_manager.py  — TemplateManager
  - services/intelligence/conflict_resolver.py  — ConflictResolver
  - services/intelligence/feedback_processor.py — FeedbackProcessor (basics)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from file_organizer.services.intelligence.conflict_resolver import ConflictResolver
from file_organizer.services.intelligence.feedback_processor import FeedbackProcessor
from file_organizer.services.intelligence.profile_exporter import ProfileExporter
from file_organizer.services.intelligence.profile_manager import ProfileManager
from file_organizer.services.intelligence.template_manager import TemplateManager

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager(tmp_path: Path) -> ProfileManager:
    return ProfileManager(storage_path=tmp_path / "profiles")


@pytest.fixture()
def exporter(manager: ProfileManager) -> ProfileExporter:
    return ProfileExporter(profile_manager=manager)


@pytest.fixture()
def template_mgr(manager: ProfileManager) -> TemplateManager:
    return TemplateManager(profile_manager=manager)


# ---------------------------------------------------------------------------
# ProfileExporter
# ---------------------------------------------------------------------------


class TestProfileExporterExport:
    def test_export_existing_profile(self, exporter: ProfileExporter, tmp_path: Path) -> None:
        out = tmp_path / "exports" / "default.json"
        result = exporter.export_profile("default", out)
        assert result is True
        assert out.exists()

    def test_export_creates_valid_json(self, exporter: ProfileExporter, tmp_path: Path) -> None:
        out = tmp_path / "out.json"
        exporter.export_profile("default", out)
        data = json.loads(out.read_text())
        assert "profile_name" in data
        assert "exported_at" in data
        assert "export_version" in data

    def test_export_nonexistent_profile_returns_false(
        self, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        result = exporter.export_profile("phantom", tmp_path / "phantom.json")
        assert result is False

    def test_export_atomic_write_no_temp_file_left(
        self, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        out = tmp_path / "profile.json"
        exporter.export_profile("default", out)
        temp = tmp_path / "profile.json.tmp"
        assert not temp.exists()


class TestProfileExporterValidate:
    def test_validate_missing_file_returns_false(
        self, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        result = exporter.validate_export(tmp_path / "missing.json")
        assert result is False

    def test_validate_valid_export_returns_true(
        self, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        out = tmp_path / "valid.json"
        exporter.export_profile("default", out)
        assert exporter.validate_export(out) is True

    def test_validate_corrupted_json_returns_false(
        self, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        assert exporter.validate_export(bad) is False

    def test_validate_missing_required_fields_returns_false(
        self, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        bad = tmp_path / "incomplete.json"
        bad.write_text(json.dumps({"profile_name": "x"}))
        assert exporter.validate_export(bad) is False


class TestProfileExporterSelective:
    def test_export_selective_global_prefs(self, exporter: ProfileExporter, tmp_path: Path) -> None:
        out = tmp_path / "selective.json"
        result = exporter.export_selective("default", out, ["global"])
        assert result is True
        data = json.loads(out.read_text())
        assert data["export_type"] == "selective"
        assert "global" in data.get("included_preferences", [])

    def test_export_selective_nonexistent_profile(
        self, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        result = exporter.export_selective("ghost", tmp_path / "out.json", ["global"])
        assert result is False

    def test_export_selective_multiple_types(
        self, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        out = tmp_path / "multi.json"
        result = exporter.export_selective("default", out, ["global", "naming", "folders"])
        assert result is True
        data = json.loads(out.read_text())
        assert len(data["included_preferences"]) == 3


class TestProfileExporterPreview:
    def test_preview_existing_profile(self, exporter: ProfileExporter) -> None:
        preview = exporter.preview_export("default")
        assert preview is not None
        assert preview["profile_name"] == "default"
        assert "statistics" in preview
        assert "export_size_estimate" in preview

    def test_preview_nonexistent_returns_none(self, exporter: ProfileExporter) -> None:
        assert exporter.preview_export("nonexistent") is None

    def test_preview_statistics_keys(self, exporter: ProfileExporter) -> None:
        preview = exporter.preview_export("default")
        assert preview is not None
        stats = preview["statistics"]
        assert "global_preferences_count" in stats
        assert "directory_specific_count" in stats
        assert "learned_patterns_count" in stats


class TestProfileExporterMultiple:
    def test_export_multiple_profiles(
        self, manager: ProfileManager, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        manager.create_profile("Work", "work profile")
        results = exporter.export_multiple(["default", "Work"], tmp_path / "exports")
        assert results["default"] is True
        assert results["Work"] is True

    def test_export_multiple_partial_failure(
        self, exporter: ProfileExporter, tmp_path: Path
    ) -> None:
        results = exporter.export_multiple(["default", "missing_xyz"], tmp_path / "exp")
        assert results["default"] is True
        assert results["missing_xyz"] is False


# ---------------------------------------------------------------------------
# TemplateManager
# ---------------------------------------------------------------------------


class TestTemplateManagerList:
    def test_list_templates_returns_5(self, template_mgr: TemplateManager) -> None:
        templates = template_mgr.list_templates()
        assert len(templates) == 5

    def test_list_templates_contains_expected(self, template_mgr: TemplateManager) -> None:
        templates = template_mgr.list_templates()
        for name in ("work", "personal", "photography", "development", "academic"):
            assert name in templates


class TestTemplateManagerGet:
    def test_get_existing_template(self, template_mgr: TemplateManager) -> None:
        t = template_mgr.get_template("work")
        assert t is not None
        assert "preferences" in t
        assert "learned_patterns" in t

    def test_get_case_insensitive(self, template_mgr: TemplateManager) -> None:
        assert template_mgr.get_template("WORK") is not None
        assert template_mgr.get_template("Work") is not None

    def test_get_nonexistent_returns_none(self, template_mgr: TemplateManager) -> None:
        assert template_mgr.get_template("unicorn") is None

    def test_get_returns_deep_copy(self, template_mgr: TemplateManager) -> None:
        t1 = template_mgr.get_template("work")
        t2 = template_mgr.get_template("work")
        assert t1 is not t2


class TestTemplateManagerPreview:
    def test_preview_existing_template(self, template_mgr: TemplateManager) -> None:
        preview = template_mgr.preview_template("development")
        assert preview is not None
        assert preview["template_name"] == "development"
        assert "preferences_summary" in preview
        assert "confidence_levels" in preview

    def test_preview_nonexistent_returns_none(self, template_mgr: TemplateManager) -> None:
        assert template_mgr.preview_template("phantom") is None

    def test_preview_summary_has_correct_keys(self, template_mgr: TemplateManager) -> None:
        preview = template_mgr.preview_template("academic")
        assert preview is not None
        summary = preview["preferences_summary"]
        assert "naming_patterns" in summary
        assert "folder_mappings" in summary
        assert "category_overrides" in summary


class TestTemplateManagerCreateProfile:
    def test_create_profile_from_template(self, template_mgr: TemplateManager) -> None:
        profile = template_mgr.create_profile_from_template("work", "MyWork")
        assert profile is not None
        assert profile.profile_name == "MyWork"

    def test_create_profile_copies_preferences(self, template_mgr: TemplateManager) -> None:
        profile = template_mgr.create_profile_from_template("photography", "MyPhotos")
        assert profile is not None
        assert profile.preferences is not None

    def test_create_profile_nonexistent_template_returns_none(
        self, template_mgr: TemplateManager
    ) -> None:
        assert template_mgr.create_profile_from_template("ghost", "Name") is None

    def test_create_profile_duplicate_name_returns_none(
        self, template_mgr: TemplateManager
    ) -> None:
        template_mgr.create_profile_from_template("work", "DupProfile")
        result = template_mgr.create_profile_from_template("personal", "DupProfile")
        assert result is None

    def test_create_profile_with_customizations(self, template_mgr: TemplateManager) -> None:
        customize = {"naming_patterns": {"separator": "-"}}
        profile = template_mgr.create_profile_from_template(
            "work", "CustomWork", customize=customize
        )
        assert profile is not None


class TestTemplateManagerCustomTemplate:
    def test_create_custom_template_from_profile(self, template_mgr: TemplateManager) -> None:
        result = template_mgr.create_custom_template("default", "my_custom")
        assert result is True
        assert template_mgr.get_template("my_custom") is not None

    def test_create_custom_template_duplicate_name_fails(
        self, template_mgr: TemplateManager
    ) -> None:
        template_mgr.create_custom_template("default", "custom_dup")
        result = template_mgr.create_custom_template("default", "custom_dup")
        assert result is False

    def test_create_custom_template_nonexistent_profile_fails(
        self, template_mgr: TemplateManager
    ) -> None:
        result = template_mgr.create_custom_template("ghost_profile", "new_tmpl")
        assert result is False


class TestTemplateManagerRecommendations:
    def test_dev_extensions_recommend_development(self, template_mgr: TemplateManager) -> None:
        recs = template_mgr.get_template_recommendations(file_types=[".py", ".ts"])
        assert "development" in recs

    def test_image_extensions_recommend_photography(self, template_mgr: TemplateManager) -> None:
        recs = template_mgr.get_template_recommendations(file_types=[".jpg", ".raw"])
        assert "photography" in recs

    def test_use_case_work_recommends_work(self, template_mgr: TemplateManager) -> None:
        recs = template_mgr.get_template_recommendations(use_case="corporate office work")
        assert "work" in recs

    def test_use_case_school_recommends_academic(self, template_mgr: TemplateManager) -> None:
        recs = template_mgr.get_template_recommendations(use_case="university research")
        assert "academic" in recs

    def test_no_duplicates_in_recommendations(self, template_mgr: TemplateManager) -> None:
        recs = template_mgr.get_template_recommendations(
            file_types=[".py"], use_case="software develop"
        )
        assert len(recs) == len(set(recs))

    def test_empty_inputs_returns_empty(self, template_mgr: TemplateManager) -> None:
        recs = template_mgr.get_template_recommendations()
        assert recs == []


class TestTemplateManagerCompare:
    def test_compare_two_templates(self, template_mgr: TemplateManager) -> None:
        result = template_mgr.compare_templates(["work", "personal"])
        assert result is not None
        assert len(result["templates"]) == 2

    def test_compare_single_template_returns_none(self, template_mgr: TemplateManager) -> None:
        assert template_mgr.compare_templates(["work"]) is None

    def test_compare_skips_nonexistent(self, template_mgr: TemplateManager) -> None:
        result = template_mgr.compare_templates(["work", "missing_xyz"])
        assert result is None  # only 1 valid template after filtering

    def test_compare_includes_style_info(self, template_mgr: TemplateManager) -> None:
        result = template_mgr.compare_templates(["development", "academic"])
        assert result is not None
        t = result["templates"][0]
        assert "naming_style" in t
        assert "folder_structure" in t


# ---------------------------------------------------------------------------
# ConflictResolver
# ---------------------------------------------------------------------------


def _pref(confidence: float, count: int, updated: str) -> dict:
    return {
        "confidence": confidence,
        "correction_count": count,
        "updated": updated,
        "folder_mappings": {"pdf": "Documents"},
    }


class TestConflictResolverInit:
    def test_default_weights_sum_to_one(self) -> None:
        r = ConflictResolver()
        total = r.recency_weight + r.frequency_weight + r.confidence_weight
        assert abs(total - 1.0) < 1e-9

    def test_custom_weights_normalized(self) -> None:
        r = ConflictResolver(recency_weight=1.0, frequency_weight=1.0, confidence_weight=0.0)
        total = r.recency_weight + r.frequency_weight + r.confidence_weight
        assert abs(total - 1.0) < 1e-9

    def test_all_zero_weights_raises(self) -> None:
        with pytest.raises(ValueError):
            ConflictResolver(recency_weight=0, frequency_weight=0, confidence_weight=0)


class TestConflictResolverResolve:
    def test_single_preference_returned_as_is(self) -> None:
        r = ConflictResolver()
        pref = _pref(0.9, 10, "2026-01-20T00:00:00Z")
        assert r.resolve([pref]) is pref

    def test_empty_list_raises(self) -> None:
        r = ConflictResolver()
        with pytest.raises(ValueError):
            r.resolve([])

    def test_higher_confidence_wins(self) -> None:
        r = ConflictResolver(recency_weight=0.0, frequency_weight=0.0, confidence_weight=1.0)
        low = _pref(0.1, 0, "2026-01-01T00:00:00Z")
        high = _pref(0.9, 0, "2026-01-01T00:00:00Z")
        result = r.resolve([low, high])
        assert result["confidence"] == 0.9

    def test_higher_frequency_wins(self) -> None:
        r = ConflictResolver(recency_weight=0.0, frequency_weight=1.0, confidence_weight=0.0)
        rare = _pref(0.5, 1, "2026-01-01T00:00:00Z")
        frequent = _pref(0.5, 100, "2026-01-01T00:00:00Z")
        result = r.resolve([rare, frequent])
        assert result["correction_count"] == 100

    def test_more_recent_wins(self) -> None:
        r = ConflictResolver(recency_weight=1.0, frequency_weight=0.0, confidence_weight=0.0)
        old = _pref(0.5, 0, "2020-01-01T00:00:00Z")
        new = _pref(0.5, 0, "2026-01-15T00:00:00Z")
        result = r.resolve([old, new])
        assert result["updated"] == "2026-01-15T00:00:00Z"


class TestConflictResolverWeighting:
    def test_recency_weights_ordered(self) -> None:
        r = ConflictResolver()
        prefs = [
            {"updated": "2020-01-01T00:00:00Z"},
            {"updated": "2026-01-15T00:00:00Z"},
        ]
        weights = r.weight_by_recency(prefs)
        assert weights[1] > weights[0]

    def test_frequency_weights_ordered(self) -> None:
        r = ConflictResolver()
        prefs = [{"correction_count": 1}, {"correction_count": 100}]
        weights = r.weight_by_frequency(prefs)
        assert weights[1] > weights[0]

    def test_frequency_weights_equal_when_all_zero(self) -> None:
        r = ConflictResolver()
        prefs = [{"correction_count": 0}, {"correction_count": 0}]
        weights = r.weight_by_frequency(prefs)
        assert abs(weights[0] - weights[1]) < 1e-9

    def test_score_confidence_default_returns_half(self) -> None:
        r = ConflictResolver()
        assert r.score_confidence({}) == 0.5

    def test_score_confidence_clamped(self) -> None:
        r = ConflictResolver()
        assert r.score_confidence({"confidence": 1.5}) == 1.0
        assert r.score_confidence({"confidence": -0.5}) == 0.0

    def test_empty_list_recency_returns_empty(self) -> None:
        r = ConflictResolver()
        assert r.weight_by_recency([]) == []

    def test_empty_list_frequency_returns_empty(self) -> None:
        r = ConflictResolver()
        assert r.weight_by_frequency([]) == []


class TestConflictResolverAmbiguity:
    def test_single_pref_ambiguity_zero(self) -> None:
        r = ConflictResolver()
        assert r.get_ambiguity_score([_pref(0.9, 10, "2026-01-01T00:00:00Z")]) == 0.0

    def test_empty_pref_ambiguity_zero(self) -> None:
        r = ConflictResolver()
        assert r.get_ambiguity_score([]) == 0.0

    def test_clear_winner_low_ambiguity(self) -> None:
        r = ConflictResolver()
        prefs = [
            _pref(0.9, 50, "2026-01-15T00:00:00Z"),
            _pref(0.1, 1, "2020-01-01T00:00:00Z"),
        ]
        score = r.get_ambiguity_score(prefs)
        assert score < 0.9

    def test_needs_user_input_high_ambiguity(self) -> None:
        r = ConflictResolver()
        # Identical preferences → maximum ambiguity
        same = _pref(0.5, 5, "2026-01-01T00:00:00Z")
        same2 = _pref(0.5, 5, "2026-01-01T00:00:00Z")
        assert r.needs_user_input([same, same2]) is True

    def test_needs_user_input_low_ambiguity(self) -> None:
        r = ConflictResolver()
        dominant = _pref(0.99, 999, "2026-01-20T00:00:00Z")
        weak = _pref(0.01, 0, "2000-01-01T00:00:00Z")
        assert r.needs_user_input([dominant, weak]) is False

    def test_parse_timestamp_invalid_returns_epoch(self) -> None:
        r = ConflictResolver()
        dt = r._parse_timestamp("not-a-date")
        assert dt.year == 1970

    def test_parse_timestamp_none_returns_epoch(self) -> None:
        r = ConflictResolver()
        dt = r._parse_timestamp(None)
        assert dt.year == 1970

    def test_parse_timestamp_z_suffix(self) -> None:
        r = ConflictResolver()
        dt = r._parse_timestamp("2026-01-15T00:00:00Z")
        assert dt.year == 2026
        assert dt.month == 1


# ---------------------------------------------------------------------------
# FeedbackProcessor
# ---------------------------------------------------------------------------


class TestFeedbackProcessorBasics:
    def test_init_correction_count_zero(self) -> None:
        fp = FeedbackProcessor()
        assert fp.correction_count == 0

    def test_process_correction_returns_dict(self, tmp_path: Path) -> None:
        fp = FeedbackProcessor()
        original = tmp_path / "report.pdf"
        corrected = tmp_path / "2026-01-15_report.pdf"
        result = fp.process_correction(original, corrected)
        assert "timestamp" in result

    def test_process_correction_increments_count(self, tmp_path: Path) -> None:
        fp = FeedbackProcessor()
        fp.process_correction(tmp_path / "a.txt", tmp_path / "b.txt")
        assert fp.correction_count == 1

    def test_process_correction_has_timestamp(self, tmp_path: Path) -> None:
        fp = FeedbackProcessor()
        result = fp.process_correction(tmp_path / "x.txt", tmp_path / "y.txt")
        assert "timestamp" in result

    def test_process_correction_with_context(self, tmp_path: Path) -> None:
        fp = FeedbackProcessor()
        ctx = {"operation": "rename", "user": "test"}
        result = fp.process_correction(tmp_path / "old.txt", tmp_path / "new.txt", context=ctx)
        assert "timestamp" in result


class TestFeedbackProcessorTrigger:
    def test_trigger_retraining_returns_dict(self) -> None:
        fp = FeedbackProcessor()
        result = fp.trigger_retraining()
        assert result["status"] == "queued"

    def test_update_learning_model_returns_bool(self) -> None:
        fp = FeedbackProcessor()
        result = fp.update_learning_model({"folder_patterns": {"pdf": "Documents"}})
        assert result is False

    def test_batch_processing_enabled_by_default(self) -> None:
        fp = FeedbackProcessor()
        assert fp.batch_processing_enabled is True
