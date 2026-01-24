"""
Johnny Decimal Category Definitions and Data Models

This module defines the core data structures for the Johnny Decimal numbering
system, which uses a hierarchical decimal-based organization scheme.

The Johnny Decimal system:
- Areas: 00-99 (e.g., 10-19 Finance, 20-29 Marketing)
- Categories: 00.00-99.99 (e.g., 11.01, 11.02 within Finance area)
- IDs: Can extend to third level (e.g., 11.01.001)

Based on the Johnny Decimal system by Johnny Noble.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class NumberLevel(str, Enum):
    """
    Hierarchy levels in Johnny Decimal system.

    - AREA: Top level (10-19, 20-29, etc.) representing broad areas
    - CATEGORY: Second level (11.01, 11.02) representing categories within areas
    - ID: Third level (11.01.001) representing specific items
    """

    AREA = "area"
    CATEGORY = "category"
    ID = "id"

    def __str__(self) -> str:
        """Return the level name in title case."""
        return self.value.title()


@dataclass
class JohnnyDecimalNumber:
    """
    Represents a Johnny Decimal number with validation and formatting.

    Examples:
        - Area: 10 (Finance)
        - Category: 11.01 (Budgets)
        - ID: 11.01.001 (Q1 Budget)
    """

    area: int
    category: Optional[int] = None
    item_id: Optional[int] = None
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        """Validate the Johnny Decimal number."""
        # Validate area (00-99)
        if not 0 <= self.area <= 99:
            raise ValueError(f"Area must be between 0 and 99, got {self.area}")

        # Validate category if present (00-99)
        if self.category is not None:
            if not 0 <= self.category <= 99:
                raise ValueError(f"Category must be between 0 and 99, got {self.category}")

        # Validate item_id if present (000-999)
        if self.item_id is not None:
            if self.category is None:
                raise ValueError("Cannot have item_id without category")
            if not 0 <= self.item_id <= 999:
                raise ValueError(f"Item ID must be between 0 and 999, got {self.item_id}")

    @property
    def level(self) -> NumberLevel:
        """Determine the hierarchy level of this number."""
        if self.item_id is not None:
            return NumberLevel.ID
        elif self.category is not None:
            return NumberLevel.CATEGORY
        else:
            return NumberLevel.AREA

    @property
    def formatted_number(self) -> str:
        """
        Return the formatted Johnny Decimal number.

        Examples:
            - Area: "10"
            - Category: "11.01"
            - ID: "11.01.001"
        """
        if self.item_id is not None:
            return f"{self.area:02d}.{self.category:02d}.{self.item_id:03d}"
        elif self.category is not None:
            return f"{self.area:02d}.{self.category:02d}"
        else:
            return f"{self.area:02d}"

    @property
    def parent_number(self) -> Optional[str]:
        """Return the parent number in the hierarchy."""
        if self.item_id is not None:
            return f"{self.area:02d}.{self.category:02d}"
        elif self.category is not None:
            return f"{self.area:02d}"
        else:
            return None

    def __str__(self) -> str:
        """Return string representation with name if available."""
        base = self.formatted_number
        if self.name:
            return f"{base} {self.name}"
        return base

    def __repr__(self) -> str:
        """Return detailed representation."""
        return f"JohnnyDecimalNumber({self.formatted_number}, name='{self.name}')"

    def __eq__(self, other: object) -> bool:
        """Check equality based on number components only."""
        if not isinstance(other, JohnnyDecimalNumber):
            return NotImplemented
        return (
            self.area == other.area
            and self.category == other.category
            and self.item_id == other.item_id
        )

    def __hash__(self) -> int:
        """Make hashable for use in sets and dicts."""
        return hash((self.area, self.category, self.item_id))

    def __lt__(self, other: "JohnnyDecimalNumber") -> bool:
        """Support sorting of numbers."""
        return (self.area, self.category or 0, self.item_id or 0) < (
            other.area,
            other.category or 0,
            other.item_id or 0,
        )

    @classmethod
    def from_string(cls, number_str: str) -> "JohnnyDecimalNumber":
        """
        Parse a Johnny Decimal number from string.

        Args:
            number_str: String like "10", "11.01", or "11.01.001"

        Returns:
            JohnnyDecimalNumber instance

        Raises:
            ValueError: If string format is invalid
        """
        parts = number_str.split(".")

        if len(parts) == 1:
            # Area only
            return cls(area=int(parts[0]))
        elif len(parts) == 2:
            # Area and category
            return cls(area=int(parts[0]), category=int(parts[1]))
        elif len(parts) == 3:
            # Full number with ID
            return cls(
                area=int(parts[0]), category=int(parts[1]), item_id=int(parts[2])
            )
        else:
            raise ValueError(
                f"Invalid Johnny Decimal format: {number_str}. "
                "Expected formats: '10', '11.01', or '11.01.001'"
            )


@dataclass
class AreaDefinition:
    """
    Definition of a Johnny Decimal area (10-19, 20-29, etc.).

    Areas represent the broadest organizational divisions in the system.
    """

    area_range_start: int  # e.g., 10
    area_range_end: int  # e.g., 19
    name: str
    description: str
    keywords: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate area definition."""
        if not 0 <= self.area_range_start <= 99:
            raise ValueError(f"Area start must be 0-99, got {self.area_range_start}")
        if not 0 <= self.area_range_end <= 99:
            raise ValueError(f"Area end must be 0-99, got {self.area_range_end}")
        if self.area_range_start > self.area_range_end:
            raise ValueError(
                f"Area start ({self.area_range_start}) must be <= end ({self.area_range_end})"
            )
        if not self.name:
            raise ValueError("Area name cannot be empty")

    def contains(self, area_number: int) -> bool:
        """Check if an area number falls within this area definition."""
        return self.area_range_start <= area_number <= self.area_range_end

    def matches_keyword(self, text: str) -> bool:
        """Check if text contains any area keywords."""
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.keywords)


@dataclass
class CategoryDefinition:
    """
    Definition of a category within a Johnny Decimal area.

    Categories are second-level divisions (e.g., 11.01, 11.02) within an area.
    """

    area: int
    category: int
    name: str
    description: str
    keywords: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    auto_assign: bool = True

    def __post_init__(self) -> None:
        """Validate category definition."""
        if not 0 <= self.area <= 99:
            raise ValueError(f"Area must be 0-99, got {self.area}")
        if not 0 <= self.category <= 99:
            raise ValueError(f"Category must be 0-99, got {self.category}")
        if not self.name:
            raise ValueError("Category name cannot be empty")

    @property
    def formatted_number(self) -> str:
        """Return formatted category number."""
        return f"{self.area:02d}.{self.category:02d}"

    def matches_keyword(self, text: str) -> bool:
        """Check if text contains any category keywords."""
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.keywords)

    def matches_pattern(self, filename: str) -> bool:
        """Check if filename matches any category patterns."""
        from fnmatch import fnmatch

        filename_lower = filename.lower()
        return any(fnmatch(filename_lower, pattern.lower()) for pattern in self.patterns)


@dataclass
class NumberingResult:
    """
    Result of Johnny Decimal number assignment for a file.

    Contains the assigned number, confidence score, reasoning,
    and alternative possibilities.
    """

    file_path: Path
    number: JohnnyDecimalNumber
    confidence: float
    reasons: List[str]
    alternative_numbers: Dict[str, float] = field(default_factory=dict)
    applied_rules: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the numbering result."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

        if not self.reasons:
            raise ValueError("reasons list cannot be empty")

        # Ensure file_path is a Path object
        if not isinstance(self.file_path, Path):
            self.file_path = Path(self.file_path)

    @property
    def is_confident(self) -> bool:
        """Check if numbering confidence is high."""
        return self.confidence >= 0.75

    @property
    def requires_review(self) -> bool:
        """Check if numbering requires manual review."""
        return self.confidence < 0.60 or len(self.conflicts) > 0

    @property
    def has_conflicts(self) -> bool:
        """Check if there are any number conflicts."""
        return len(self.conflicts) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert the result to a dictionary."""
        return {
            "file_path": str(self.file_path),
            "number": self.number.formatted_number,
            "number_name": self.number.name,
            "level": self.number.level.value,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "alternative_numbers": self.alternative_numbers,
            "applied_rules": self.applied_rules,
            "metadata": self.metadata,
            "conflicts": self.conflicts,
            "is_confident": self.is_confident,
            "requires_review": self.requires_review,
            "has_conflicts": self.has_conflicts,
        }


@dataclass
class NumberingScheme:
    """
    Complete Johnny Decimal numbering scheme configuration.

    Contains all area definitions, category definitions, and rules
    for automatic number assignment.
    """

    name: str
    description: str
    areas: Dict[int, AreaDefinition] = field(default_factory=dict)
    categories: Dict[str, CategoryDefinition] = field(default_factory=dict)
    reserved_numbers: Set[str] = field(default_factory=set)
    allow_gaps: bool = True
    auto_increment: bool = True

    def __post_init__(self) -> None:
        """Validate the numbering scheme."""
        if not self.name:
            raise ValueError("Scheme name cannot be empty")

    def add_area(self, area_def: AreaDefinition) -> None:
        """Add an area definition to the scheme."""
        for area_num in range(area_def.area_range_start, area_def.area_range_end + 1):
            self.areas[area_num] = area_def

    def add_category(self, category_def: CategoryDefinition) -> None:
        """Add a category definition to the scheme."""
        key = f"{category_def.area:02d}.{category_def.category:02d}"
        self.categories[key] = category_def

    def get_area(self, area_number: int) -> Optional[AreaDefinition]:
        """Get the area definition for a given area number."""
        return self.areas.get(area_number)

    def get_category(self, area: int, category: int) -> Optional[CategoryDefinition]:
        """Get the category definition for a given area and category."""
        key = f"{area:02d}.{category:02d}"
        return self.categories.get(key)

    def is_number_reserved(self, number: JohnnyDecimalNumber) -> bool:
        """Check if a number is reserved."""
        return number.formatted_number in self.reserved_numbers

    def reserve_number(self, number: JohnnyDecimalNumber) -> None:
        """Reserve a number to prevent it from being assigned."""
        self.reserved_numbers.add(number.formatted_number)

    def get_available_areas(self) -> List[int]:
        """Get list of all defined area numbers."""
        return sorted(self.areas.keys())

    def get_available_categories(self, area: int) -> List[str]:
        """Get list of all defined categories in an area."""
        return sorted([
            key for key in self.categories.keys()
            if key.startswith(f"{area:02d}.")
        ])


# Default Johnny Decimal scheme with common area definitions
DEFAULT_AREAS: List[AreaDefinition] = [
    AreaDefinition(
        area_range_start=10,
        area_range_end=19,
        name="Finance & Administration",
        description="Financial records, budgets, invoices, and administrative tasks",
        keywords=[
            "budget", "invoice", "receipt", "expense", "financial",
            "accounting", "tax", "payment", "admin", "contract"
        ],
        examples=["Budget spreadsheet", "Invoice template", "Expense report"],
    ),
    AreaDefinition(
        area_range_start=20,
        area_range_end=29,
        name="Marketing & Sales",
        description="Marketing materials, campaigns, sales documents, and customer data",
        keywords=[
            "marketing", "campaign", "sales", "customer", "lead",
            "proposal", "pitch", "brand", "advertising", "promotion"
        ],
        examples=["Marketing plan", "Sales proposal", "Customer list"],
    ),
    AreaDefinition(
        area_range_start=30,
        area_range_end=39,
        name="Operations & Projects",
        description="Project plans, operational procedures, and process documentation",
        keywords=[
            "project", "operation", "process", "procedure", "workflow",
            "plan", "schedule", "task", "milestone", "deliverable"
        ],
        examples=["Project plan", "Process document", "Task list"],
    ),
    AreaDefinition(
        area_range_start=40,
        area_range_end=49,
        name="Human Resources",
        description="Employee records, policies, training materials, and HR documents",
        keywords=[
            "employee", "hr", "hiring", "training", "policy",
            "benefit", "payroll", "performance", "recruitment", "onboarding"
        ],
        examples=["Employee handbook", "Training material", "Job description"],
    ),
    AreaDefinition(
        area_range_start=50,
        area_range_end=59,
        name="Technology & IT",
        description="Technical documentation, code, infrastructure, and IT resources",
        keywords=[
            "code", "technical", "documentation", "software", "hardware",
            "infrastructure", "server", "database", "api", "system"
        ],
        examples=["API documentation", "Code repository", "System diagram"],
    ),
]


def get_default_scheme() -> NumberingScheme:
    """
    Get the default Johnny Decimal numbering scheme.

    Returns:
        NumberingScheme with default areas configured
    """
    scheme = NumberingScheme(
        name="Default Johnny Decimal Scheme",
        description="Standard Johnny Decimal numbering with common business areas",
        allow_gaps=True,
        auto_increment=True,
    )

    for area_def in DEFAULT_AREAS:
        scheme.add_area(area_def)

    return scheme
