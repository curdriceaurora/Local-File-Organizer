"""Integration tests for PARA suggestion engine and API config.

Covers:
  - methodologies/para/ai/suggestion_engine.py — PARASuggestionEngine, PARASuggestion,
      FeatureExtractor, HeuristicEngine, MetadataFeatures, TextFeatures, StructuralFeatures
  - api/config.py — ApiSettings, load_settings, hash_api_key
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.para.ai.suggestion_engine import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    FeatureExtractor,
    HeuristicEngine,
    MetadataFeatures,
    PARASuggestion,
    PARASuggestionEngine,
    StructuralFeatures,
    TextFeatures,
)
from file_organizer.methodologies.para.categories import PARACategory

pytestmark = [pytest.mark.ci, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConfidenceConstants:
    def test_high_above_medium(self) -> None:
        assert CONFIDENCE_HIGH > CONFIDENCE_MEDIUM

    def test_medium_above_low(self) -> None:
        assert CONFIDENCE_MEDIUM > CONFIDENCE_LOW

    def test_all_in_range(self) -> None:
        for val in (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW):
            assert 0.0 <= val <= 1.0


# ---------------------------------------------------------------------------
# PARASuggestion dataclass
# ---------------------------------------------------------------------------


class TestPARASuggestion:
    def _make_suggestion(self, **kwargs) -> PARASuggestion:
        defaults = {
            "category": PARACategory.RESOURCE,
            "confidence": 0.7,
            "reasoning": ["keyword match"],
            "alternative_categories": [(PARACategory.ARCHIVE, 0.3)],
            "tags": ["finance"],
            "metadata": {},
        }
        defaults.update(kwargs)
        return PARASuggestion(**defaults)

    def test_created(self) -> None:
        s = self._make_suggestion()
        assert s.category == PARACategory.RESOURCE
        assert s.confidence == 0.7

    def test_optional_subfolder_default_none(self) -> None:
        s = self._make_suggestion()
        assert s.suggested_subfolder is None

    def test_custom_subfolder(self) -> None:
        s = self._make_suggestion(suggested_subfolder="Finance/2024")
        assert s.suggested_subfolder == "Finance/2024"

    def test_reasoning_stored(self) -> None:
        s = self._make_suggestion(reasoning=["temporal signal", "keyword match"])
        assert "temporal signal" in s.reasoning

    def test_tags_stored(self) -> None:
        s = self._make_suggestion(tags=["finance", "quarterly"])
        assert "finance" in s.tags

    def test_alternative_categories_stored(self) -> None:
        alts = [(PARACategory.PROJECT, 0.5), (PARACategory.AREA, 0.2)]
        s = self._make_suggestion(alternative_categories=alts)
        assert len(s.alternative_categories) == 2

    def test_metadata_stored(self) -> None:
        s = self._make_suggestion(metadata={"source": "ai"})
        assert s.metadata["source"] == "ai"


# ---------------------------------------------------------------------------
# FeatureExtractor
# ---------------------------------------------------------------------------


@pytest.fixture()
def extractor() -> FeatureExtractor:
    return FeatureExtractor()


class TestFeatureExtractorInit:
    def test_default_init(self) -> None:
        fe = FeatureExtractor()
        assert fe is not None

    def test_custom_max_length(self) -> None:
        fe = FeatureExtractor(max_content_length=1000)
        assert fe is not None


class TestExtractMetadataFeatures:
    def test_returns_metadata_features(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("content")
        result = extractor.extract_metadata_features(f)
        assert isinstance(result, MetadataFeatures)

    def test_file_size_correct(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_bytes(b"x" * 100)
        result = extractor.extract_metadata_features(f)
        assert result.file_size == 100

    def test_file_type_correct(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        f = tmp_path / "report.pdf"
        f.write_bytes(b"pdf data")
        result = extractor.extract_metadata_features(f)
        assert result.file_type == ".pdf"

    def test_modification_date_set(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello")
        result = extractor.extract_metadata_features(f)
        assert result.modification_date is not None

    def test_days_since_modified_non_negative(
        self, extractor: FeatureExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello")
        result = extractor.extract_metadata_features(f)
        assert result.days_since_modified >= 0


class TestExtractStructuralFeatures:
    def test_returns_structural_features(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        result = extractor.extract_structural_features(f)
        assert isinstance(result, StructuralFeatures)

    def test_directory_depth_positive(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("x")
        result = extractor.extract_structural_features(f)
        assert result.directory_depth >= 0

    def test_path_keywords_is_list(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("x")
        result = extractor.extract_structural_features(f)
        assert result.path_keywords == []

    def test_has_project_structure_bool(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("x")
        result = extractor.extract_structural_features(f)
        assert result.has_project_structure is False

    def test_has_date_in_path_bool(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        subdir = tmp_path / "2024-03"
        subdir.mkdir()
        f = subdir / "notes.txt"
        f.write_text("x")
        result = extractor.extract_structural_features(f)
        assert result.has_date_in_path is False


class TestExtractTextFeatures:
    def test_returns_text_features(self, extractor: FeatureExtractor) -> None:
        result = extractor.extract_text_features("hello finance quarterly")
        assert isinstance(result, TextFeatures)

    def test_keywords_is_list(self, extractor: FeatureExtractor) -> None:
        result = extractor.extract_text_features("invoice payment finance")
        assert len(result.keywords) >= 1

    def test_word_count_correct(self, extractor: FeatureExtractor) -> None:
        result = extractor.extract_text_features("one two three four five")
        assert result.word_count == 5

    def test_empty_content(self, extractor: FeatureExtractor) -> None:
        result = extractor.extract_text_features("")
        assert isinstance(result, TextFeatures)
        assert result.word_count == 0

    def test_category_keyword_counts_is_dict(self, extractor: FeatureExtractor) -> None:
        result = extractor.extract_text_features("project deadline work")
        assert "project" in result.category_keyword_counts

    def test_temporal_indicators_list(self, extractor: FeatureExtractor) -> None:
        result = extractor.extract_text_features("deadline next week project")
        assert len(result.temporal_indicators) >= 1

    def test_action_items_list(self, extractor: FeatureExtractor) -> None:
        result = extractor.extract_text_features("todo: fix the bug, review the code")
        assert len(result.action_items) >= 1


# ---------------------------------------------------------------------------
# HeuristicEngine
# ---------------------------------------------------------------------------


class TestHeuristicEngineInit:
    def test_default_init(self) -> None:
        he = HeuristicEngine()
        assert he is not None

    def test_with_flags(self) -> None:
        he = HeuristicEngine(
            enable_temporal=True,
            enable_content=True,
            enable_structural=False,
            enable_ai=False,
        )
        assert he is not None


class TestHeuristicEngineEvaluate:
    def test_returns_heuristic_result(self, tmp_path: Path) -> None:
        from file_organizer.methodologies.para.detection.heuristics import HeuristicResult

        he = HeuristicEngine()
        f = tmp_path / "file.txt"
        f.write_text("project deadline work")
        result = he.evaluate(f)
        assert isinstance(result, HeuristicResult)

    def test_result_has_recommended_category_field(self, tmp_path: Path) -> None:
        he = HeuristicEngine()
        f = tmp_path / "file.txt"
        f.write_text("project deadline work")
        result = he.evaluate(f)
        # recommended_category may be None when needs_manual_review is True
        assert result.recommended_category is None or isinstance(
            result.recommended_category, PARACategory
        )

    def test_result_confidence_in_range(self, tmp_path: Path) -> None:
        he = HeuristicEngine()
        f = tmp_path / "file.txt"
        f.write_text("some text content")
        result = he.evaluate(f)
        assert 0.0 <= result.overall_confidence <= 1.0

    def test_with_metadata(self, tmp_path: Path) -> None:
        from file_organizer.methodologies.para.detection.heuristics import HeuristicResult

        he = HeuristicEngine()
        f = tmp_path / "archive.txt"
        f.write_text("old notes from 2018")
        result = he.evaluate(f, metadata={"age_days": 2000})
        assert isinstance(result, HeuristicResult)


# ---------------------------------------------------------------------------
# PARASuggestionEngine
# ---------------------------------------------------------------------------


@pytest.fixture()
def para_engine() -> PARASuggestionEngine:
    return PARASuggestionEngine()


class TestPARASuggestionEngineInit:
    def test_default_init(self) -> None:
        e = PARASuggestionEngine()
        assert e is not None

    def test_with_custom_components(self) -> None:
        fe = FeatureExtractor()
        he = HeuristicEngine()
        e = PARASuggestionEngine(feature_extractor=fe, heuristic_engine=he)
        assert e is not None


class TestPARASuggestionEngineSuggest:
    def test_returns_para_suggestion(
        self, para_engine: PARASuggestionEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "report.pdf"
        f.write_bytes(b"financial quarterly report")
        result = para_engine.suggest(f)
        assert isinstance(result, PARASuggestion)

    def test_category_is_para_category(
        self, para_engine: PARASuggestionEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("notes content")
        result = para_engine.suggest(f)
        assert isinstance(result.category, PARACategory)

    def test_confidence_in_range(self, para_engine: PARASuggestionEngine, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("content")
        result = para_engine.suggest(f)
        assert 0.0 <= result.confidence <= 1.0

    def test_reasoning_is_list(self, para_engine: PARASuggestionEngine, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("some text")
        result = para_engine.suggest(f)
        assert len(result.reasoning) >= 1

    def test_tags_is_list(self, para_engine: PARASuggestionEngine, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("some text")
        result = para_engine.suggest(f)
        assert len(result.tags) >= 1

    def test_with_content_hint(self, para_engine: PARASuggestionEngine, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("meeting notes")
        result = para_engine.suggest(f, content="project deadline client meeting")
        assert isinstance(result, PARASuggestion)

    def test_alternative_categories_list(
        self, para_engine: PARASuggestionEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "quarterly_budget_review.xlsx"
        f.write_bytes(b"data")
        result = para_engine.suggest(f, content="quarterly financial budget planning spreadsheet")
        assert isinstance(result.alternative_categories, list)
        assert all(
            isinstance(cat, tuple) and len(cat) == 2 for cat in result.alternative_categories
        )


class TestPARASuggestionEngineSuggestBatch:
    def test_empty_list_returns_empty(self, para_engine: PARASuggestionEngine) -> None:
        result = para_engine.suggest_batch([])
        assert result == []

    def test_single_file_returns_one(
        self, para_engine: PARASuggestionEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = para_engine.suggest_batch([f])
        assert len(result) == 1

    def test_multiple_files(self, para_engine: PARASuggestionEngine, tmp_path: Path) -> None:
        files = []
        for i in range(3):
            f = tmp_path / f"doc{i}.txt"
            f.write_text(f"content {i}")
            files.append(f)
        result = para_engine.suggest_batch(files)
        assert len(result) == 3

    def test_each_result_is_para_suggestion(
        self, para_engine: PARASuggestionEngine, tmp_path: Path
    ) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.pdf"
        f1.write_text("text")
        f2.write_bytes(b"pdf data")
        results = para_engine.suggest_batch([f1, f2])
        for r in results:
            assert isinstance(r, PARASuggestion)


class TestPARASuggestionEngineExplain:
    def test_returns_string(self, para_engine: PARASuggestionEngine, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("text")
        suggestion = para_engine.suggest(f)
        explanation = para_engine.explain(suggestion)
        assert len(explanation) > 0

    def test_non_empty_explanation(self, para_engine: PARASuggestionEngine, tmp_path: Path) -> None:
        f = tmp_path / "report.pdf"
        f.write_bytes(b"report data")
        suggestion = para_engine.suggest(f)
        explanation = para_engine.explain(suggestion)
        assert len(explanation) > 0


# ---------------------------------------------------------------------------
# ApiSettings and api/config utilities
# ---------------------------------------------------------------------------


class TestApiSettings:
    def test_default_init(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert s is not None

    def test_app_name_default(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert isinstance(s.app_name, str)
        assert len(s.app_name) > 0

    def test_version_default(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert len(s.version) > 0

    def test_port_default(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert s.port == 8000

    def test_host_default(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert s.host == "0.0.0.0"

    def test_environment_default(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert s.environment == "development"

    def test_auth_enabled_is_bool(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert s.auth_enabled is True

    def test_api_key_enabled_is_bool(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert s.api_key_enabled is True

    def test_cors_origins_is_list(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert len(s.cors_origins) >= 1

    def test_rate_limit_enabled_is_bool(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert s.rate_limit_enabled is True

    def test_security_headers_enabled_is_bool(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert s.security_headers_enabled is True

    def test_ollama_url_default(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        assert "localhost" in s.ollama_url or "11434" in s.ollama_url

    def test_custom_port(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings(port=9000)
        assert s.port == 9000

    def test_model_dump_returns_dict(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings()
        d = s.model_dump()
        assert isinstance(d, dict)
        assert "app_name" in d

    def test_ollama_url_normalized(self) -> None:
        from file_organizer.api.config import ApiSettings

        s = ApiSettings(ollama_url="localhost:11434")
        assert s.ollama_url.startswith("http://")


class TestHashApiKey:
    def test_returns_string(self) -> None:
        from file_organizer.api.config import hash_api_key

        result = hash_api_key("test-key-123")
        assert len(result) > 0

    def test_non_empty_result(self) -> None:
        from file_organizer.api.config import hash_api_key

        result = hash_api_key("my-secret-key")
        assert len(result) > 0

    def test_different_keys_different_hashes(self) -> None:
        from file_organizer.api.config import hash_api_key

        h1 = hash_api_key("key-one")
        h2 = hash_api_key("key-two")
        assert h1 != h2

    def test_not_plaintext(self) -> None:
        from file_organizer.api.config import hash_api_key

        key = "my-secret-api-key"
        result = hash_api_key(key)
        assert key not in result


class TestLoadSettings:
    def test_returns_api_settings(self) -> None:
        from file_organizer.api.config import ApiSettings, load_settings

        result = load_settings()
        assert isinstance(result, ApiSettings)

    def test_loaded_settings_have_defaults(self) -> None:
        from file_organizer.api.config import load_settings

        result = load_settings()
        assert result.port > 0
        assert len(result.app_name) > 0
