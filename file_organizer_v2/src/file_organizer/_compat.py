"""
Backward compatibility module for Python 3.9+ support.

Provides polyfills and compatibility utilities for features introduced in
newer Python versions, ensuring the codebase runs on Python 3.9 through 3.14+.

Compatibility features:
- StrEnum (Python 3.11+): String-valued enum backport
- Runtime version checks: Utilities for version-dependent behavior
- Type hint compatibility: Guidance on using `from __future__ import annotations`
"""

from __future__ import annotations

import sys
from datetime import timezone
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Version constants for feature detection
# ---------------------------------------------------------------------------

PY_VERSION: tuple[int, int] = sys.version_info[:2]
HAS_STRENUM: bool = PY_VERSION >= (3, 11)
HAS_UNION_TYPE: bool = PY_VERSION >= (3, 10)  # X | Y syntax at runtime
HAS_MATCH_STATEMENT: bool = PY_VERSION >= (3, 10)
HAS_EXCEPTION_GROUPS: bool = PY_VERSION >= (3, 11)
HAS_DATETIME_UTC: bool = PY_VERSION >= (3, 11)

# ---------------------------------------------------------------------------
# StrEnum backport
# ---------------------------------------------------------------------------

if HAS_STRENUM:
    from enum import StrEnum
else:

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """
        Backport of StrEnum for Python < 3.11.

        Provides string-valued enum members that behave like both str and Enum.
        Members can be compared directly with strings and used in string
        operations (formatting, concatenation, etc.).

        Example::

            class Color(StrEnum):
                RED = "red"
                GREEN = "green"

            assert Color.RED == "red"
            assert f"color is {Color.RED}" == "color is red"
        """

        def __new__(cls, value: str, *args: Any, **kwargs: Any) -> StrEnum:
            if not isinstance(value, str):
                raise TypeError(f"Values for StrEnum must be strings, got {type(value)!r}")
            member = str.__new__(cls, value)
            member._value_ = value
            return member

        def __str__(self) -> str:
            """Return the string value, not 'ClassName.MEMBER'."""
            return self.value

        def __repr__(self) -> str:
            return f"{self.__class__.__name__}.{self.name}"

        def __format__(self, format_spec: str) -> str:
            """Support string formatting."""
            return str.__format__(self.value, format_spec)

        def __hash__(self) -> int:
            """Hash based on the string value for dict/set compatibility."""
            return str.__hash__(self.value)

        def __eq__(self, other: object) -> bool:
            """Allow comparison with plain strings."""
            if isinstance(other, str):
                return self.value == other
            return NotImplemented

        @staticmethod
        def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str:
            """Generate lowercase name when auto() is used."""
            return name.lower()


# ---------------------------------------------------------------------------
# Timezone compatibility
# ---------------------------------------------------------------------------

# Python 3.11 introduced datetime.UTC as an alias for datetime.timezone.utc.
# For 3.9+ compatibility, always use datetime.timezone.utc or this constant.
UTC = timezone.utc


# ---------------------------------------------------------------------------
# isinstance() compatibility helper
# ---------------------------------------------------------------------------


def check_type(obj: object, types: tuple[type, ...]) -> bool:
    """
    Version-safe isinstance() check.

    In Python 3.10+, ``isinstance(x, int | str)`` is valid syntax, but
    this does not work in 3.9. This helper ensures we always use the
    tuple form which is compatible across all supported versions.

    Args:
        obj: The object to check.
        types: A tuple of types to check against.

    Returns:
        True if obj is an instance of any of the given types.
    """
    return isinstance(obj, types)


__all__ = [
    "StrEnum",
    "UTC",
    "PY_VERSION",
    "HAS_STRENUM",
    "HAS_UNION_TYPE",
    "HAS_MATCH_STATEMENT",
    "HAS_EXCEPTION_GROUPS",
    "HAS_DATETIME_UTC",
    "check_type",
]
