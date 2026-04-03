"""Tests for Johnny Decimal adapters uncovered branches.

Targets: PARAAdapter.adapt_to_jd invalid category, FileSystemAdapter depth
branches, AdapterRegistry.adapt_from_jd, create_default_registry.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.methodologies.johnny_decimal.adapters import (
    AdapterRegistry,
    FileSystemAdapter,
    OrganizationItem,
    PARAAdapter,
    create_default_registry,
)
from file_organizer.methodologies.johnny_decimal.categories import (
    JohnnyDecimalNumber,
    NumberLevel,
)
from file_organizer.methodologies.johnny_decimal.config import (
    JohnnyDecimalConfig,
    create_para_compatible_config,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def jd_config() -> MagicMock:
    """Create a mock JD config."""
    config = MagicMock()
    config.compatibility.para_integration.enabled = True
    config.custom_mappings = {}
    return config


class TestPARAAdapter:
    """Cover PARAAdapter branches — lines 136, 128."""

    def test_adapt_to_jd_invalid_category_raises(self, jd_config: MagicMock) -> None:
        """Unknown PARA category raises ValueError (line 128)."""
        adapter = PARAAdapter(jd_config)
        item = OrganizationItem(name="test", path=Path("/x"), category="unknown_cat", metadata={})
        with pytest.raises(ValueError, match="Cannot determine PARA category"):
            adapter.adapt_to_jd(item)

    def test_adapt_to_jd_subcategory_non_int(self, jd_config: MagicMock) -> None:
        """Non-int subcategory defaults to 1 (line 136)."""
        adapter = PARAAdapter(jd_config)
        adapter.bridge.para_to_jd_area = MagicMock(return_value=10)
        item = OrganizationItem(
            name="test", path=Path("/x"), category="projects", metadata={"subcategory": "not_int"}
        )
        result = adapter.adapt_to_jd(item)
        assert result.category == 1

    def test_adapt_from_jd_not_in_para_range(self, jd_config: MagicMock) -> None:
        """JD area not in PARA range raises ValueError (line 160)."""
        adapter = PARAAdapter(jd_config)
        adapter.bridge.jd_area_to_para = MagicMock(return_value=None)
        jd_num = JohnnyDecimalNumber(area=50, category=1)
        with pytest.raises(ValueError, match="not in PARA range"):
            adapter.adapt_from_jd(jd_num, "test")

    def test_can_adapt_false(self, jd_config: MagicMock) -> None:
        """Non-PARA item returns False."""
        adapter = PARAAdapter(jd_config)
        item = OrganizationItem(name="x", path=Path("/x"), category="random", metadata={})
        assert adapter.can_adapt(item) is False


class TestFileSystemAdapter:
    """Cover FileSystemAdapter branches — lines 209-231, 267, 272-280, 285-295, 299."""

    def test_adapt_to_jd_custom_mapping(self, jd_config: MagicMock) -> None:
        """Custom mapping takes precedence (line 210-212)."""
        jd_config.custom_mappings = {"test": 42}
        adapter = FileSystemAdapter(jd_config)
        item = OrganizationItem(name="test", path=Path("test"), category="fs", metadata={})
        result = adapter.adapt_to_jd(item)
        assert result.area == 42

    def test_adapt_to_jd_depth_1(self, jd_config: MagicMock) -> None:
        """Depth 1 => area level (line 217-220)."""
        adapter = FileSystemAdapter(jd_config)
        item = OrganizationItem(name="Finance", path=Path("Finance"), category="fs", metadata={})
        result = adapter.adapt_to_jd(item)
        assert result.level == NumberLevel.AREA

    def test_adapt_to_jd_depth_2(self, jd_config: MagicMock) -> None:
        """Depth 2 => category level (line 221-225)."""
        adapter = FileSystemAdapter(jd_config)
        item = OrganizationItem(
            name="Budgets", path=Path("Finance/Budgets"), category="fs", metadata={}
        )
        result = adapter.adapt_to_jd(item)
        assert result.level == NumberLevel.CATEGORY

    def test_adapt_to_jd_depth_3(self, jd_config: MagicMock) -> None:
        """Depth 3+ => ID level (line 226-231)."""
        adapter = FileSystemAdapter(jd_config)
        item = OrganizationItem(
            name="Q1", path=Path("Finance/Budgets/Q1"), category="fs", metadata={}
        )
        result = adapter.adapt_to_jd(item)
        assert result.level == NumberLevel.ID

    def test_adapt_from_jd_area_level(self, jd_config: MagicMock) -> None:
        """Area level generates simple path (line 244-245)."""
        adapter = FileSystemAdapter(jd_config)
        jd_num = JohnnyDecimalNumber(area=10)
        result = adapter.adapt_from_jd(jd_num, "Finance")
        assert "10 Finance" in str(result.path)

    def test_adapt_from_jd_category_level(self, jd_config: MagicMock) -> None:
        """Category level generates two-part path (line 246-249)."""
        adapter = FileSystemAdapter(jd_config)
        jd_num = JohnnyDecimalNumber(area=10, category=1)
        result = adapter.adapt_from_jd(jd_num, "Budgets")
        assert "10.01" in str(result.path)

    def test_adapt_from_jd_id_level(self, jd_config: MagicMock) -> None:
        """ID level generates three-part path (line 250-256)."""
        adapter = FileSystemAdapter(jd_config)
        jd_num = JohnnyDecimalNumber(area=10, category=1, item_id=1)
        result = adapter.adapt_from_jd(jd_num, "Q1 Budget")
        assert "10.01.001" in str(result.path)

    def test_can_adapt_always_true(self, jd_config: MagicMock) -> None:
        adapter = FileSystemAdapter(jd_config)
        item = OrganizationItem(name="any", path=Path("/any"), category="any", metadata={})
        assert adapter.can_adapt(item) is True

    def test_suggest_area_from_name_with_number(self, jd_config: MagicMock) -> None:
        """Name with leading number in 10-99 range uses it (line 272-276)."""
        adapter = FileSystemAdapter(jd_config)
        result = adapter._suggest_area_from_name("42 Finance")
        assert result == 42

    def test_suggest_area_from_name_hash_fallback(self, jd_config: MagicMock) -> None:
        """Name without number uses hash (line 279-280)."""
        adapter = FileSystemAdapter(jd_config)
        result = adapter._suggest_area_from_name("Finance")
        assert 10 <= result <= 99

    def test_suggest_category_from_name_with_dots(self, jd_config: MagicMock) -> None:
        """Name with XX.XX format extracts category (line 285-291)."""
        adapter = FileSystemAdapter(jd_config)
        result = adapter._suggest_category_from_name("10.05 Budgets")
        assert result == 5

    def test_suggest_category_hash_fallback(self, jd_config: MagicMock) -> None:
        """Name without dot format uses hash (line 294-295)."""
        adapter = FileSystemAdapter(jd_config)
        result = adapter._suggest_category_from_name("Budgets")
        assert 1 <= result <= 99

    def test_suggest_id_from_index(self, jd_config: MagicMock) -> None:
        """Index is clamped to valid range (line 299)."""
        adapter = FileSystemAdapter(jd_config)
        assert adapter._suggest_id_from_index(0) == 1
        assert adapter._suggest_id_from_index(998) == 999


class TestAdapterRegistry:
    """Cover AdapterRegistry branches — lines 333, 347, 366-369."""

    def test_get_adapter_returns_none_when_empty(self) -> None:
        registry = AdapterRegistry()
        item = OrganizationItem(name="x", path=Path("/x"), category="x", metadata={})
        assert registry.get_adapter(item) is None

    def test_adapt_to_jd_no_adapter(self) -> None:
        """adapt_to_jd returns None when no adapter matches (line 347)."""
        registry = AdapterRegistry()
        item = OrganizationItem(name="x", path=Path("/x"), category="x", metadata={})
        assert registry.adapt_to_jd(item) is None

    def test_adapt_from_jd_para(self, jd_config: MagicMock) -> None:
        """adapt_from_jd with 'para' methodology finds PARAAdapter (line 364-365)."""
        registry = AdapterRegistry()
        adapter = PARAAdapter(jd_config)
        adapter.adapt_from_jd = MagicMock(
            return_value=OrganizationItem(
                name="x", path=Path("/x"), category="project", metadata={}
            )
        )
        registry.register(adapter)
        jd_num = JohnnyDecimalNumber(area=10, category=1)
        result = registry.adapt_from_jd(jd_num, "test", methodology="para")
        assert result is not None

    def test_adapt_from_jd_filesystem(self, jd_config: MagicMock) -> None:
        """adapt_from_jd with 'filesystem' finds FileSystemAdapter (line 366-367)."""
        registry = AdapterRegistry()
        registry.register(FileSystemAdapter(jd_config))
        jd_num = JohnnyDecimalNumber(area=10)
        result = registry.adapt_from_jd(jd_num, "test", methodology="filesystem")
        assert result is not None

    def test_adapt_from_jd_unknown_methodology(self) -> None:
        """Unknown methodology returns None (line 369)."""
        registry = AdapterRegistry()
        jd_num = JohnnyDecimalNumber(area=10)
        result = registry.adapt_from_jd(jd_num, "test", methodology="unknown")
        assert result is None


class TestCreateDefaultRegistry:
    """Cover create_default_registry — lines 384-392."""

    def test_creates_with_para_enabled(self, jd_config: MagicMock) -> None:
        jd_config.compatibility.para_integration.enabled = True
        registry = create_default_registry(jd_config)
        assert len(registry._adapters) == 2  # PARA + FS

    def test_creates_without_para(self, jd_config: MagicMock) -> None:
        jd_config.compatibility.para_integration.enabled = False
        registry = create_default_registry(jd_config)
        assert len(registry._adapters) == 1  # FS only


class TestAdaptersCoverage:
    """Cover all missing branches in adapters.py."""

    @pytest.fixture
    def config(self) -> JohnnyDecimalConfig:
        return create_para_compatible_config()

    # Branch 275->279: _suggest_area_from_name digit outside 10-99
    def test_suggest_area_digit_out_of_range(self, config: JohnnyDecimalConfig) -> None:
        adapter = FileSystemAdapter(config)
        area = adapter._suggest_area_from_name("5 LowNum")
        assert 10 <= area <= 99  # falls through to hash-based

    # Branch 288->294: _suggest_category_from_name with non-digit second part
    def test_suggest_category_non_digit_after_dot(self, config: JohnnyDecimalConfig) -> None:
        adapter = FileSystemAdapter(config)
        cat = adapter._suggest_category_from_name("10.abc NotDigit")
        assert 1 <= cat <= 99  # falls through to hash-based

    # Branch 290->294: _suggest_category_from_name digit out of range
    def test_suggest_category_digit_out_of_range(self, config: JohnnyDecimalConfig) -> None:
        adapter = FileSystemAdapter(config)
        cat = adapter._suggest_category_from_name("10.0 Zero")
        assert 1 <= cat <= 99  # 0 is outside 1-99, falls through to hash

    # Branch 331->330: get_adapter where adapter.can_adapt returns False
    def test_get_adapter_can_adapt_false(self, config: JohnnyDecimalConfig) -> None:
        registry = AdapterRegistry()
        registry.register(PARAAdapter(config))
        # Item with non-PARA category => PARAAdapter.can_adapt returns False
        item = OrganizationItem(
            name="test",
            path=Path("test"),
            category="unknown",
            metadata={},
        )
        assert registry.get_adapter(item) is None

    # Branch 366->363: adapt_from_jd with unknown methodology
    def test_adapt_from_jd_unknown_methodology(self, config: JohnnyDecimalConfig) -> None:
        registry = AdapterRegistry()
        registry.register(PARAAdapter(config))
        num = JohnnyDecimalNumber(area=10, category=1)
        result = registry.adapt_from_jd(num, "test", methodology="unknown")
        assert result is None
