"""
PARA Methodology Implementation

The PARA method is a universal system for organizing digital information and life.
PARA stands for Projects, Areas, Resources, and Archive.

Components:
- categories: Core PARA category definitions and data models
- models: Data structures for categorization results
- interfaces: Abstract interfaces for rule engines and heuristics

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

__all__ = [
    "PARACategory",
    "CategoryDefinition",
    "CategorizationResult",
    "get_category_definition",
    "get_all_category_definitions",
]

__version__ = "1.0.0"
