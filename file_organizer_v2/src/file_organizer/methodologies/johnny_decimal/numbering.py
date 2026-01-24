"""
Johnny Decimal Number Generation

This module provides number generation logic for the Johnny Decimal system,
including automatic number assignment, validation, and conflict detection.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

from .categories import (
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalNumber,
    NumberingScheme,
    NumberingResult,
)

logger = logging.getLogger(__name__)


class NumberConflictError(Exception):
    """Raised when a number assignment conflicts with existing numbers."""

    pass


class InvalidNumberError(Exception):
    """Raised when a number is invalid or out of range."""

    pass


class JohnnyDecimalGenerator:
    """
    Generator for Johnny Decimal numbers with automatic assignment
    and conflict resolution.
    """

    def __init__(self, scheme: NumberingScheme):
        """
        Initialize the generator with a numbering scheme.

        Args:
            scheme: The Johnny Decimal numbering scheme to use
        """
        self.scheme = scheme
        self._used_numbers: Set[str] = set()
        self._number_mappings: Dict[str, Path] = {}

    def register_existing_number(self, number: JohnnyDecimalNumber, file_path: Path) -> None:
        """
        Register an existing number to track usage and prevent conflicts.

        Args:
            number: The Johnny Decimal number to register
            file_path: The file path associated with this number

        Raises:
            NumberConflictError: If number is already registered
        """
        number_str = number.formatted_number

        if number_str in self._used_numbers:
            existing_path = self._number_mappings.get(number_str)
            raise NumberConflictError(
                f"Number {number_str} is already registered to {existing_path}"
            )

        self._used_numbers.add(number_str)
        self._number_mappings[number_str] = file_path
        logger.debug(f"Registered number {number_str} for {file_path}")

    def is_number_available(self, number: JohnnyDecimalNumber) -> bool:
        """
        Check if a number is available for assignment.

        Args:
            number: The number to check

        Returns:
            True if number is available, False otherwise
        """
        number_str = number.formatted_number

        # Check if already used
        if number_str in self._used_numbers:
            return False

        # Check if reserved in scheme
        if self.scheme.is_number_reserved(number):
            return False

        return True

    def get_next_available_area(self, preferred_area: Optional[int] = None) -> int:
        """
        Get the next available area number.

        Args:
            preferred_area: Preferred area number to try first

        Returns:
            Next available area number

        Raises:
            InvalidNumberError: If no areas are available
        """
        available_areas = self.scheme.get_available_areas()

        if not available_areas:
            raise InvalidNumberError("No areas defined in scheme")

        # Try preferred area first
        if preferred_area is not None and preferred_area in available_areas:
            # Check if any numbers in this area are available
            for cat in range(100):
                test_num = JohnnyDecimalNumber(area=preferred_area, category=cat)
                if self.is_number_available(test_num):
                    return preferred_area

        # Find first available area
        for area in available_areas:
            for cat in range(100):
                test_num = JohnnyDecimalNumber(area=area, category=cat)
                if self.is_number_available(test_num):
                    return area

        raise InvalidNumberError("No available area numbers")

    def get_next_available_category(self, area: int) -> int:
        """
        Get the next available category number in an area.

        Args:
            area: The area number

        Returns:
            Next available category number

        Raises:
            InvalidNumberError: If no categories are available in this area
        """
        for category in range(100):
            test_num = JohnnyDecimalNumber(area=area, category=category)
            if self.is_number_available(test_num):
                return category

        raise InvalidNumberError(f"No available category numbers in area {area}")

    def get_next_available_id(self, area: int, category: int) -> int:
        """
        Get the next available ID number in a category.

        Args:
            area: The area number
            category: The category number

        Returns:
            Next available ID number

        Raises:
            InvalidNumberError: If no IDs are available in this category
        """
        for item_id in range(1000):
            test_num = JohnnyDecimalNumber(area=area, category=category, item_id=item_id)
            if self.is_number_available(test_num):
                return item_id

        raise InvalidNumberError(
            f"No available ID numbers in category {area:02d}.{category:02d}"
        )

    def generate_area_number(
        self,
        name: str,
        description: str = "",
        preferred_area: Optional[int] = None,
    ) -> JohnnyDecimalNumber:
        """
        Generate a new area number.

        Args:
            name: Name for this area
            description: Optional description
            preferred_area: Preferred area number (will use if available)

        Returns:
            New Johnny Decimal area number

        Raises:
            InvalidNumberError: If number cannot be generated
        """
        if preferred_area is not None:
            test_num = JohnnyDecimalNumber(
                area=preferred_area, name=name, description=description
            )
            if self.is_number_available(test_num):
                return test_num

        # Find next available
        area = self.get_next_available_area(preferred_area)
        return JohnnyDecimalNumber(area=area, name=name, description=description)

    def generate_category_number(
        self,
        area: int,
        name: str,
        description: str = "",
        preferred_category: Optional[int] = None,
    ) -> JohnnyDecimalNumber:
        """
        Generate a new category number within an area.

        Args:
            area: The area number
            name: Name for this category
            description: Optional description
            preferred_category: Preferred category number

        Returns:
            New Johnny Decimal category number

        Raises:
            InvalidNumberError: If number cannot be generated
        """
        if preferred_category is not None:
            test_num = JohnnyDecimalNumber(
                area=area,
                category=preferred_category,
                name=name,
                description=description,
            )
            if self.is_number_available(test_num):
                return test_num

        # Find next available
        category = self.get_next_available_category(area)
        return JohnnyDecimalNumber(
            area=area, category=category, name=name, description=description
        )

    def generate_id_number(
        self,
        area: int,
        category: int,
        name: str,
        description: str = "",
        preferred_id: Optional[int] = None,
    ) -> JohnnyDecimalNumber:
        """
        Generate a new ID number within a category.

        Args:
            area: The area number
            category: The category number
            name: Name for this ID
            description: Optional description
            preferred_id: Preferred ID number

        Returns:
            New Johnny Decimal ID number

        Raises:
            InvalidNumberError: If number cannot be generated
        """
        if preferred_id is not None:
            test_num = JohnnyDecimalNumber(
                area=area,
                category=category,
                item_id=preferred_id,
                name=name,
                description=description,
            )
            if self.is_number_available(test_num):
                return test_num

        # Find next available
        item_id = self.get_next_available_id(area, category)
        return JohnnyDecimalNumber(
            area=area,
            category=category,
            item_id=item_id,
            name=name,
            description=description,
        )

    def suggest_number_for_content(
        self,
        content: str,
        filename: str = "",
        prefer_category: bool = True,
    ) -> Tuple[JohnnyDecimalNumber, float, List[str]]:
        """
        Suggest a Johnny Decimal number based on content analysis.

        Args:
            content: The file content to analyze
            filename: Optional filename for additional hints
            prefer_category: If True, prefer category-level numbers over IDs

        Returns:
            Tuple of (suggested_number, confidence, reasons)
        """
        reasons: List[str] = []
        best_area: Optional[int] = None
        best_category: Optional[CategoryDefinition] = None
        max_matches = 0

        # Analyze content against area definitions
        for area_num, area_def in self.scheme.areas.items():
            if area_def.matches_keyword(content) or area_def.matches_keyword(filename):
                matches = sum(
                    1 for kw in area_def.keywords
                    if kw.lower() in content.lower() or kw.lower() in filename.lower()
                )
                if matches > max_matches:
                    max_matches = matches
                    best_area = area_num
                    reasons = [
                        f"Content matches area '{area_def.name}' keywords",
                        f"Matched {matches} keywords: {', '.join(area_def.keywords[:3])}...",
                    ]

        # If no area found, use first available
        if best_area is None:
            best_area = self.get_next_available_area()
            reasons.append(f"Using default area {best_area}")
            confidence = 0.3
        else:
            confidence = min(0.9, 0.5 + (max_matches * 0.1))

        # Try to find best category
        available_categories = self.scheme.get_available_categories(best_area)
        for cat_key in available_categories:
            cat_def = self.scheme.categories[cat_key]
            if cat_def.matches_keyword(content) or cat_def.matches_pattern(filename):
                best_category = cat_def
                reasons.append(f"Matched category '{cat_def.name}'")
                confidence = min(0.95, confidence + 0.15)
                break

        # Generate the number
        if best_category and prefer_category:
            # Use the matched category directly
            number = JohnnyDecimalNumber(
                area=best_category.area,
                category=best_category.category
            )
            # Check if it's available, if not generate an ID within it
            if not self.is_number_available(number):
                try:
                    item_id = self.get_next_available_id(
                        best_category.area, best_category.category
                    )
                    number = JohnnyDecimalNumber(
                        area=best_category.area,
                        category=best_category.category,
                        item_id=item_id
                    )
                    reasons.append("Category matched but occupied, using ID level")
                except InvalidNumberError:
                    # Category is full, use area level
                    number = JohnnyDecimalNumber(area=best_area)
                    reasons.append("Category full, using area number")
        else:
            # Generate new category in best area
            try:
                category = self.get_next_available_category(best_area)
                number = JohnnyDecimalNumber(area=best_area, category=category)
                if not prefer_category:
                    # Add ID level
                    item_id = self.get_next_available_id(best_area, category)
                    number = JohnnyDecimalNumber(
                        area=best_area, category=category, item_id=item_id
                    )
            except InvalidNumberError:
                number = JohnnyDecimalNumber(area=best_area)
                reasons.append("Using area-level number")

        return number, confidence, reasons

    def validate_number(self, number: JohnnyDecimalNumber) -> Tuple[bool, List[str]]:
        """
        Validate a Johnny Decimal number against the scheme.

        Args:
            number: The number to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors: List[str] = []

        # Check if area exists in scheme
        area_def = self.scheme.get_area(number.area)
        if area_def is None:
            errors.append(f"Area {number.area} is not defined in scheme")

        # Check if category is defined (if present)
        if number.category is not None:
            cat_def = self.scheme.get_category(number.area, number.category)
            if cat_def is None and number.category >= 10:
                # Allow undefined categories in valid ranges
                pass

        # Check if number is reserved
        if self.scheme.is_number_reserved(number):
            errors.append(f"Number {number.formatted_number} is reserved")

        # Check if number is already used
        if number.formatted_number in self._used_numbers:
            existing_path = self._number_mappings.get(number.formatted_number)
            errors.append(
                f"Number {number.formatted_number} is already used by {existing_path}"
            )

        return len(errors) == 0, errors

    def find_conflicts(
        self, number: JohnnyDecimalNumber
    ) -> List[Tuple[str, Path]]:
        """
        Find all numbers that conflict with the given number.

        Args:
            number: The number to check for conflicts

        Returns:
            List of (conflicting_number, file_path) tuples
        """
        conflicts: List[Tuple[str, Path]] = []
        number_str = number.formatted_number

        # Check exact match
        if number_str in self._used_numbers:
            path = self._number_mappings[number_str]
            conflicts.append((number_str, path))

        # Check parent conflicts (e.g., if assigning 11.01 but 11 exists)
        if number.category is not None:
            parent = f"{number.area:02d}"
            if parent in self._used_numbers:
                path = self._number_mappings[parent]
                conflicts.append((parent, path))

        # Check child conflicts (e.g., if assigning 11 but 11.01 exists)
        if number.category is None:
            for used_num in self._used_numbers:
                if used_num.startswith(f"{number.area:02d}."):
                    path = self._number_mappings[used_num]
                    conflicts.append((used_num, path))

        return conflicts

    def resolve_conflict(
        self, number: JohnnyDecimalNumber, strategy: str = "increment"
    ) -> JohnnyDecimalNumber:
        """
        Resolve a number conflict by finding an alternative.

        Args:
            number: The conflicting number
            strategy: Conflict resolution strategy ('increment', 'skip', 'suggest')

        Returns:
            Alternative non-conflicting number

        Raises:
            InvalidNumberError: If no alternative can be found
        """
        if strategy == "increment":
            # Try incrementing at the lowest level
            if number.item_id is not None:
                # Increment ID
                return self.generate_id_number(
                    area=number.area,
                    category=number.category,
                    name=number.name,
                    description=number.description,
                )
            elif number.category is not None:
                # Increment category
                return self.generate_category_number(
                    area=number.area,
                    name=number.name,
                    description=number.description,
                )
            else:
                # Increment area
                return self.generate_area_number(
                    name=number.name,
                    description=number.description,
                )

        elif strategy == "skip":
            # Skip to next available in range
            if number.item_id is not None:
                item_id = self.get_next_available_id(number.area, number.category)
                return JohnnyDecimalNumber(
                    area=number.area,
                    category=number.category,
                    item_id=item_id,
                    name=number.name,
                    description=number.description,
                )
            elif number.category is not None:
                category = self.get_next_available_category(number.area)
                return JohnnyDecimalNumber(
                    area=number.area,
                    category=category,
                    name=number.name,
                    description=number.description,
                )
            else:
                area = self.get_next_available_area()
                return JohnnyDecimalNumber(
                    area=area,
                    name=number.name,
                    description=number.description,
                )

        else:  # suggest
            # Use content-based suggestion
            return self.generate_area_number(
                name=number.name or "Unknown",
                description=number.description,
            )

    def get_usage_statistics(self) -> Dict[str, any]:
        """
        Get statistics about number usage.

        Returns:
            Dictionary with usage statistics
        """
        stats = {
            "total_numbers": len(self._used_numbers),
            "areas_used": len(set(
                JohnnyDecimalNumber.from_string(n).area
                for n in self._used_numbers
            )),
            "categories_used": len(set(
                n for n in self._used_numbers if "." in n and n.count(".") == 1
            )),
            "ids_used": len(set(
                n for n in self._used_numbers if n.count(".") == 2
            )),
            "reserved_numbers": len(self.scheme.reserved_numbers),
        }

        return stats

    def clear_registrations(self) -> None:
        """Clear all registered numbers (for testing or reset)."""
        self._used_numbers.clear()
        self._number_mappings.clear()
        logger.info("Cleared all number registrations")
