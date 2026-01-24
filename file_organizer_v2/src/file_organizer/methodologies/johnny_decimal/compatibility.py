"""
Johnny Decimal PARA Compatibility Layer

Integrates Johnny Decimal methodology with PARA (Projects/Areas/Resources/Archive)
organizational system, allowing hybrid setups and smooth migrations.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from .categories import JohnnyDecimalNumber, NumberLevel
from .config import JohnnyDecimalConfig, PARAIntegrationConfig

logger = logging.getLogger(__name__)


class PARACategory(Enum):
    """PARA methodology categories."""

    PROJECTS = "projects"
    AREAS = "areas"
    RESOURCES = "resources"
    ARCHIVE = "archive"


@dataclass
class PARAMapping:
    """Mapping between PARA category and JD area."""

    para_category: PARACategory
    jd_area_start: int
    jd_area_end: int
    description: str


class PARAJohnnyDecimalBridge:
    """
    Bridge between PARA and Johnny Decimal methodologies.

    Provides bidirectional mapping and translation between the two systems,
    enabling hybrid organizational structures.
    """

    def __init__(self, config: PARAIntegrationConfig):
        """
        Initialize the bridge.

        Args:
            config: PARA integration configuration
        """
        self.config = config
        self._create_mappings()

    def _create_mappings(self) -> None:
        """Create PARA to JD area mappings."""
        self.mappings: Dict[PARACategory, PARAMapping] = {
            PARACategory.PROJECTS: PARAMapping(
                para_category=PARACategory.PROJECTS,
                jd_area_start=self.config.projects_area,
                jd_area_end=self.config.projects_area + 9,
                description="Active projects with clear goals and deadlines",
            ),
            PARACategory.AREAS: PARAMapping(
                para_category=PARACategory.AREAS,
                jd_area_start=self.config.areas_area,
                jd_area_end=self.config.areas_area + 9,
                description="Ongoing responsibilities and standards",
            ),
            PARACategory.RESOURCES: PARAMapping(
                para_category=PARACategory.RESOURCES,
                jd_area_start=self.config.resources_area,
                jd_area_end=self.config.resources_area + 9,
                description="Reference materials and topics of interest",
            ),
            PARACategory.ARCHIVE: PARAMapping(
                para_category=PARACategory.ARCHIVE,
                jd_area_start=self.config.archive_area,
                jd_area_end=self.config.archive_area + 9,
                description="Completed projects and inactive items",
            ),
        }

    def para_to_jd_area(self, para_category: PARACategory, index: int = 0) -> int:
        """
        Convert PARA category to JD area number.

        Args:
            para_category: PARA category
            index: Index within category (0-9)

        Returns:
            JD area number

        Raises:
            ValueError: If index out of range
        """
        if not (0 <= index <= 9):
            raise ValueError(f"Index must be 0-9, got {index}")

        mapping = self.mappings[para_category]
        return mapping.jd_area_start + index

    def jd_area_to_para(self, area_number: int) -> Optional[PARACategory]:
        """
        Convert JD area number to PARA category.

        Args:
            area_number: JD area number

        Returns:
            PARA category or None if not in PARA range
        """
        for category, mapping in self.mappings.items():
            if mapping.jd_area_start <= area_number <= mapping.jd_area_end:
                return category
        return None

    def is_para_area(self, area_number: int) -> bool:
        """
        Check if JD area corresponds to PARA category.

        Args:
            area_number: JD area number

        Returns:
            True if area is in PARA range
        """
        return self.jd_area_to_para(area_number) is not None

    def get_para_path_suggestion(
        self, para_category: PARACategory, item_name: str
    ) -> str:
        """
        Suggest JD path for PARA item.

        Args:
            para_category: PARA category
            item_name: Item name

        Returns:
            Suggested JD path format
        """
        base_area = self.mappings[para_category].jd_area_start
        return f"{base_area:02d} {para_category.value.title()} / {base_area:02d}.01 {item_name}"

    def create_para_structure(self, root_path: Path) -> Dict[PARACategory, Path]:
        """
        Create PARA-compatible JD structure.

        Args:
            root_path: Root directory

        Returns:
            Dictionary mapping PARA categories to created paths

        Raises:
            OSError: If directory creation fails
        """
        created_paths: Dict[PARACategory, Path] = {}

        for category, mapping in self.mappings.items():
            # Create area folder
            area_name = f"{mapping.jd_area_start:02d} {category.value.title()}"
            area_path = root_path / area_name
            area_path.mkdir(parents=True, exist_ok=True)

            created_paths[category] = area_path
            logger.info(f"Created PARA area: {area_path}")

        return created_paths


class CompatibilityAnalyzer:
    """
    Analyzes folder structures for PARA patterns and JD compatibility.

    Helps identify existing PARA structures and suggest migration paths.
    """

    def __init__(self, config: JohnnyDecimalConfig):
        """
        Initialize analyzer.

        Args:
            config: Johnny Decimal configuration
        """
        self.config = config
        if config.compatibility.para_integration.enabled:
            self.bridge = PARAJohnnyDecimalBridge(config.compatibility.para_integration)
        else:
            self.bridge = None

    def detect_para_structure(self, root_path: Path) -> Dict[PARACategory, Optional[Path]]:
        """
        Detect existing PARA structure.

        Args:
            root_path: Root directory to analyze

        Returns:
            Dictionary mapping PARA categories to their paths (None if not found)
        """
        detected: Dict[PARACategory, Optional[Path]] = {
            category: None for category in PARACategory
        }

        if not root_path.exists() or not root_path.is_dir():
            logger.warning(f"Path does not exist or is not a directory: {root_path}")
            return detected

        # Look for PARA folders
        for item in root_path.iterdir():
            if not item.is_dir():
                continue

            name_lower = item.name.lower()

            # Check each PARA category
            for category in PARACategory:
                if category.value in name_lower:
                    detected[category] = item
                    logger.info(f"Detected PARA category: {category.value} at {item}")

        return detected

    def is_mixed_structure(self, root_path: Path) -> bool:
        """
        Check if structure mixes PARA and JD.

        Args:
            root_path: Root directory

        Returns:
            True if both PARA and JD patterns detected
        """
        # Validate path exists
        if not root_path.exists() or not root_path.is_dir():
            return False

        has_para = any(self.detect_para_structure(root_path).values())

        # Check for JD numbers
        has_jd = False
        for item in root_path.iterdir():
            if item.is_dir() and self._looks_like_jd(item.name):
                has_jd = True
                break

        return has_para and has_jd

    def _looks_like_jd(self, name: str) -> bool:
        """Check if name looks like JD format."""
        parts = name.split()
        if not parts:
            return False

        first = parts[0]
        # Check for XX, XX.XX, or XX.XX.XXX format
        if first.isdigit() and len(first) == 2:
            return True
        if "." in first:
            nums = first.split(".")
            if len(nums) in (2, 3) and all(n.isdigit() for n in nums):
                return True
        return False

    def suggest_migration_strategy(
        self, root_path: Path
    ) -> Dict[str, any]:
        """
        Suggest migration strategy for existing structure.

        Args:
            root_path: Root directory

        Returns:
            Dictionary with migration recommendations
        """
        para_detected = self.detect_para_structure(root_path)
        is_mixed = self.is_mixed_structure(root_path)

        strategy = {
            "detected_para": {
                cat.value: str(path) if path else None
                for cat, path in para_detected.items()
            },
            "is_mixed_structure": is_mixed,
            "recommendations": [],
        }

        # Add recommendations
        if any(para_detected.values()):
            if self.config.compatibility.para_integration.enabled:
                strategy["recommendations"].append(
                    "Use PARA-to-JD mapping to integrate existing PARA structure"
                )
                strategy["recommendations"].append(
                    f"Projects → Areas {self.config.compatibility.para_integration.projects_area}-{self.config.compatibility.para_integration.projects_area + 9}"
                )
                strategy["recommendations"].append(
                    f"Areas → Areas {self.config.compatibility.para_integration.areas_area}-{self.config.compatibility.para_integration.areas_area + 9}"
                )
                strategy["recommendations"].append(
                    f"Resources → Areas {self.config.compatibility.para_integration.resources_area}-{self.config.compatibility.para_integration.resources_area + 9}"
                )
                strategy["recommendations"].append(
                    f"Archive → Areas {self.config.compatibility.para_integration.archive_area}-{self.config.compatibility.para_integration.archive_area + 9}"
                )
            else:
                strategy["recommendations"].append(
                    "Enable PARA integration in config for better compatibility"
                )

        if is_mixed:
            strategy["recommendations"].append(
                "Mixed structure detected - consider consolidating to JD or keeping PARA at top level"
            )

        if not any(para_detected.values()) and not is_mixed:
            strategy["recommendations"].append(
                "Clean structure - can apply JD directly without special handling"
            )

        return strategy


class HybridOrganizer:
    """
    Manages hybrid PARA + JD organizational structures.

    Allows maintaining PARA at top level with JD within each category,
    or other hybrid approaches.
    """

    def __init__(self, config: JohnnyDecimalConfig):
        """
        Initialize hybrid organizer.

        Args:
            config: Johnny Decimal configuration
        """
        self.config = config
        self.bridge = PARAJohnnyDecimalBridge(config.compatibility.para_integration)
        self.analyzer = CompatibilityAnalyzer(config)

    def create_hybrid_structure(self, root_path: Path) -> Dict[str, Path]:
        """
        Create hybrid PARA + JD structure.

        Top level: PARA categories
        Within each: JD areas/categories

        Args:
            root_path: Root directory

        Returns:
            Dictionary of created paths

        Raises:
            OSError: If directory creation fails
        """
        created: Dict[str, Path] = {}

        # Create PARA top-level structure
        para_paths = self.bridge.create_para_structure(root_path)

        for category, category_path in para_paths.items():
            created[f"para_{category.value}"] = category_path

            # Create sample JD structure within each PARA category
            mapping = self.bridge.mappings[category]
            sample_area = mapping.jd_area_start

            # Create one sample area and category
            area_name = f"{sample_area:02d} {category.value.title()} Items"
            area_path = category_path / area_name
            area_path.mkdir(exist_ok=True)
            created[f"jd_area_{category.value}"] = area_path

            category_name = f"{sample_area:02d}.01 General"
            category_path_jd = category_path / category_name
            category_path_jd.mkdir(exist_ok=True)
            created[f"jd_category_{category.value}"] = category_path_jd

        logger.info(f"Created hybrid PARA + JD structure at {root_path}")
        return created

    def categorize_item(
        self, item_name: str, para_category: PARACategory
    ) -> JohnnyDecimalNumber:
        """
        Categorize item into hybrid structure.

        Args:
            item_name: Item to categorize
            para_category: PARA category for item

        Returns:
            Suggested JD number within PARA range
        """
        # Get base area for this PARA category
        base_area = self.bridge.para_to_jd_area(para_category, index=0)

        # Simple categorization: use first area, first category
        return JohnnyDecimalNumber(
            area=base_area,
            category=1,
            item_id=None,
        )

    def get_item_path(
        self,
        root_path: Path,
        para_category: PARACategory,
        jd_number: JohnnyDecimalNumber,
        item_name: str = "",
    ) -> Path:
        """
        Get full path for item in hybrid structure.

        Args:
            root_path: Root directory
            para_category: PARA category
            jd_number: JD number
            item_name: Optional item name

        Returns:
            Full path in hybrid structure
        """
        # PARA category folder
        para_folder = f"{self.bridge.mappings[para_category].jd_area_start:02d} {para_category.value.title()}"
        path = root_path / para_folder

        # JD formatted name
        if jd_number.level == NumberLevel.AREA:
            jd_name = f"{jd_number.area:02d}"
        elif jd_number.level == NumberLevel.CATEGORY:
            jd_name = f"{jd_number.area:02d}.{jd_number.category:02d}"
        else:  # ID
            jd_name = f"{jd_number.area:02d}.{jd_number.category:02d}.{jd_number.id_number:03d}"

        # Add item name if provided
        if item_name:
            jd_name = f"{jd_name} {item_name}"

        path = path / jd_name
        return path
