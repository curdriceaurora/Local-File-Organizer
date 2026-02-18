"""
Johnny Decimal Methodology Implementation

The Johnny Decimal system is a decimal-based numbering scheme for organizing files
and folders hierarchically. It uses a three-level hierarchy:

- Areas: 00-99 (e.g., 10-19 for Finance)
- Categories: 00.00-99.99 (e.g., 11.01 for Budgets)
- IDs: 00.00.000-99.99.999 (e.g., 11.01.001 for Q1 Budget)

This system provides a scalable, human-readable way to organize information
with clear boundaries and easy navigation.

Components:
- categories: Core data models and definitions
- numbering: Number generation and validation logic
- system: Main system orchestration
- scanner: Directory scanning for migration
- transformer: Folder structure transformation
- validator: Migration plan validation
- migrator: Complete migration orchestration
- config: Configuration management for JD and hybrid setups
- compatibility: PARA integration and compatibility layer
- adapters: Methodology adapters for bridging systems

Based on the Johnny Decimal system by Johnny Noble (johnnydecimal.com).

Author: File Organizer v2.0
License: MIT
"""

from __future__ import annotations

from .adapters import (
    AdapterRegistry,
    FileSystemAdapter,
    MethodologyAdapter,
    OrganizationItem,
    PARAAdapter,
    create_default_registry,
)
from .categories import (
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalNumber,
    NumberingResult,
    NumberingScheme,
    NumberLevel,
    get_default_scheme,
)
from .compatibility import (
    CompatibilityAnalyzer,
    HybridOrganizer,
    PARACategory,
    PARAJohnnyDecimalBridge,
    PARAMapping,
)
from .config import (
    CompatibilityConfig,
    ConfigBuilder,
    JohnnyDecimalConfig,
    MigrationConfig,
    PARAIntegrationConfig,
    create_default_config,
    create_para_compatible_config,
)
from .migrator import (
    JohnnyDecimalMigrator,
    MigrationResult,
    RollbackInfo,
)
from .numbering import (
    InvalidNumberError,
    JohnnyDecimalGenerator,
    NumberConflictError,
)
from .scanner import (
    FolderInfo,
    FolderScanner,
    ScanResult,
)
from .system import (
    JohnnyDecimalSystem,
)
from .transformer import (
    FolderTransformer,
    TransformationPlan,
    TransformationRule,
)
from .validator import (
    MigrationValidator,
    ValidationIssue,
    ValidationResult,
)

__all__ = [
    # Data models
    "JohnnyDecimalNumber",
    "NumberLevel",
    "AreaDefinition",
    "CategoryDefinition",
    "NumberingScheme",
    "NumberingResult",
    # Core classes
    "JohnnyDecimalGenerator",
    "JohnnyDecimalSystem",
    # Migration classes
    "FolderScanner",
    "FolderInfo",
    "ScanResult",
    "FolderTransformer",
    "TransformationRule",
    "TransformationPlan",
    "MigrationValidator",
    "ValidationIssue",
    "ValidationResult",
    "JohnnyDecimalMigrator",
    "MigrationResult",
    "RollbackInfo",
    # Configuration
    "JohnnyDecimalConfig",
    "MigrationConfig",
    "PARAIntegrationConfig",
    "CompatibilityConfig",
    "ConfigBuilder",
    "create_default_config",
    "create_para_compatible_config",
    # Compatibility Layer
    "PARACategory",
    "PARAMapping",
    "PARAJohnnyDecimalBridge",
    "CompatibilityAnalyzer",
    "HybridOrganizer",
    # Adapters
    "OrganizationItem",
    "MethodologyAdapter",
    "PARAAdapter",
    "FileSystemAdapter",
    "AdapterRegistry",
    "create_default_registry",
    # Exceptions
    "NumberConflictError",
    "InvalidNumberError",
    # Utilities
    "get_default_scheme",
]

__version__ = "1.0.0"
