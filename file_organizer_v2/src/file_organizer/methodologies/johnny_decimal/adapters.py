"""
Johnny Decimal Methodology Adapters

Adapter pattern implementation for bridging Johnny Decimal with other
organizational methodologies and file management systems.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from .categories import JohnnyDecimalNumber, NumberLevel
from .compatibility import PARACategory, PARAJohnnyDecimalBridge
from .config import JohnnyDecimalConfig

logger = logging.getLogger(__name__)


@dataclass
class OrganizationItem:
    """Generic item in any organizational system."""

    name: str
    path: Path
    category: str
    metadata: Dict[str, Any]


class OrganizationMethodology(Protocol):
    """Protocol defining organization methodology interface."""

    def categorize(self, item: OrganizationItem) -> str:
        """Categorize an item according to methodology."""
        ...

    def suggest_location(self, item: OrganizationItem) -> Path:
        """Suggest location for item."""
        ...


class MethodologyAdapter(ABC):
    """
    Base adapter for methodology integration.

    Provides common interface for adapting different organizational
    methodologies to work with Johnny Decimal.
    """

    @abstractmethod
    def adapt_to_jd(self, item: OrganizationItem) -> JohnnyDecimalNumber:
        """
        Adapt item to Johnny Decimal number.

        Args:
            item: Item from source methodology

        Returns:
            Equivalent JD number
        """
        pass

    @abstractmethod
    def adapt_from_jd(
        self, jd_number: JohnnyDecimalNumber, item_name: str
    ) -> OrganizationItem:
        """
        Adapt JD number to source methodology item.

        Args:
            jd_number: Johnny Decimal number
            item_name: Item name

        Returns:
            Item in source methodology format
        """
        pass

    @abstractmethod
    def can_adapt(self, item: OrganizationItem) -> bool:
        """
        Check if item can be adapted.

        Args:
            item: Item to check

        Returns:
            True if item can be adapted
        """
        pass


class PARAAdapter(MethodologyAdapter):
    """
    Adapter for PARA methodology integration.

    Translates between PARA (Projects/Areas/Resources/Archive)
    and Johnny Decimal structures.
    """

    def __init__(self, config: JohnnyDecimalConfig):
        """
        Initialize PARA adapter.

        Args:
            config: Johnny Decimal configuration with PARA integration
        """
        self.config = config
        self.bridge = PARAJohnnyDecimalBridge(config.compatibility.para_integration)

    def adapt_to_jd(self, item: OrganizationItem) -> JohnnyDecimalNumber:
        """
        Convert PARA item to JD number.

        Args:
            item: PARA item

        Returns:
            JD number in PARA-mapped area

        Raises:
            ValueError: If item category not recognized
        """
        # Determine PARA category
        category_lower = item.category.lower()

        para_category = None
        for cat in PARACategory:
            if cat.value in category_lower:
                para_category = cat
                break

        if not para_category:
            raise ValueError(f"Cannot determine PARA category for: {item.category}")

        # Get base area for this PARA category
        base_area = self.bridge.para_to_jd_area(para_category, index=0)

        # Use metadata hints if available
        subcategory = item.metadata.get("subcategory", 1)
        if not isinstance(subcategory, int):
            subcategory = 1

        return JohnnyDecimalNumber(
            area=base_area,
            category=subcategory,
            id_number=None,
            level=NumberLevel.CATEGORY,
        )

    def adapt_from_jd(
        self, jd_number: JohnnyDecimalNumber, item_name: str
    ) -> OrganizationItem:
        """
        Convert JD number to PARA item.

        Args:
            jd_number: JD number
            item_name: Item name

        Returns:
            PARA organization item

        Raises:
            ValueError: If JD number not in PARA range
        """
        # Determine PARA category from JD area
        para_category = self.bridge.jd_area_to_para(jd_number.area)

        if not para_category:
            raise ValueError(
                f"JD area {jd_number.area} is not in PARA range"
            )

        # Construct path
        para_folder = para_category.value.title()
        path = Path(para_folder) / item_name

        return OrganizationItem(
            name=item_name,
            path=path,
            category=para_category.value,
            metadata={
                "jd_number": jd_number.formatted_number,
                "para_category": para_category.value,
            },
        )

    def can_adapt(self, item: OrganizationItem) -> bool:
        """Check if item is PARA-compatible."""
        category_lower = item.category.lower()
        return any(cat.value in category_lower for cat in PARACategory)


class FileSystemAdapter(MethodologyAdapter):
    """
    Adapter for generic filesystem organization.

    Maps filesystem folders to JD numbers based on heuristics
    and naming patterns.
    """

    def __init__(self, config: JohnnyDecimalConfig):
        """
        Initialize filesystem adapter.

        Args:
            config: Johnny Decimal configuration
        """
        self.config = config

    def adapt_to_jd(self, item: OrganizationItem) -> JohnnyDecimalNumber:
        """
        Convert filesystem item to JD number.

        Uses custom mappings or sequential assignment.

        Args:
            item: Filesystem item

        Returns:
            Assigned JD number
        """
        # Check custom mappings first
        item_name_lower = item.name.lower()
        if item_name_lower in self.config.custom_mappings:
            area = self.config.custom_mappings[item_name_lower]
            return JohnnyDecimalNumber(
                area=area, category=None, id_number=None, level=NumberLevel.AREA
            )

        # Fallback: use depth to determine level
        depth = len(item.path.parts)

        if depth <= 1:
            # Top level → Area
            area = self._suggest_area_from_name(item.name)
            return JohnnyDecimalNumber(
                area=area, category=None, id_number=None, level=NumberLevel.AREA
            )
        elif depth == 2:
            # Second level → Category
            area = self._suggest_area_from_name(item.path.parts[0])
            category = self._suggest_category_from_name(item.name)
            return JohnnyDecimalNumber(
                area=area, category=category, id_number=None, level=NumberLevel.CATEGORY
            )
        else:
            # Third level → ID
            area = self._suggest_area_from_name(item.path.parts[0])
            category = self._suggest_category_from_name(item.path.parts[1])
            id_num = self._suggest_id_from_index(depth - 3)
            return JohnnyDecimalNumber(
                area=area, category=category, id_number=id_num, level=NumberLevel.ID
            )

    def adapt_from_jd(
        self, jd_number: JohnnyDecimalNumber, item_name: str
    ) -> OrganizationItem:
        """
        Convert JD number to filesystem item.

        Args:
            jd_number: JD number
            item_name: Item name

        Returns:
            Filesystem organization item
        """
        # Construct path based on JD level
        if jd_number.level == NumberLevel.AREA:
            path = Path(f"{jd_number.area:02d} {item_name}")
        elif jd_number.level == NumberLevel.CATEGORY:
            area_name = f"{jd_number.area:02d} Area"
            cat_name = f"{jd_number.area:02d}.{jd_number.category:02d} {item_name}"
            path = Path(area_name) / cat_name
        else:  # ID
            area_name = f"{jd_number.area:02d} Area"
            cat_name = f"{jd_number.area:02d}.{jd_number.category:02d} Category"
            id_name = f"{jd_number.area:02d}.{jd_number.category:02d}.{jd_number.id_number:03d} {item_name}"
            path = Path(area_name) / cat_name / id_name

        return OrganizationItem(
            name=item_name,
            path=path,
            category="filesystem",
            metadata={"jd_number": jd_number.formatted_number},
        )

    def can_adapt(self, item: OrganizationItem) -> bool:
        """Any filesystem item can be adapted."""
        return True

    def _suggest_area_from_name(self, name: str) -> int:
        """Suggest area number from folder name."""
        # Try to extract number from name
        parts = name.split()
        if parts and parts[0].isdigit():
            num = int(parts[0])
            if 10 <= num <= 99:
                return num

        # Default: hash-based assignment (using deterministic MD5)
        hash_value = int(hashlib.md5(name.lower().encode()).hexdigest(), 16)
        return 10 + (hash_value % 90)

    def _suggest_category_from_name(self, name: str) -> int:
        """Suggest category number from folder name."""
        # Try to extract from XX.XX format
        parts = name.split()
        if parts and "." in parts[0]:
            nums = parts[0].split(".")
            if len(nums) >= 2 and nums[1].isdigit():
                num = int(nums[1])
                if 1 <= num <= 99:
                    return num

        # Default: hash-based (using deterministic MD5)
        hash_value = int(hashlib.md5(name.lower().encode()).hexdigest(), 16)
        return 1 + (hash_value % 99)

    def _suggest_id_from_index(self, index: int) -> int:
        """Suggest ID number from index."""
        return min(max(index + 1, 1), 999)


class AdapterRegistry:
    """
    Registry for methodology adapters.

    Manages multiple adapters and routes items to appropriate adapter.
    """

    def __init__(self):
        """Initialize adapter registry."""
        self._adapters: List[MethodologyAdapter] = []

    def register(self, adapter: MethodologyAdapter) -> None:
        """
        Register an adapter.

        Args:
            adapter: Adapter to register
        """
        self._adapters.append(adapter)
        logger.info(f"Registered adapter: {adapter.__class__.__name__}")

    def get_adapter(self, item: OrganizationItem) -> Optional[MethodologyAdapter]:
        """
        Get appropriate adapter for item.

        Args:
            item: Item to adapt

        Returns:
            Suitable adapter or None
        """
        for adapter in self._adapters:
            if adapter.can_adapt(item):
                return adapter
        return None

    def adapt_to_jd(self, item: OrganizationItem) -> Optional[JohnnyDecimalNumber]:
        """
        Adapt item to JD using registered adapters.

        Args:
            item: Item to adapt

        Returns:
            JD number or None if no adapter found
        """
        adapter = self.get_adapter(item)
        if adapter:
            return adapter.adapt_to_jd(item)
        return None

    def adapt_from_jd(
        self, jd_number: JohnnyDecimalNumber, item_name: str, methodology: str = "para"
    ) -> Optional[OrganizationItem]:
        """
        Adapt JD number to specified methodology.

        Args:
            jd_number: JD number to adapt
            item_name: Item name
            methodology: Target methodology ("para", "filesystem")

        Returns:
            Organization item or None if no adapter found
        """
        # Find adapter by type
        for adapter in self._adapters:
            if methodology == "para" and isinstance(adapter, PARAAdapter):
                return adapter.adapt_from_jd(jd_number, item_name)
            elif methodology == "filesystem" and isinstance(adapter, FileSystemAdapter):
                return adapter.adapt_from_jd(jd_number, item_name)

        return None


def create_default_registry(config: JohnnyDecimalConfig) -> AdapterRegistry:
    """
    Create adapter registry with default adapters.

    Args:
        config: Johnny Decimal configuration

    Returns:
        Registry with PARA and filesystem adapters
    """
    registry = AdapterRegistry()

    # Register PARA adapter if enabled
    if config.compatibility.para_integration.enabled:
        registry.register(PARAAdapter(config))
        logger.info("PARA adapter registered")

    # Always register filesystem adapter as fallback
    registry.register(FileSystemAdapter(config))
    logger.info("Filesystem adapter registered")

    return registry
