"""
Johnny Decimal Configuration Management

Manages configuration for Johnny Decimal methodology including hybrid setups
with PARA and other organizational systems.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .categories import NumberingScheme, AreaDefinition, CategoryDefinition

logger = logging.getLogger(__name__)


@dataclass
class MigrationConfig:
    """Configuration for migration operations."""

    preserve_original_names: bool = True
    create_backups: bool = True
    max_depth: int = 10
    skip_hidden: bool = True
    auto_categorize: bool = False


@dataclass
class PARAIntegrationConfig:
    """Configuration for PARA methodology integration."""

    enabled: bool = False
    projects_area: int = 10  # Projects → Area 10-19
    areas_area: int = 20  # Areas → Area 20-29
    resources_area: int = 30  # Resources → Area 30-39
    archive_area: int = 40  # Archive → Area 40-49
    map_para_to_jd: bool = True
    preserve_para_structure: bool = False


@dataclass
class CompatibilityConfig:
    """Configuration for compatibility with other methodologies."""

    para_integration: PARAIntegrationConfig = field(default_factory=PARAIntegrationConfig)
    allow_mixed_structure: bool = True
    validate_before_migration: bool = True


@dataclass
class JohnnyDecimalConfig:
    """
    Complete configuration for Johnny Decimal system.

    Manages all aspects of JD setup including numbering scheme,
    migration settings, and compatibility options.
    """

    scheme: NumberingScheme
    migration: MigrationConfig = field(default_factory=MigrationConfig)
    compatibility: CompatibilityConfig = field(default_factory=CompatibilityConfig)
    custom_mappings: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert configuration to dictionary."""
        return {
            "scheme": {
                "name": self.scheme.name,
                "areas": [
                    {
                        "area_range_start": area.area_range_start,
                        "area_range_end": area.area_range_end,
                        "name": area.name,
                        "description": area.description,
                    }
                    for area in self.scheme.areas.values()
                ],
                "categories": [
                    {
                        "area": cat.area,
                        "category": cat.category,
                        "name": cat.name,
                        "description": cat.description,
                    }
                    for cat in self.scheme.categories.values()
                ],
            },
            "migration": {
                "preserve_original_names": self.migration.preserve_original_names,
                "create_backups": self.migration.create_backups,
                "max_depth": self.migration.max_depth,
                "skip_hidden": self.migration.skip_hidden,
                "auto_categorize": self.migration.auto_categorize,
            },
            "compatibility": {
                "para_integration": {
                    "enabled": self.compatibility.para_integration.enabled,
                    "projects_area": self.compatibility.para_integration.projects_area,
                    "areas_area": self.compatibility.para_integration.areas_area,
                    "resources_area": self.compatibility.para_integration.resources_area,
                    "archive_area": self.compatibility.para_integration.archive_area,
                    "map_para_to_jd": self.compatibility.para_integration.map_para_to_jd,
                    "preserve_para_structure": self.compatibility.para_integration.preserve_para_structure,
                },
                "allow_mixed_structure": self.compatibility.allow_mixed_structure,
                "validate_before_migration": self.compatibility.validate_before_migration,
            },
            "custom_mappings": self.custom_mappings,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "JohnnyDecimalConfig":
        """Create configuration from dictionary."""
        # Parse scheme
        scheme_data = data.get("scheme", {})
        areas = [
            AreaDefinition(
                area_range_start=area["area_range_start"],
                area_range_end=area["area_range_end"],
                name=area["name"],
                description=area.get("description", ""),
            )
            for area in scheme_data.get("areas", [])
        ]
        categories = [
            CategoryDefinition(
                area=cat["area"],
                category=cat["category"],
                name=cat["name"],
                description=cat.get("description", ""),
            )
            for cat in scheme_data.get("categories", [])
        ]
        # Create empty scheme and populate it
        scheme = NumberingScheme(
            name=scheme_data.get("name", "default"),
            description="",
        )
        # Add areas using the scheme's add_area method
        for area_def in areas:
            scheme.add_area(area_def)
        # Add categories using the scheme's add_category method
        for cat_def in categories:
            scheme.add_category(cat_def)

        # Parse migration config
        migration_data = data.get("migration", {})
        migration = MigrationConfig(
            preserve_original_names=migration_data.get("preserve_original_names", True),
            create_backups=migration_data.get("create_backups", True),
            max_depth=migration_data.get("max_depth", 10),
            skip_hidden=migration_data.get("skip_hidden", True),
            auto_categorize=migration_data.get("auto_categorize", False),
        )

        # Parse compatibility config
        compat_data = data.get("compatibility", {})
        para_data = compat_data.get("para_integration", {})
        para_integration = PARAIntegrationConfig(
            enabled=para_data.get("enabled", False),
            projects_area=para_data.get("projects_area", 10),
            areas_area=para_data.get("areas_area", 20),
            resources_area=para_data.get("resources_area", 30),
            archive_area=para_data.get("archive_area", 40),
            map_para_to_jd=para_data.get("map_para_to_jd", True),
            preserve_para_structure=para_data.get("preserve_para_structure", False),
        )
        compatibility = CompatibilityConfig(
            para_integration=para_integration,
            allow_mixed_structure=compat_data.get("allow_mixed_structure", True),
            validate_before_migration=compat_data.get("validate_before_migration", True),
        )

        return cls(
            scheme=scheme,
            migration=migration,
            compatibility=compatibility,
            custom_mappings=data.get("custom_mappings", {}),
        )

    def save_to_file(self, path: Path) -> None:
        """
        Save configuration to JSON file.

        Args:
            path: File path to save to

        Raises:
            OSError: If file cannot be written
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        logger.info(f"Configuration saved to {path}")

    @classmethod
    def load_from_file(cls, path: Path) -> "JohnnyDecimalConfig":
        """
        Load configuration from JSON file.

        Args:
            path: File path to load from

        Returns:
            JohnnyDecimalConfig instance

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path) as f:
            data = json.load(f)

        logger.info(f"Configuration loaded from {path}")
        return cls.from_dict(data)


class ConfigBuilder:
    """
    Builder for creating JohnnyDecimalConfig with fluent API.

    Provides convenient methods for constructing configurations
    programmatically.
    """

    def __init__(self, scheme_name: str = "default"):
        """
        Initialize builder.

        Args:
            scheme_name: Name for the numbering scheme
        """
        self._scheme_name = scheme_name
        self._areas: List[AreaDefinition] = []
        self._categories: List[CategoryDefinition] = []
        self._migration = MigrationConfig()
        self._compatibility = CompatibilityConfig()
        self._custom_mappings: Dict[str, int] = {}

    def add_area(self, area_number: int, title: str, description: str = "") -> "ConfigBuilder":
        """
        Add an area to the scheme.

        Args:
            area_number: Area number (10-99)
            title: Area title
            description: Optional description

        Returns:
            Self for chaining
        """
        self._areas.append(
            AreaDefinition(
                area_range_start=area_number,
                area_range_end=area_number,
                name=title,
                description=description
            )
        )
        return self

    def add_category(
        self, area_number: int, category_number: int, title: str, description: str = ""
    ) -> "ConfigBuilder":
        """
        Add a category to the scheme.

        Args:
            area_number: Parent area number
            category_number: Category number (01-99)
            title: Category title
            description: Optional description

        Returns:
            Self for chaining
        """
        self._categories.append(
            CategoryDefinition(
                area=area_number,
                category=category_number,
                name=title,
                description=description,
            )
        )
        return self

    def with_migration_config(
        self,
        preserve_names: bool = True,
        create_backups: bool = True,
        max_depth: int = 10,
    ) -> "ConfigBuilder":
        """
        Configure migration settings.

        Args:
            preserve_names: Keep original folder names
            create_backups: Create backups before migration
            max_depth: Maximum directory depth to scan

        Returns:
            Self for chaining
        """
        self._migration = MigrationConfig(
            preserve_original_names=preserve_names,
            create_backups=create_backups,
            max_depth=max_depth,
        )
        return self

    def with_para_integration(
        self,
        enabled: bool = True,
        projects_area: int = 10,
        areas_area: int = 20,
        resources_area: int = 30,
        archive_area: int = 40,
    ) -> "ConfigBuilder":
        """
        Enable and configure PARA integration.

        Args:
            enabled: Enable PARA integration
            projects_area: Area number for Projects
            areas_area: Area number for Areas
            resources_area: Area number for Resources
            archive_area: Area number for Archive

        Returns:
            Self for chaining
        """
        self._compatibility.para_integration = PARAIntegrationConfig(
            enabled=enabled,
            projects_area=projects_area,
            areas_area=areas_area,
            resources_area=resources_area,
            archive_area=archive_area,
        )
        return self

    def add_custom_mapping(self, folder_name: str, area_number: int) -> "ConfigBuilder":
        """
        Add custom folder-to-area mapping.

        Args:
            folder_name: Folder name to map
            area_number: Target area number

        Returns:
            Self for chaining
        """
        self._custom_mappings[folder_name.lower()] = area_number
        return self

    def build(self) -> JohnnyDecimalConfig:
        """
        Build the configuration.

        Returns:
            JohnnyDecimalConfig instance
        """
        # Create empty scheme and populate it
        scheme = NumberingScheme(
            name=self._scheme_name,
            description="",
        )

        # Add areas using the scheme's add_area method
        for area_def in self._areas:
            scheme.add_area(area_def)

        # Add categories using the scheme's add_category method
        for cat_def in self._categories:
            scheme.add_category(cat_def)

        return JohnnyDecimalConfig(
            scheme=scheme,
            migration=self._migration,
            compatibility=self._compatibility,
            custom_mappings=self._custom_mappings,
        )


def create_default_config() -> JohnnyDecimalConfig:
    """
    Create default Johnny Decimal configuration.

    Returns:
        JohnnyDecimalConfig with sensible defaults
    """
    from .categories import get_default_scheme

    return JohnnyDecimalConfig(
        scheme=get_default_scheme(),
        migration=MigrationConfig(),
        compatibility=CompatibilityConfig(),
    )


def create_para_compatible_config() -> JohnnyDecimalConfig:
    """
    Create configuration optimized for PARA compatibility.

    Returns:
        JohnnyDecimalConfig with PARA integration enabled
    """
    return (
        ConfigBuilder("para-compatible")
        .add_area(10, "Projects", "Active projects with deadlines")
        .add_area(20, "Areas", "Ongoing responsibilities")
        .add_area(30, "Resources", "Reference materials")
        .add_area(40, "Archive", "Completed items")
        .with_para_integration(enabled=True)
        .with_migration_config(preserve_names=True, create_backups=True)
        .build()
    )
