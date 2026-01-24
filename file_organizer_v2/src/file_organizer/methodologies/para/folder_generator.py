"""
PARA Folder Structure Generator

Creates and manages PARA (Projects, Areas, Resources, Archive) folder structures
with support for custom templates and nested organizations.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .categories import PARACategory
from .config import PARAConfig

logger = logging.getLogger(__name__)


@dataclass
class FolderCreationResult:
    """Result of folder creation operation."""
    created_folders: list[Path]
    skipped_folders: list[Path]
    errors: list[tuple[Path, str]]
    success: bool


class PARAFolderGenerator:
    """
    Generates PARA folder structures.

    Creates the standard Projects/Areas/Resources/Archive structure
    with support for custom naming and nested subfolders.
    """

    def __init__(self, config: Optional[PARAConfig] = None):
        """
        Initialize the PARA folder generator.

        Args:
            config: PARA configuration (uses default if None)
        """
        self.config = config or PARAConfig()

    def generate_structure(
        self,
        root_path: Path,
        create_subdirs: bool = True,
        dry_run: bool = False
    ) -> FolderCreationResult:
        """
        Generate standard PARA folder structure.

        Args:
            root_path: Root directory for PARA structure
            create_subdirs: Whether to create standard subdirectories
            dry_run: If True, don't actually create folders

        Returns:
            FolderCreationResult with details of operation
        """
        logger.info(f"Generating PARA structure at: {root_path}")

        created: list[Path] = []
        skipped: list[Path] = []
        errors: list[tuple[Path, str]] = []

        # Ensure root exists
        if not dry_run:
            try:
                root_path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Ensured root exists: {root_path}")
            except Exception as e:
                errors.append((root_path, str(e)))
                return FolderCreationResult(created, skipped, errors, False)

        # Create main PARA categories
        main_folders = {
            PARACategory.PROJECT: self.config.project_dir,
            PARACategory.AREA: self.config.area_dir,
            PARACategory.RESOURCE: self.config.resource_dir,
            PARACategory.ARCHIVE: self.config.archive_dir,
        }

        for category, folder_name in main_folders.items():
            folder_path = root_path / folder_name

            if folder_path.exists():
                logger.debug(f"Folder already exists: {folder_path}")
                skipped.append(folder_path)
                continue

            if not dry_run:
                try:
                    folder_path.mkdir(parents=True, exist_ok=True)
                    created.append(folder_path)
                    logger.info(f"Created {category.value}: {folder_path}")
                except Exception as e:
                    logger.error(f"Failed to create {folder_path}: {e}")
                    errors.append((folder_path, str(e)))
            else:
                created.append(folder_path)
                logger.info(f"[DRY RUN] Would create: {folder_path}")

        # Create standard subdirectories if requested
        if create_subdirs:
            subdirs = self._get_standard_subdirs(root_path)
            for subdir in subdirs:
                if subdir.exists():
                    skipped.append(subdir)
                    continue

                if not dry_run:
                    try:
                        subdir.mkdir(parents=True, exist_ok=True)
                        created.append(subdir)
                        logger.info(f"Created subdir: {subdir}")
                    except Exception as e:
                        logger.error(f"Failed to create {subdir}: {e}")
                        errors.append((subdir, str(e)))
                else:
                    created.append(subdir)
                    logger.info(f"[DRY RUN] Would create: {subdir}")

        success = len(errors) == 0
        return FolderCreationResult(created, skipped, errors, success)

    def _get_standard_subdirs(self, root_path: Path) -> list[Path]:
        """
        Get standard subdirectories for PARA structure.

        Args:
            root_path: Root directory

        Returns:
            List of subdirectory paths to create
        """
        subdirs = []

        # Projects subdirectories
        projects_root = root_path / self.config.project_dir
        subdirs.extend([
            projects_root / "Active",
            projects_root / "Completed",
        ])

        # Areas subdirectories
        areas_root = root_path / self.config.area_dir
        subdirs.extend([
            areas_root / "Personal",
            areas_root / "Professional",
        ])

        # Resources subdirectories
        resources_root = root_path / self.config.resource_dir
        subdirs.extend([
            resources_root / "Topics",
            resources_root / "References",
        ])

        # Archive subdirectories (organized by year)
        # Note: Year-based organization can be added dynamically
        archive_root = root_path / self.config.archive_dir
        subdirs.extend([
            archive_root / "Projects",
            archive_root / "Areas",
            archive_root / "Resources",
        ])

        return subdirs

    def create_category_folder(
        self,
        category: PARACategory,
        subfolder: Optional[str] = None,
        root_path: Optional[Path] = None
    ) -> Path:
        """
        Create a specific category folder.

        Args:
            category: PARA category
            subfolder: Optional subfolder name within category
            root_path: Root path (uses config default if None)

        Returns:
            Path to created folder

        Raises:
            ValueError: If category is invalid
            OSError: If folder creation fails
        """
        if root_path is None:
            if self.config.default_root is None:
                raise ValueError("No root path specified and no default configured")
            root_path = self.config.default_root

        # Get category folder name
        category_name = {
            PARACategory.PROJECT: self.config.project_dir,
            PARACategory.AREA: self.config.area_dir,
            PARACategory.RESOURCE: self.config.resource_dir,
            PARACategory.ARCHIVE: self.config.archive_dir,
        }.get(category)

        if category_name is None:
            raise ValueError(f"Invalid category: {category}")

        # Build path
        folder_path = root_path / category_name
        if subfolder:
            folder_path = folder_path / subfolder

        # Create folder
        folder_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created category folder: {folder_path}")

        return folder_path

    def validate_structure(self, root_path: Path) -> bool:
        """
        Validate that PARA structure exists and is complete.

        Args:
            root_path: Root directory to validate

        Returns:
            True if structure is valid, False otherwise
        """
        required_folders = [
            root_path / self.config.project_dir,
            root_path / self.config.area_dir,
            root_path / self.config.resource_dir,
            root_path / self.config.archive_dir,
        ]

        for folder in required_folders:
            if not folder.exists() or not folder.is_dir():
                logger.warning(f"Missing or invalid folder: {folder}")
                return False

        logger.info(f"PARA structure validated at: {root_path}")
        return True

    def get_category_path(
        self,
        category: PARACategory,
        root_path: Optional[Path] = None
    ) -> Path:
        """
        Get the path for a PARA category.

        Args:
            category: PARA category
            root_path: Root path (uses config default if None)

        Returns:
            Path to category folder
        """
        if root_path is None:
            if self.config.default_root is None:
                raise ValueError("No root path specified and no default configured")
            root_path = self.config.default_root

        category_name = {
            PARACategory.PROJECT: self.config.project_dir,
            PARACategory.AREA: self.config.area_dir,
            PARACategory.RESOURCE: self.config.resource_dir,
            PARACategory.ARCHIVE: self.config.archive_dir,
        }.get(category)

        if category_name is None:
            raise ValueError(f"Invalid category: {category}")

        return root_path / category_name
