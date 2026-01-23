"""
PARA Category Definitions and Data Models

This module defines the core PARA (Projects, Areas, Resources, Archive) categories
and their associated data structures for automated categorization.

Based on Tiago Forte's PARA methodology from "Building a Second Brain".
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class PARACategory(str, Enum):
    """
    PARA methodology categories.
    
    The PARA system organizes information into four categories based on
    actionability and time-sensitivity:
    
    - PROJECT: Time-bound efforts with specific goals and deadlines
    - AREA: Ongoing responsibilities requiring maintenance over time
    - RESOURCE: Reference materials and knowledge for future use
    - ARCHIVE: Inactive items from the other three categories
    """
    
    PROJECT = "project"
    AREA = "area"
    RESOURCE = "resource"
    ARCHIVE = "archive"
    
    def __str__(self) -> str:
        """Return the category name in title case."""
        return self.value.title()
    
    @property
    def description(self) -> str:
        """Return a brief description of the category."""
        descriptions = {
            PARACategory.PROJECT: "Time-bound with specific completion criteria",
            PARACategory.AREA: "Ongoing responsibility without end date",
            PARACategory.RESOURCE: "Reference material or knowledge base",
            PARACategory.ARCHIVE: "Completed or inactive item"
        }
        return descriptions[self]


@dataclass
class CategoryDefinition:
    """
    Complete definition of a PARA category including its criteria and patterns.
    
    This class encapsulates all the information needed to identify and
    categorize files according to the PARA methodology.
    """
    
    name: PARACategory
    description: str
    criteria: List[str]
    examples: List[str]
    keywords: List[str]
    patterns: List[str]
    confidence_threshold: float = 0.75
    auto_categorize: bool = True
    
    def __post_init__(self) -> None:
        """Validate the category definition."""
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        
        if not self.criteria:
            raise ValueError("criteria list cannot be empty")
    
    def matches_keyword(self, text: str) -> bool:
        """Check if text contains any of the category keywords."""
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.keywords)
    
    def matches_pattern(self, filename: str) -> bool:
        """Check if filename matches any of the category patterns."""
        from fnmatch import fnmatch
        filename_lower = filename.lower()
        return any(fnmatch(filename_lower, pattern.lower()) for pattern in self.patterns)


@dataclass
class CategorizationResult:
    """
    Result of PARA categorization for a file.
    
    Contains the determined category, confidence score, reasoning,
    and alternative possibilities.
    """
    
    file_path: Path
    category: PARACategory
    confidence: float
    reasons: List[str]
    alternative_categories: Dict[PARACategory, float] = field(default_factory=dict)
    applied_rules: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate the categorization result."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        
        if not self.reasons:
            raise ValueError("reasons list cannot be empty")
        
        # Ensure file_path is a Path object
        if not isinstance(self.file_path, Path):
            self.file_path = Path(self.file_path)
    
    @property
    def is_confident(self) -> bool:
        """Check if categorization confidence exceeds the default threshold."""
        return self.confidence >= 0.75
    
    @property
    def requires_review(self) -> bool:
        """Check if categorization requires manual review."""
        return self.confidence < 0.60
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the result to a dictionary."""
        return {
            "file_path": str(self.file_path),
            "category": self.category.value,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "alternative_categories": {
                cat.value: score 
                for cat, score in self.alternative_categories.items()
            },
            "applied_rules": self.applied_rules,
            "metadata": self.metadata,
            "is_confident": self.is_confident,
            "requires_review": self.requires_review
        }


# Standard category definitions following PARA methodology
CATEGORY_DEFINITIONS: Dict[PARACategory, CategoryDefinition] = {
    PARACategory.PROJECT: CategoryDefinition(
        name=PARACategory.PROJECT,
        description=(
            "Projects are short-term efforts with specific goals and deadlines. "
            "They have clear completion criteria and are actively worked on. "
            "When completed, they move to Archive."
        ),
        criteria=[
            "Has a specific, defined goal or outcome",
            "Has a deadline or target completion date",
            "Requires multiple steps or tasks to complete",
            "Is actively being worked on",
            "Will be finished at some point in time"
        ],
        examples=[
            "Website redesign project",
            "Book writing project",
            "Client proposal",
            "Product launch plan",
            "Marketing campaign",
            "Research paper"
        ],
        keywords=[
            "deadline", "milestone", "deliverable", "sprint", "goal",
            "project plan", "due date", "completion", "task list",
            "proposal", "campaign", "launch", "initiative"
        ],
        patterns=[
            "project-*", "*-proposal", "*-plan", "*-campaign",
            "*-initiative", "sprint-*", "*-deliverable"
        ],
        confidence_threshold=0.75,
        auto_categorize=True
    ),
    
    PARACategory.AREA: CategoryDefinition(
        name=PARACategory.AREA,
        description=(
            "Areas are ongoing responsibilities that require continuous maintenance. "
            "They have no end date and represent parts of life or work that need "
            "regular attention. Unlike projects, areas are never 'completed'."
        ),
        criteria=[
            "Is an ongoing responsibility or commitment",
            "Requires regular attention and maintenance",
            "Has no defined endpoint or completion date",
            "Represents a standard or quality to maintain",
            "Contains recurring tasks or processes"
        ],
        examples=[
            "Health and fitness tracking",
            "Financial management",
            "Team management",
            "Customer relationships",
            "Home maintenance",
            "Professional development"
        ],
        keywords=[
            "ongoing", "maintenance", "routine", "checklist", "regular",
            "continuous", "process", "standard", "recurring", "daily",
            "weekly", "monthly", "management", "operations", "relationship"
        ],
        patterns=[
            "routine-*", "*-checklist", "*-maintenance", "*-management",
            "*-operations", "*-tracking", "daily-*", "weekly-*"
        ],
        confidence_threshold=0.75,
        auto_categorize=True
    ),
    
    PARACategory.RESOURCE: CategoryDefinition(
        name=PARACategory.RESOURCE,
        description=(
            "Resources are reference materials, research, or knowledge that may "
            "be useful in the future. They are informational rather than actionable "
            "and are accessed on an as-needed basis."
        ),
        criteria=[
            "Is primarily informational or reference material",
            "May be useful in the future but not immediately needed",
            "Contains knowledge, research, or learning materials",
            "Is accessed occasionally rather than regularly",
            "Has value as a reference or template"
        ],
        examples=[
            "Technical documentation",
            "Research papers and articles",
            "Tutorials and how-to guides",
            "Templates and examples",
            "Industry reports",
            "Learning materials"
        ],
        keywords=[
            "reference", "tutorial", "guide", "template", "documentation",
            "how-to", "example", "learning", "research", "article",
            "manual", "handbook", "resource", "knowledge", "info"
        ],
        patterns=[
            "ref-*", "*-guide", "*-template", "*-tutorial", "*-docs",
            "*-manual", "*-handbook", "example-*", "sample-*"
        ],
        confidence_threshold=0.80,
        auto_categorize=True
    ),
    
    PARACategory.ARCHIVE: CategoryDefinition(
        name=PARACategory.ARCHIVE,
        description=(
            "Archive contains inactive items from the other three categories. "
            "Projects that are completed, areas that are no longer relevant, "
            "and resources that are outdated all move to Archive."
        ),
        criteria=[
            "Was previously in Project, Area, or Resource",
            "Is no longer active or relevant",
            "Has been completed or abandoned",
            "Is kept for historical reference",
            "Is not expected to be accessed frequently"
        ],
        examples=[
            "Completed projects",
            "Old versions of documents",
            "Deprecated processes",
            "Historical records",
            "Obsolete information",
            "Past year's files"
        ],
        keywords=[
            "final", "completed", "archived", "old", "legacy",
            "deprecated", "obsolete", "historical", "past",
            "inactive", "finished", "done", "closed", "ended"
        ],
        patterns=[
            "*-final", "*-archived", "*-old", "*-deprecated",
            "*-legacy", "*-obsolete", "archive-*", "old-*",
            "*-v1", "*-v2", "*-backup"
        ],
        confidence_threshold=0.90,
        auto_categorize=False  # Require manual confirmation for archival
    )
}


def get_category_definition(category: PARACategory) -> CategoryDefinition:
    """
    Get the standard definition for a PARA category.
    
    Args:
        category: The PARA category
        
    Returns:
        The category definition
        
    Raises:
        KeyError: If category is not defined
    """
    return CATEGORY_DEFINITIONS[category]


def get_all_category_definitions() -> Dict[PARACategory, CategoryDefinition]:
    """
    Get all standard PARA category definitions.
    
    Returns:
        Dictionary mapping categories to their definitions
    """
    return CATEGORY_DEFINITIONS.copy()