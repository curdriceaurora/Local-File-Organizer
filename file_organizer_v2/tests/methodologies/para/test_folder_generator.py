"""
Tests for PARA folder generation.

Tests folder structure generation, validation, and category path management.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.folder_generator import (
    FolderCreationResult,
    PARAFolderGenerator,
)


class TestPARAFolderGenerator:
    """Test PARA folder structure generation."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return PARAConfig(
            project_dir="Projects",
            area_dir="Areas",
            resource_dir="Resources",
            archive_dir="Archive",
        )

    @pytest.fixture
    def generator(self, config):
        """Create folder generator instance."""
        return PARAFolderGenerator(config)

    def test_initialization(self, config):
        """Test generator initialization."""
        generator = PARAFolderGenerator(config)
        assert generator.config == config

        # Test default config
        default_generator = PARAFolderGenerator()
        assert default_generator.config is not None

    def test_generate_basic_structure(self, generator, temp_dir):
        """Test generating basic PARA folder structure."""
        result = generator.generate_structure(temp_dir, create_subdirs=False)

        assert result.success is True
        assert len(result.created_folders) == 4
        assert len(result.errors) == 0

        # Check all main folders exist
        assert (temp_dir / "Projects").exists()
        assert (temp_dir / "Areas").exists()
        assert (temp_dir / "Resources").exists()
        assert (temp_dir / "Archive").exists()

    def test_generate_structure_with_subdirs(self, generator, temp_dir):
        """Test generating structure with standard subdirectories."""
        result = generator.generate_structure(temp_dir, create_subdirs=True)

        assert result.success is True
        assert len(result.created_folders) > 4  # Main + subdirs

        # Check Projects subdirectories
        assert (temp_dir / "Projects" / "Active").exists()
        assert (temp_dir / "Projects" / "Completed").exists()

        # Check Areas subdirectories
        assert (temp_dir / "Areas" / "Personal").exists()
        assert (temp_dir / "Areas" / "Professional").exists()

        # Check Resources subdirectories
        assert (temp_dir / "Resources" / "Topics").exists()
        assert (temp_dir / "Resources" / "References").exists()

        # Check Archive subdirectories
        assert (temp_dir / "Archive" / "Projects").exists()
        assert (temp_dir / "Archive" / "Areas").exists()
        assert (temp_dir / "Archive" / "Resources").exists()

    def test_dry_run_mode(self, generator, temp_dir):
        """Test dry run mode doesn't create folders."""
        result = generator.generate_structure(temp_dir, dry_run=True)

        assert result.success is True
        assert len(result.created_folders) > 0  # Would have created

        # Check folders were NOT actually created
        assert not (temp_dir / "Projects").exists()
        assert not (temp_dir / "Areas").exists()
        assert not (temp_dir / "Resources").exists()
        assert not (temp_dir / "Archive").exists()

    def test_existing_folders_skipped(self, generator, temp_dir):
        """Test that existing folders are skipped, not overwritten."""
        # Create structure first time
        result1 = generator.generate_structure(temp_dir, create_subdirs=False)
        assert result1.success is True
        assert len(result1.created_folders) == 4

        # Try to create again
        result2 = generator.generate_structure(temp_dir, create_subdirs=False)
        assert result2.success is True
        assert len(result2.created_folders) == 0  # Nothing created
        assert len(result2.skipped_folders) == 4  # All skipped

    def test_create_category_folder_project(self, generator, temp_dir):
        """Test creating a specific category folder."""
        folder = generator.create_category_folder(
            PARACategory.PROJECT, root_path=temp_dir
        )

        assert folder == temp_dir / "Projects"
        assert folder.exists()
        assert folder.is_dir()

    def test_create_category_folder_with_subfolder(self, generator, temp_dir):
        """Test creating category folder with subfolder."""
        folder = generator.create_category_folder(
            PARACategory.PROJECT, subfolder="Active", root_path=temp_dir
        )

        assert folder == temp_dir / "Projects" / "Active"
        assert folder.exists()
        assert folder.is_dir()
        assert (temp_dir / "Projects").exists()  # Parent also created

    def test_create_category_folder_no_root(self):
        """Test that missing root path raises error."""
        config = PARAConfig(default_root=None)
        generator = PARAFolderGenerator(config)

        with pytest.raises(ValueError, match="No root path"):
            generator.create_category_folder(PARACategory.PROJECT)

    def test_create_category_folder_with_default_root(self, temp_dir):
        """Test creating folder using config default root."""
        config = PARAConfig(default_root=temp_dir)
        generator = PARAFolderGenerator(config)

        folder = generator.create_category_folder(PARACategory.AREA)

        assert folder == temp_dir / "Areas"
        assert folder.exists()

    def test_validate_structure_valid(self, generator, temp_dir):
        """Test validating a complete PARA structure."""
        # Create structure
        generator.generate_structure(temp_dir, create_subdirs=False)

        # Validate
        is_valid = generator.validate_structure(temp_dir)
        assert is_valid is True

    def test_validate_structure_missing_folder(self, generator, temp_dir):
        """Test validation fails with missing folder."""
        # Create partial structure
        (temp_dir / "Projects").mkdir()
        (temp_dir / "Areas").mkdir()
        (temp_dir / "Resources").mkdir()
        # Missing Archive

        is_valid = generator.validate_structure(temp_dir)
        assert is_valid is False

    def test_validate_structure_empty_root(self, generator, temp_dir):
        """Test validation fails on empty root."""
        is_valid = generator.validate_structure(temp_dir)
        assert is_valid is False

    def test_get_category_path_project(self, generator, temp_dir):
        """Test getting path for Project category."""
        path = generator.get_category_path(PARACategory.PROJECT, temp_dir)
        assert path == temp_dir / "Projects"

    def test_get_category_path_area(self, generator, temp_dir):
        """Test getting path for Area category."""
        path = generator.get_category_path(PARACategory.AREA, temp_dir)
        assert path == temp_dir / "Areas"

    def test_get_category_path_resource(self, generator, temp_dir):
        """Test getting path for Resource category."""
        path = generator.get_category_path(PARACategory.RESOURCE, temp_dir)
        assert path == temp_dir / "Resources"

    def test_get_category_path_archive(self, generator, temp_dir):
        """Test getting path for Archive category."""
        path = generator.get_category_path(PARACategory.ARCHIVE, temp_dir)
        assert path == temp_dir / "Archive"

    def test_get_category_path_no_root(self):
        """Test that missing root path raises error."""
        config = PARAConfig(default_root=None)
        generator = PARAFolderGenerator(config)

        with pytest.raises(ValueError, match="No root path"):
            generator.get_category_path(PARACategory.PROJECT)

    def test_get_category_path_with_default_root(self, temp_dir):
        """Test getting path using config default root."""
        config = PARAConfig(default_root=temp_dir)
        generator = PARAFolderGenerator(config)

        path = generator.get_category_path(PARACategory.PROJECT)
        assert path == temp_dir / "Projects"

    def test_custom_folder_names(self, temp_dir):
        """Test using custom folder names."""
        config = PARAConfig(
            project_dir="MyProjects",
            area_dir="MyAreas",
            resource_dir="MyResources",
            archive_dir="MyArchive",
        )
        generator = PARAFolderGenerator(config)

        result = generator.generate_structure(temp_dir, create_subdirs=False)

        assert result.success is True
        assert (temp_dir / "MyProjects").exists()
        assert (temp_dir / "MyAreas").exists()
        assert (temp_dir / "MyResources").exists()
        assert (temp_dir / "MyArchive").exists()

    def test_error_handling_invalid_permissions(self, generator):
        """Test error handling when folder creation fails."""
        # Try to create in a non-existent parent that can't be created
        invalid_path = Path("/root/definitely_no_permission_here")

        result = generator.generate_structure(invalid_path, create_subdirs=False)

        assert result.success is False
        assert len(result.errors) > 0
        assert invalid_path in [error[0] for error in result.errors]


class TestFolderCreationResult:
    """Test FolderCreationResult dataclass."""

    def test_success_result(self):
        """Test successful creation result."""
        result = FolderCreationResult(
            created_folders=[Path("/test/Projects")],
            skipped_folders=[],
            errors=[],
            success=True,
        )

        assert result.success is True
        assert len(result.created_folders) == 1
        assert len(result.skipped_folders) == 0
        assert len(result.errors) == 0

    def test_partial_success_result(self):
        """Test result with both created and skipped folders."""
        result = FolderCreationResult(
            created_folders=[Path("/test/Projects")],
            skipped_folders=[Path("/test/Areas")],
            errors=[],
            success=True,
        )

        assert result.success is True
        assert len(result.created_folders) == 1
        assert len(result.skipped_folders) == 1

    def test_error_result(self):
        """Test result with errors."""
        result = FolderCreationResult(
            created_folders=[],
            skipped_folders=[],
            errors=[(Path("/test/Projects"), "Permission denied")],
            success=False,
        )

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0][1] == "Permission denied"
