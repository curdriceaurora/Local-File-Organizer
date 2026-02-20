"""
Compatibility shim module.

Provides re-exports used across the codebase for consistent imports.
Requires Python 3.11+.
"""

from __future__ import annotations

from datetime import UTC
from enum import StrEnum

__all__ = [
    "StrEnum",
    "UTC",
]
