"""
Tests for Johnny Decimal PARA Compatibility

Tests PARA integration, compatibility analyzer, and hybrid organizer.
"""

import pytest
from pathlib import Path

from file_organizer.methodologies.johnny_decimal import (
    PARACategory,
    PARAMapping,
    PARAJohnnyDecimalBridge,
    CompatibilityAnalyzer,
    HybridOrganizer,
    PARAAdapter,
    OrganizationItem,
    create_para_compatible_config,
    JohnnyDecimalNumber,
    NumberLevel,
)


@pytest.fixture
def para_config():
    """Create PARA-compatible configuration."""
    return create_para_compatible_config()


@pytest.fixture
def para_bridge(para_config):
    """Create PARA-JD bridge."""
    return PARAJohnnyDecimalBridge(para_config.compatibility.para_integration)


@pytest.fixture
def analyzer(para_config):
    """Create compatibility analyzer."""
    return CompatibilityAnalyzer(para_config)


@pytest.fixture
def hybrid_organizer(para_config):
    """Create hybrid organizer."""
    return HybridOrganizer(para_config)


@pytest.fixture
def para_adapter(para_config):
    """Create PARA adapter."""
    return PARAAdapter(para_config)


@pytest.fixture
def para_structure(tmp_path):
    """Create sample PARA structure."""
    # Create PARA folders
    (tmp_path / "Projects").mkdir()
    (tmp_path / "Projects/Website").mkdir()
    (tmp_path / "Areas").mkdir()
    (tmp_path / "Areas/Health").mkdir()
    (tmp_path / "Resources").mkdir()
    (tmp_path / "Resources/References").mkdir()
    (tmp_path / "Archive").mkdir()
    (tmp_path / "Archive/2023").mkdir()

    return tmp_path


class TestPARAJohnnyDecimalBridge:
    """Tests for PARAJohnnyDecimalBridge."""

    def test_para_to_jd_area(self, para_bridge):
        """Test PARA category to JD area conversion."""
        # Projects → Area 10
        area = para_bridge.para_to_jd_area(PARACategory.PROJECTS, index=0)
        assert area == 10

        # Areas → Area 20
        area = para_bridge.para_to_jd_area(PARACategory.AREAS, index=0)
        assert area == 20

        # Resources → Area 30
        area = para_bridge.para_to_jd_area(PARACategory.RESOURCES, index=0)
        assert area == 30

        # Archive → Area 40
        area = para_bridge.para_to_jd_area(PARACategory.ARCHIVE, index=0)
        assert area == 40

    def test_para_to_jd_area_with_index(self, para_bridge):
        """Test PARA to JD with different indices."""
        # Projects with index 2 → Area 12
        area = para_bridge.para_to_jd_area(PARACategory.PROJECTS, index=2)
        assert area == 12

        # Areas with index 5 → Area 25
        area = para_bridge.para_to_jd_area(PARACategory.AREAS, index=5)
        assert area == 25

    def test_para_to_jd_area_invalid_index(self, para_bridge):
        """Test invalid index handling."""
        with pytest.raises(ValueError, match="Index must be 0-9"):
            para_bridge.para_to_jd_area(PARACategory.PROJECTS, index=10)

        with pytest.raises(ValueError, match="Index must be 0-9"):
            para_bridge.para_to_jd_area(PARACategory.PROJECTS, index=-1)

    def test_jd_area_to_para(self, para_bridge):
        """Test JD area to PARA category conversion."""
        # Area 15 → Projects
        category = para_bridge.jd_area_to_para(15)
        assert category == PARACategory.PROJECTS

        # Area 25 → Areas
        category = para_bridge.jd_area_to_para(25)
        assert category == PARACategory.AREAS

        # Area 35 → Resources
        category = para_bridge.jd_area_to_para(35)
        assert category == PARACategory.RESOURCES

        # Area 45 → Archive
        category = para_bridge.jd_area_to_para(45)
        assert category == PARACategory.ARCHIVE

    def test_jd_area_to_para_outside_range(self, para_bridge):
        """Test JD area outside PARA range."""
        # Area 50 is not in PARA range
        category = para_bridge.jd_area_to_para(50)
        assert category is None

        category = para_bridge.jd_area_to_para(5)
        assert category is None

    def test_is_para_area(self, para_bridge):
        """Test PARA area checking."""
        # In range
        assert para_bridge.is_para_area(15)  # Projects
        assert para_bridge.is_para_area(25)  # Areas
        assert para_bridge.is_para_area(35)  # Resources
        assert para_bridge.is_para_area(45)  # Archive

        # Out of range
        assert not para_bridge.is_para_area(5)
        assert not para_bridge.is_para_area(50)

    def test_get_para_path_suggestion(self, para_bridge):
        """Test path suggestion generation."""
        path = para_bridge.get_para_path_suggestion(
            PARACategory.PROJECTS, "Website Redesign"
        )

        assert "10" in path
        assert "Projects" in path
        assert "Website Redesign" in path

    def test_create_para_structure(self, para_bridge, tmp_path):
        """Test PARA structure creation."""
        paths = para_bridge.create_para_structure(tmp_path)

        assert PARACategory.PROJECTS in paths
        assert PARACategory.AREAS in paths
        assert PARACategory.RESOURCES in paths
        assert PARACategory.ARCHIVE in paths

        # Verify paths exist
        for category, path in paths.items():
            assert path.exists()
            assert path.is_dir()


class TestCompatibilityAnalyzer:
    """Tests for CompatibilityAnalyzer."""

    def test_detect_para_structure(self, analyzer, para_structure):
        """Test PARA structure detection."""
        detected = analyzer.detect_para_structure(para_structure)

        assert detected[PARACategory.PROJECTS] is not None
        assert detected[PARACategory.AREAS] is not None
        assert detected[PARACategory.RESOURCES] is not None
        assert detected[PARACategory.ARCHIVE] is not None

    def test_detect_para_structure_empty(self, analyzer, tmp_path):
        """Test detection on empty directory."""
        detected = analyzer.detect_para_structure(tmp_path)

        assert all(path is None for path in detected.values())

    def test_detect_para_structure_partial(self, analyzer, tmp_path):
        """Test detection with partial PARA structure."""
        # Only create Projects and Areas
        (tmp_path / "Projects").mkdir()
        (tmp_path / "Areas").mkdir()

        detected = analyzer.detect_para_structure(tmp_path)

        assert detected[PARACategory.PROJECTS] is not None
        assert detected[PARACategory.AREAS] is not None
        assert detected[PARACategory.RESOURCES] is None
        assert detected[PARACategory.ARCHIVE] is None

    def test_is_mixed_structure(self, analyzer, tmp_path):
        """Test mixed structure detection."""
        # Create both PARA and JD folders
        (tmp_path / "Projects").mkdir()
        (tmp_path / "10 Finance").mkdir()

        is_mixed = analyzer.is_mixed_structure(tmp_path)
        assert is_mixed

    def test_is_mixed_structure_pure_para(self, analyzer, para_structure):
        """Test pure PARA structure detection."""
        is_mixed = analyzer.is_mixed_structure(para_structure)
        # Should not be mixed (pure PARA)
        assert not is_mixed

    def test_is_mixed_structure_pure_jd(self, analyzer, tmp_path):
        """Test pure JD structure detection."""
        (tmp_path / "10 Finance").mkdir()
        (tmp_path / "20 Marketing").mkdir()

        is_mixed = analyzer.is_mixed_structure(tmp_path)
        # Should not be mixed (pure JD)
        assert not is_mixed

    def test_suggest_migration_strategy(self, analyzer, para_structure):
        """Test migration strategy suggestion."""
        strategy = analyzer.suggest_migration_strategy(para_structure)

        assert "detected_para" in strategy
        assert "is_mixed_structure" in strategy
        assert "recommendations" in strategy
        assert len(strategy["recommendations"]) > 0


class TestHybridOrganizer:
    """Tests for HybridOrganizer."""

    def test_create_hybrid_structure(self, hybrid_organizer, tmp_path):
        """Test hybrid structure creation."""
        paths = hybrid_organizer.create_hybrid_structure(tmp_path)

        # Check PARA paths created
        assert "para_projects" in paths
        assert "para_areas" in paths
        assert "para_resources" in paths
        assert "para_archive" in paths

        # Check JD paths created within each
        assert "jd_area_projects" in paths
        assert "jd_category_projects" in paths

        # Verify paths exist
        for key, path in paths.items():
            assert path.exists()

    def test_categorize_item(self, hybrid_organizer):
        """Test item categorization."""
        jd_number = hybrid_organizer.categorize_item(
            "Website Project", PARACategory.PROJECTS
        )

        assert jd_number.area == 10  # Projects area
        assert jd_number.category is not None
        assert jd_number.level == NumberLevel.CATEGORY

    def test_get_item_path_area(self, hybrid_organizer, tmp_path):
        """Test path generation for area level."""
        jd_number = JohnnyDecimalNumber(
            area=10, category=None, id_number=None, level=NumberLevel.AREA
        )

        path = hybrid_organizer.get_item_path(
            tmp_path, PARACategory.PROJECTS, jd_number, "General"
        )

        assert "10 Projects" in str(path)
        assert "10 General" in str(path)

    def test_get_item_path_category(self, hybrid_organizer, tmp_path):
        """Test path generation for category level."""
        jd_number = JohnnyDecimalNumber(
            area=10, category=1, id_number=None, level=NumberLevel.CATEGORY
        )

        path = hybrid_organizer.get_item_path(
            tmp_path, PARACategory.PROJECTS, jd_number, "Website"
        )

        assert "10 Projects" in str(path)
        assert "10.01 Website" in str(path)

    def test_get_item_path_id(self, hybrid_organizer, tmp_path):
        """Test path generation for ID level."""
        jd_number = JohnnyDecimalNumber(
            area=10, category=1, id_number=1, level=NumberLevel.ID
        )

        path = hybrid_organizer.get_item_path(
            tmp_path, PARACategory.PROJECTS, jd_number, "Design Phase"
        )

        assert "10 Projects" in str(path)
        assert "10.01.001 Design Phase" in str(path)


class TestPARAAdapter:
    """Tests for PARAAdapter."""

    def test_adapt_to_jd_projects(self, para_adapter):
        """Test adapting Projects item to JD."""
        item = OrganizationItem(
            name="Website Redesign",
            path=Path("Projects/Website Redesign"),
            category="projects",
            metadata={"subcategory": 1},
        )

        jd_number = para_adapter.adapt_to_jd(item)

        assert jd_number.area == 10  # Projects area
        assert jd_number.category == 1

    def test_adapt_to_jd_areas(self, para_adapter):
        """Test adapting Areas item to JD."""
        item = OrganizationItem(
            name="Personal Finance",
            path=Path("Areas/Personal Finance"),
            category="areas",
            metadata={"subcategory": 2},
        )

        jd_number = para_adapter.adapt_to_jd(item)

        assert jd_number.area == 20  # Areas area
        assert jd_number.category == 2

    def test_adapt_to_jd_resources(self, para_adapter):
        """Test adapting Resources item to JD."""
        item = OrganizationItem(
            name="Code Snippets",
            path=Path("Resources/Code Snippets"),
            category="resources",
            metadata={},
        )

        jd_number = para_adapter.adapt_to_jd(item)

        assert jd_number.area == 30  # Resources area

    def test_adapt_to_jd_archive(self, para_adapter):
        """Test adapting Archive item to JD."""
        item = OrganizationItem(
            name="2023 Projects",
            path=Path("Archive/2023 Projects"),
            category="archive",
            metadata={},
        )

        jd_number = para_adapter.adapt_to_jd(item)

        assert jd_number.area == 40  # Archive area

    def test_adapt_to_jd_invalid_category(self, para_adapter):
        """Test adapting item with invalid category."""
        item = OrganizationItem(
            name="Random",
            path=Path("Random"),
            category="invalid",
            metadata={},
        )

        with pytest.raises(ValueError, match="Cannot determine PARA category"):
            para_adapter.adapt_to_jd(item)

    def test_adapt_from_jd_projects(self, para_adapter):
        """Test adapting JD to PARA Projects."""
        jd_number = JohnnyDecimalNumber(
            area=15, category=1, id_number=None, level=NumberLevel.CATEGORY
        )

        item = para_adapter.adapt_from_jd(jd_number, "Website")

        assert item.category == "projects"
        assert "Projects" in str(item.path)

    def test_adapt_from_jd_invalid_area(self, para_adapter):
        """Test adapting JD number outside PARA range."""
        jd_number = JohnnyDecimalNumber(
            area=50, category=1, id_number=None, level=NumberLevel.CATEGORY
        )

        with pytest.raises(ValueError, match="not in PARA range"):
            para_adapter.adapt_from_jd(jd_number, "Item")

    def test_can_adapt(self, para_adapter):
        """Test adapter compatibility checking."""
        para_item = OrganizationItem(
            name="Project",
            path=Path("Projects/Project"),
            category="projects",
            metadata={},
        )

        non_para_item = OrganizationItem(
            name="Random",
            path=Path("Random"),
            category="other",
            metadata={},
        )

        assert para_adapter.can_adapt(para_item)
        assert not para_adapter.can_adapt(non_para_item)


class TestPARAIntegration:
    """Integration tests for PARA compatibility."""

    def test_complete_para_workflow(self, tmp_path):
        """Test complete PARA integration workflow."""
        # Setup
        config = create_para_compatible_config()
        organizer = HybridOrganizer(config)

        # Create hybrid structure
        paths = organizer.create_hybrid_structure(tmp_path)
        assert len(paths) > 0

        # Add items to each PARA category
        for para_cat in PARACategory:
            jd_number = organizer.categorize_item(f"Test {para_cat.value}", para_cat)
            path = organizer.get_item_path(
                tmp_path, para_cat, jd_number, f"Test {para_cat.value}"
            )

            # Create the path
            path.mkdir(parents=True, exist_ok=True)
            assert path.exists()

    def test_para_migration(self, para_structure):
        """Test migrating existing PARA structure."""
        config = create_para_compatible_config()
        analyzer = CompatibilityAnalyzer(config)

        # Detect existing PARA
        detected = analyzer.detect_para_structure(para_structure)
        assert any(detected.values())

        # Get migration strategy
        strategy = analyzer.suggest_migration_strategy(para_structure)
        assert len(strategy["recommendations"]) > 0

    def test_para_adapter_roundtrip(self, para_config):
        """Test roundtrip conversion PARA → JD → PARA."""
        adapter = PARAAdapter(para_config)

        # Original item
        original = OrganizationItem(
            name="Website Project",
            path=Path("Projects/Website"),
            category="projects",
            metadata={},
        )

        # Convert to JD
        jd_number = adapter.adapt_to_jd(original)

        # Convert back to PARA
        restored = adapter.adapt_from_jd(jd_number, "Website Project")

        # Should preserve category
        assert restored.category == original.category


class TestEdgeCases:
    """Tests for edge cases in PARA compatibility."""

    def test_para_detection_case_insensitive(self, analyzer, tmp_path):
        """Test case-insensitive PARA detection."""
        # Create folders with different cases
        (tmp_path / "PROJECTS").mkdir()
        (tmp_path / "areas").mkdir()
        (tmp_path / "Resources").mkdir()

        detected = analyzer.detect_para_structure(tmp_path)

        # Should detect all despite case differences
        assert detected[PARACategory.PROJECTS] is not None
        assert detected[PARACategory.AREAS] is not None
        assert detected[PARACategory.RESOURCES] is not None

    def test_para_adapter_with_metadata(self, para_adapter):
        """Test adapter with custom metadata."""
        item = OrganizationItem(
            name="Complex Project",
            path=Path("Projects/Complex"),
            category="projects",
            metadata={"subcategory": 5, "priority": "high"},
        )

        jd_number = para_adapter.adapt_to_jd(item)

        assert jd_number.area == 10
        assert jd_number.category == 5  # Uses metadata hint

    def test_hybrid_structure_with_existing_folders(self, hybrid_organizer, tmp_path):
        """Test creating hybrid structure with existing folders."""
        # Create some folders first
        (tmp_path / "10 Existing").mkdir()

        # Create hybrid structure
        paths = hybrid_organizer.create_hybrid_structure(tmp_path)

        # Should handle existing folders
        assert all(path.exists() for path in paths.values())
