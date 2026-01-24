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

Based on the Johnny Decimal system by Johnny Noble (johnnydecimal.com).

Author: File Organizer v2.0
License: MIT
"""

from .categories import (
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalNumber,
    NumberingResult,
    NumberingScheme,
    NumberLevel,
    get_default_scheme,
)

from .numbering import (
    JohnnyDecimalGenerator,
    NumberConflictError,
    InvalidNumberError,
)

from .system import (
    JohnnyDecimalSystem,
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
    # Exceptions
    "NumberConflictError",
    "InvalidNumberError",
    # Utilities
    "get_default_scheme",
]

__version__ = "1.0.0"
