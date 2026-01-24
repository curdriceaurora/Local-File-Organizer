"""
Johnny Decimal System Core

This module provides the main system orchestration for Johnny Decimal
file organization, including number assignment, validation, and management.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .categories import (
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalNumber,
    NumberingResult,
    NumberingScheme,
    get_default_scheme,
)
from .numbering import (
    InvalidNumberError,
    JohnnyDecimalGenerator,
    NumberConflictError,
)

logger = logging.getLogger(__name__)


class JohnnyDecimalSystem:
    """
    Main system for Johnny Decimal file organization.

    Orchestrates number generation, validation, conflict resolution,
    and persistence of the numbering scheme.
    """

    def __init__(
        self,
        scheme: Optional[NumberingScheme] = None,
        config_path: Optional[Path] = None,
    ):
        """
        Initialize the Johnny Decimal system.

        Args:
            scheme: Custom numbering scheme (uses default if None)
            config_path: Path to save/load configuration
        """
        self.scheme = scheme or get_default_scheme()
        self.generator = JohnnyDecimalGenerator(self.scheme)
        self.config_path = config_path
        self._initialized = False

        if config_path and config_path.exists():
            self.load_configuration(config_path)

    def initialize_from_directory(self, directory: Path) -> None:
        """
        Scan a directory to detect existing Johnny Decimal numbers.

        Args:
            directory: Directory to scan for existing numbers

        Raises:
            ValueError: If directory doesn't exist
        """
        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        logger.info(f"Initializing from directory: {directory}")
        detected_numbers = 0

        # Scan all items in directory
        for item in directory.rglob("*"):
            if item.is_file() or item.is_dir():
                number = self._extract_number_from_path(item)
                if number:
                    try:
                        self.generator.register_existing_number(number, item)
                        detected_numbers += 1
                        logger.debug(f"Detected number {number.formatted_number} in {item.name}")
                    except NumberConflictError as e:
                        logger.warning(f"Conflict detected: {e}")

        logger.info(f"Initialized with {detected_numbers} existing numbers")
        self._initialized = True

    def _extract_number_from_path(self, path: Path) -> Optional[JohnnyDecimalNumber]:
        """
        Extract Johnny Decimal number from a file or directory path.

        Looks for patterns like:
        - "10 Finance"
        - "11.01 Budgets"
        - "11.01.001 Q1 Budget"

        Args:
            path: File or directory path

        Returns:
            JohnnyDecimalNumber if found, None otherwise
        """
        name = path.name

        # Try to extract number patterns
        parts = name.split()
        if not parts:
            return None

        number_part = parts[0]

        try:
            # Parse the number
            number = JohnnyDecimalNumber.from_string(number_part)

            # Extract name from remaining parts
            if len(parts) > 1:
                name_part = " ".join(parts[1:])
                # Remove file extension if present
                name_part = Path(name_part).stem if "." in name_part else name_part
                number.name = name_part

            return number
        except (ValueError, IndexError):
            return None

    def assign_number_to_file(
        self,
        file_path: Path,
        content: Optional[str] = None,
        preferred_number: Optional[JohnnyDecimalNumber] = None,
        auto_register: bool = True,
    ) -> NumberingResult:
        """
        Assign a Johnny Decimal number to a file.

        Args:
            file_path: Path to the file
            content: Optional file content for analysis
            preferred_number: Preferred number to assign (if available)
            auto_register: Automatically register the assigned number

        Returns:
            NumberingResult with assigned number and metadata

        Raises:
            NumberConflictError: If preferred number conflicts
        """
        reasons: List[str] = []
        conflicts: List[str] = []
        alternative_numbers: Dict[str, float] = {}
        confidence = 0.5

        # Check if preferred number is available
        if preferred_number:
            is_valid, errors = self.generator.validate_number(preferred_number)

            if is_valid:
                number = preferred_number
                confidence = 0.95
                reasons.append("Using preferred number")
            else:
                conflicts.extend(errors)
                # Try to resolve conflict
                try:
                    number = self.generator.resolve_conflict(
                        preferred_number, strategy="increment"
                    )
                    confidence = 0.7
                    reasons.append(f"Resolved conflict: using {number.formatted_number}")
                    alternative_numbers[preferred_number.formatted_number] = 0.95
                except InvalidNumberError as e:
                    logger.error(f"Could not resolve conflict: {e}")
                    raise NumberConflictError(
                        f"Preferred number conflicts and no alternative found: {errors}"
                    )
        else:
            # Suggest number based on content
            if content:
                number, confidence, suggestion_reasons = (
                    self.generator.suggest_number_for_content(
                        content=content,
                        filename=file_path.name,
                        prefer_category=True,
                    )
                )
                reasons.extend(suggestion_reasons)
            else:
                # Use default area
                try:
                    area = self.generator.get_next_available_area()
                    category = self.generator.get_next_available_category(area)
                    number = JohnnyDecimalNumber(area=area, category=category)
                    confidence = 0.4
                    reasons.append("No content provided, using next available number")
                except InvalidNumberError as e:
                    logger.error(f"Could not generate number: {e}")
                    raise

        # Check for conflicts
        found_conflicts = self.generator.find_conflicts(number)
        if found_conflicts:
            conflicts.extend([
                f"{num} (used by {path})"
                for num, path in found_conflicts
            ])

        # Register the number if requested
        if auto_register and not found_conflicts:
            try:
                self.generator.register_existing_number(number, file_path)
                reasons.append(f"Registered number {number.formatted_number}")
            except NumberConflictError as e:
                conflicts.append(str(e))

        # Create result
        result = NumberingResult(
            file_path=file_path,
            number=number,
            confidence=confidence,
            reasons=reasons,
            alternative_numbers=alternative_numbers,
            conflicts=conflicts,
            metadata={
                "file_name": file_path.name,
                "file_size": file_path.stat().st_size if file_path.exists() else 0,
                "registered": auto_register and not found_conflicts,
            },
        )

        logger.info(
            f"Assigned {number.formatted_number} to {file_path.name} "
            f"(confidence: {confidence:.2f})"
        )

        return result

    def validate_number_assignment(
        self, number: JohnnyDecimalNumber, file_path: Path
    ) -> NumberingResult:
        """
        Validate a proposed number assignment without registering it.

        Args:
            number: The number to validate
            file_path: The file to assign the number to

        Returns:
            NumberingResult with validation details
        """
        is_valid, errors = self.generator.validate_number(number)
        conflicts = self.generator.find_conflicts(number)

        confidence = 1.0 if is_valid else 0.0
        reasons = ["Number is valid and available"] if is_valid else errors

        conflict_strs = [
            f"{num} (used by {path})"
            for num, path in conflicts
        ]

        return NumberingResult(
            file_path=file_path,
            number=number,
            confidence=confidence,
            reasons=reasons,
            conflicts=conflict_strs,
            metadata={
                "validation_only": True,
                "is_valid": is_valid,
            },
        )

    def renumber_file(
        self,
        old_number: JohnnyDecimalNumber,
        new_number: JohnnyDecimalNumber,
        file_path: Path,
    ) -> NumberingResult:
        """
        Renumber an existing file to a new Johnny Decimal number.

        Args:
            old_number: Current number
            new_number: New number to assign
            file_path: Path to the file

        Returns:
            NumberingResult with renumbering details

        Raises:
            NumberConflictError: If new number conflicts
            InvalidNumberError: If old number not found
        """
        old_str = old_number.formatted_number

        # Verify old number exists
        if old_str not in self.generator._used_numbers:
            raise InvalidNumberError(
                f"Old number {old_str} is not registered"
            )

        # Validate new number
        is_valid, errors = self.generator.validate_number(new_number)
        if not is_valid:
            raise NumberConflictError(
                f"New number {new_number.formatted_number} is not available: {errors}"
            )

        # Unregister old number
        self.generator._used_numbers.discard(old_str)
        self.generator._number_mappings.pop(old_str, None)

        # Register new number
        try:
            self.generator.register_existing_number(new_number, file_path)

            result = NumberingResult(
                file_path=file_path,
                number=new_number,
                confidence=1.0,
                reasons=[
                    f"Renumbered from {old_str} to {new_number.formatted_number}",
                    "Old number released and new number registered",
                ],
                conflicts=[],
                metadata={
                    "operation": "renumber",
                    "old_number": old_str,
                    "new_number": new_number.formatted_number,
                },
            )

            logger.info(
                f"Renumbered {file_path.name} from {old_str} "
                f"to {new_number.formatted_number}"
            )

            return result

        except NumberConflictError as e:
            # Rollback: restore old number
            self.generator._used_numbers.add(old_str)
            self.generator._number_mappings[old_str] = file_path
            raise

    def get_area_summary(self, area: int) -> Dict[str, any]:
        """
        Get summary information about an area.

        Args:
            area: Area number

        Returns:
            Dictionary with area information
        """
        area_def = self.scheme.get_area(area)
        categories = self.scheme.get_available_categories(area)

        # Count used numbers in this area
        used_numbers = [
            n for n in self.generator._used_numbers
            if n.startswith(f"{area:02d}")
        ]

        return {
            "area": area,
            "name": area_def.name if area_def else "Undefined",
            "description": area_def.description if area_def else "",
            "defined_categories": len(categories),
            "used_numbers": len(used_numbers),
            "available": area_def is not None,
            "numbers": sorted(used_numbers),
        }

    def get_all_areas_summary(self) -> List[Dict[str, any]]:
        """
        Get summary of all defined areas.

        Returns:
            List of area summaries
        """
        areas = self.scheme.get_available_areas()
        return [self.get_area_summary(area) for area in areas]

    def get_usage_report(self) -> Dict[str, any]:
        """
        Generate a comprehensive usage report.

        Returns:
            Dictionary with usage statistics and details
        """
        stats = self.generator.get_usage_statistics()
        areas_summary = self.get_all_areas_summary()

        return {
            "statistics": stats,
            "areas": areas_summary,
            "scheme_name": self.scheme.name,
            "scheme_description": self.scheme.description,
            "initialized": self._initialized,
        }

    def save_configuration(self, path: Optional[Path] = None) -> None:
        """
        Save the current configuration to a file.

        Args:
            path: Path to save configuration (uses self.config_path if None)

        Raises:
            ValueError: If no path provided and no default path set
        """
        save_path = path or self.config_path

        if not save_path:
            raise ValueError("No configuration path provided")

        config = {
            "scheme": {
                "name": self.scheme.name,
                "description": self.scheme.description,
                "allow_gaps": self.scheme.allow_gaps,
                "auto_increment": self.scheme.auto_increment,
                "reserved_numbers": list(self.scheme.reserved_numbers),
            },
            "used_numbers": {
                num: str(path)
                for num, path in self.generator._number_mappings.items()
            },
            "statistics": self.generator.get_usage_statistics(),
        }

        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Saved configuration to {save_path}")

    def load_configuration(self, path: Optional[Path] = None) -> None:
        """
        Load configuration from a file.

        Args:
            path: Path to load configuration from (uses self.config_path if None)

        Raises:
            ValueError: If no path provided and no default path set
            FileNotFoundError: If configuration file doesn't exist
        """
        load_path = path or self.config_path

        if not load_path:
            raise ValueError("No configuration path provided")

        if not load_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {load_path}")

        with open(load_path) as f:
            config = json.load(f)

        # Restore reserved numbers
        if "scheme" in config and "reserved_numbers" in config["scheme"]:
            self.scheme.reserved_numbers = set(config["scheme"]["reserved_numbers"])

        # Restore used numbers
        if "used_numbers" in config:
            self.generator.clear_registrations()
            for num_str, path_str in config["used_numbers"].items():
                try:
                    number = JohnnyDecimalNumber.from_string(num_str)
                    path = Path(path_str)
                    self.generator.register_existing_number(number, path)
                except (ValueError, NumberConflictError) as e:
                    logger.warning(f"Could not restore number {num_str}: {e}")

        logger.info(f"Loaded configuration from {load_path}")
        self._initialized = True

    def add_custom_area(self, area_def: AreaDefinition) -> None:
        """
        Add a custom area definition to the scheme.

        Args:
            area_def: The area definition to add
        """
        self.scheme.add_area(area_def)
        logger.info(
            f"Added custom area: {area_def.name} "
            f"({area_def.area_range_start}-{area_def.area_range_end})"
        )

    def add_custom_category(self, category_def: CategoryDefinition) -> None:
        """
        Add a custom category definition to the scheme.

        Args:
            category_def: The category definition to add
        """
        self.scheme.add_category(category_def)
        logger.info(
            f"Added custom category: {category_def.formatted_number} "
            f"{category_def.name}"
        )

    def reserve_number_range(
        self, start: JohnnyDecimalNumber, end: JohnnyDecimalNumber
    ) -> None:
        """
        Reserve a range of numbers to prevent automatic assignment.

        Args:
            start: Start of range (inclusive)
            end: End of range (inclusive)
        """
        # Simple range reservation - reserve each number individually
        if start.level != end.level:
            raise ValueError("Start and end must be at same hierarchy level")

        if start.area != end.area:
            raise ValueError("Range cannot span multiple areas")

        # Reserve based on level
        if start.level == "area":
            for area in range(start.area, end.area + 1):
                num = JohnnyDecimalNumber(area=area)
                self.scheme.reserve_number(num)
        elif start.level == "category":
            for cat in range(start.category, end.category + 1):
                num = JohnnyDecimalNumber(area=start.area, category=cat)
                self.scheme.reserve_number(num)
        else:  # ID level
            for item in range(start.item_id, end.item_id + 1):
                num = JohnnyDecimalNumber(
                    area=start.area, category=start.category, item_id=item
                )
                self.scheme.reserve_number(num)

        logger.info(
            f"Reserved range {start.formatted_number} to {end.formatted_number}"
        )

    def clear_all_registrations(self) -> None:
        """Clear all number registrations (for testing or reset)."""
        self.generator.clear_registrations()
        self._initialized = False
        logger.info("Cleared all registrations")
