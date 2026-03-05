"""Tests for PARA config module — targeting uncovered branches.

Covers: load_from_yaml, save_to_yaml, get_category_threshold,
get_category_keywords, get_category_directory, load_config.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import (
    CategoryThresholds,
    HeuristicWeights,
    KeywordPatterns,
    PARAConfig,
    TemporalThresholds,
    load_config,
)

pytestmark = pytest.mark.unit


class TestPARAConfigLoadFromYaml:
    """Tests for PARAConfig.load_from_yaml covering lines 144-194."""

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Config file not found returns defaults."""
        cfg = PARAConfig.load_from_yaml(tmp_path / "nonexistent.yaml")
        assert cfg.auto_categorize is True
        assert cfg.enable_ai_heuristic is False

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Empty YAML file returns defaults."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        cfg = PARAConfig.load_from_yaml(config_file)
        assert cfg.auto_categorize is True

    def test_load_valid_full_config(self, tmp_path: Path) -> None:
        """Full YAML with all sections is parsed correctly."""
        data = {
            "heuristic_weights": {"temporal": 0.1, "content": 0.2, "structural": 0.3, "ai": 0.4},
            "category_thresholds": {"project": 0.6, "area": 0.7, "resource": 0.8, "archive": 0.9},
            "keyword_patterns": {
                "project": ["proj"],
                "area": ["area"],
                "resource": ["ref"],
                "archive": ["old"],
            },
            "temporal_thresholds": {
                "project_max_age": 15,
                "area_min_age": 20,
                "area_max_age": 100,
                "resource_min_age": 40,
                "archive_min_age": 120,
                "archive_min_inactive": 60,
            },
            "enable_temporal_heuristic": False,
            "enable_content_heuristic": False,
            "enable_structural_heuristic": False,
            "enable_ai_heuristic": True,
            "manual_review_threshold": 0.5,
            "auto_categorize": False,
            "preserve_user_overrides": False,
            "default_root": "/tmp/para_root",
            "project_dir": "Proj",
            "area_dir": "Ar",
            "resource_dir": "Res",
            "archive_dir": "Arch",
        }
        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        cfg = PARAConfig.load_from_yaml(config_file)
        assert cfg.heuristic_weights.temporal == 0.1
        assert cfg.category_thresholds.archive == 0.9
        assert cfg.keyword_patterns.project == ["proj"]
        assert cfg.temporal_thresholds.project_max_age == 15
        assert cfg.enable_ai_heuristic is True
        assert cfg.auto_categorize is False
        assert cfg.default_root == Path("/tmp/para_root")
        assert cfg.project_dir == "Proj"

    def test_load_invalid_yaml_returns_defaults(self, tmp_path: Path) -> None:
        """Invalid YAML content falls back to defaults."""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text(": invalid: yaml: [")
        cfg = PARAConfig.load_from_yaml(config_file)
        # Should return defaults on exception
        assert cfg.auto_categorize is True

    def test_load_partial_config(self, tmp_path: Path) -> None:
        """Partial config uses defaults for missing fields."""
        data = {"enable_ai_heuristic": True, "project_dir": "MyProjects"}
        config_file = tmp_path / "partial.yaml"
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        cfg = PARAConfig.load_from_yaml(config_file)
        assert cfg.enable_ai_heuristic is True
        assert cfg.project_dir == "MyProjects"
        # Defaults preserved
        assert cfg.auto_categorize is True


class TestPARAConfigSaveToYaml:
    """Tests for PARAConfig.save_to_yaml covering lines 202-251."""

    def test_save_and_reload(self, tmp_path: Path) -> None:
        """Round-trip save then load preserves values."""
        cfg = PARAConfig(
            heuristic_weights=HeuristicWeights(temporal=0.5, content=0.2, structural=0.2, ai=0.1),
            category_thresholds=CategoryThresholds(
                project=0.6, area=0.7, resource=0.8, archive=0.9
            ),
            keyword_patterns=KeywordPatterns(
                project=["p1"], area=["a1"], resource=["r1"], archive=["ar1"]
            ),
            temporal_thresholds=TemporalThresholds(project_max_age=10),
            enable_ai_heuristic=True,
            auto_categorize=False,
            default_root=Path("/some/path"),
            project_dir="P",
            area_dir="A",
            resource_dir="R",
            archive_dir="Ar",
        )
        out_file = tmp_path / "out.yaml"
        cfg.save_to_yaml(out_file)

        assert out_file.exists()
        reloaded = PARAConfig.load_from_yaml(out_file)
        assert reloaded.enable_ai_heuristic is True
        assert reloaded.auto_categorize is False
        assert reloaded.default_root == Path("/some/path")

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        """save_to_yaml creates parent directories."""
        nested = tmp_path / "a" / "b" / "c" / "config.yaml"
        PARAConfig().save_to_yaml(nested)
        assert nested.exists()

    def test_save_with_no_default_root(self, tmp_path: Path) -> None:
        """save_to_yaml handles None default_root."""
        cfg = PARAConfig(default_root=None)
        out_file = tmp_path / "noroot.yaml"
        cfg.save_to_yaml(out_file)

        with open(out_file) as f:
            data = yaml.safe_load(f)
        assert data["default_root"] is None

    def test_save_error_handling(self, tmp_path: Path) -> None:
        """save_to_yaml logs error on write failure."""
        cfg = PARAConfig()
        # Use a path that cannot be written (directory as file)
        bad_path = tmp_path / "dir_target"
        bad_path.mkdir()
        # Writing to a directory should fail gracefully
        cfg.save_to_yaml(bad_path)
        # No exception raised; error logged


class TestPARAConfigCategoryHelpers:
    """Tests for get_category_threshold/keywords/directory covering lines 255-271, 290-292."""

    def test_get_category_threshold_all(self) -> None:
        cfg = PARAConfig(
            category_thresholds=CategoryThresholds(project=0.6, area=0.7, resource=0.8, archive=0.9)
        )
        assert cfg.get_category_threshold(PARACategory.PROJECT) == 0.6
        assert cfg.get_category_threshold(PARACategory.AREA) == 0.7
        assert cfg.get_category_threshold(PARACategory.RESOURCE) == 0.8
        assert cfg.get_category_threshold(PARACategory.ARCHIVE) == 0.9

    def test_get_category_keywords_all(self) -> None:
        cfg = PARAConfig()
        for cat in PARACategory:
            kw = cfg.get_category_keywords(cat)
            assert isinstance(kw, list)
            assert len(kw) > 0

    def test_get_category_directory_all(self) -> None:
        cfg = PARAConfig(project_dir="P", area_dir="A", resource_dir="R", archive_dir="Ar")
        assert cfg.get_category_directory(PARACategory.PROJECT) == "P"
        assert cfg.get_category_directory(PARACategory.AREA) == "A"
        assert cfg.get_category_directory(PARACategory.RESOURCE) == "R"
        assert cfg.get_category_directory(PARACategory.ARCHIVE) == "Ar"


class TestLoadConfig:
    """Tests for module-level load_config covering lines 304-321."""

    def test_load_config_with_explicit_path(self, tmp_path: Path) -> None:
        data = {"enable_ai_heuristic": True}
        config_file = tmp_path / "para_config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        cfg = load_config(config_file)
        assert cfg.enable_ai_heuristic is True

    def test_load_config_with_nonexistent_path(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "nope.yaml")
        # Should return defaults
        assert cfg.auto_categorize is True

    def test_load_config_none_uses_defaults(self) -> None:
        """When config_path is None and no default files exist, returns defaults."""
        with patch(
            "file_organizer.methodologies.para.config._get_para_config_dir",
            return_value=Path("/nonexistent/dir"),
        ):
            cfg = load_config(None)
            assert cfg.auto_categorize is True

    def test_load_config_finds_default_file(self, tmp_path: Path) -> None:
        """When config_path is None, searches standard locations."""
        data = {"project_dir": "Found"}
        config_file = tmp_path / "para_config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        with patch(
            "file_organizer.methodologies.para.config._get_para_config_dir",
            return_value=tmp_path,
        ):
            cfg = load_config(None)
            assert cfg.project_dir == "Found"
