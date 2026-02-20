"""
Backward compatibility module.

Provides shared aliases used across the codebase.
"""

from __future__ import annotations

from datetime import timezone
from enum import StrEnum

# ---------------------------------------------------------------------------
# Timezone alias
# ---------------------------------------------------------------------------

UTC = timezone.utc

__all__ = [
    "StrEnum",
    "UTC",
]
