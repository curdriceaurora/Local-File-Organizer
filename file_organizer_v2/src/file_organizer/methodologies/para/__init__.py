"""
PARA Methodology Implementation

The PARA method is a universal system for organizing digital information and life.
PARA stands for Projects, Areas, Resources, and Archive.

Components:
- categories: Core PARA category definitions and data models
- config: Configuration management for PARA categorization
- detection: Heuristic-based detection algorithms
- rules: Rule engine for custom categorization logic
- folder_generator: PARA folder structure generation
- migration_manager: Migration from flat structures to PARA

Author: File Organizer v2.0
License: MIT
"""

from .categories import (
    CategorizationResult,
    CategoryDefinition,
    PARACategory,
    get_all_category_definitions,
    get_category_definition,
)
from .folder_generator import FolderCreationResult, PARAFolderGenerator
from .migration_manager import (
    MigrationFile,
    MigrationPlan,
    MigrationReport,
    PARAMigrationManager,
)

__all__ = [
    "PARACategory",
    "CategoryDefinition",
    "CategorizationResult",
    "get_category_definition",
    "get_all_category_definitions",
    "PARAFolderGenerator",
    "FolderCreationResult",
    "PARAMigrationManager",
    "MigrationPlan",
    "MigrationReport",
    "MigrationFile",
]

__version__ = "1.0.0"
