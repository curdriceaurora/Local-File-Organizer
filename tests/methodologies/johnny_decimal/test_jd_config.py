"""Tests for Johnny Decimal config uncovered branches.

Targets: from_dict missing descriptions, load_from_file missing path,
ConfigBuilder edge cases, and save/load roundtrips.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.johnny_decimal.config import (
    ConfigBuilder,
    JohnnyDecimalConfig,
    create_default_config,
    create_para_compatible_config,
)

pytestmark = pytest.mark.unit


class TestConfigCoverage:
    """Cover all missing lines in config.py."""

    # Line 146: from_dict with missing category description
    def test_from_dict_missing_descriptions(self) -> None:
        data = {
            "scheme": {
                "name": "test",
                "areas": [
                    {
                        "area_range_start": 10,
                        "area_range_end": 19,
                        "name": "Finance",
                    }
                ],
                "categories": [{"area": 10, "category": 1, "name": "Budget"}],
            }
        }
        config = JohnnyDecimalConfig.from_dict(data)
        assert config.scheme.name == "test"

    # Line 214: load_from_file with non-existent file
    def test_load_from_file_not_found(self, tmp_path: Path) -> None:
        missing_config = tmp_path / "missing_config.json"
        with pytest.raises(FileNotFoundError, match="not found"):
            JohnnyDecimalConfig.load_from_file(missing_config)

    # Lines 278-286: ConfigBuilder.add_category
    def test_config_builder_add_category(self) -> None:
        config = (
            ConfigBuilder("test")
            .add_area(10, "Finance")
            .add_category(10, 1, "Budget", "Budget tracking")
            .build()
        )
        cats = config.scheme.get_available_categories(10)
        assert len(cats) >= 1

    # Lines 350-351: add_custom_mapping
    def test_config_builder_custom_mapping(self) -> None:
        config = (
            ConfigBuilder("test")
            .add_area(10, "Finance")
            .add_custom_mapping("Documents", 10)
            .build()
        )
        assert config.custom_mappings["documents"] == 10

    # Line 371: build with no areas/categories
    def test_config_builder_empty(self) -> None:
        config = ConfigBuilder("empty").build()
        assert config.scheme.name == "empty"

    # Lines 387-389: create_para_compatible_config exercises full builder
    def test_create_para_compatible(self) -> None:
        config = create_para_compatible_config()
        assert config.compatibility.para_integration.enabled is True
        assert config.scheme.name == "para-compatible"

    # save_to_file / load_from_file roundtrip
    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        config = create_default_config()
        path = tmp_path / "config.json"
        config.save_to_file(path)
        loaded = JohnnyDecimalConfig.load_from_file(path)
        assert loaded.scheme.name == config.scheme.name
