"""Core file organization functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from file_organizer.core.organizer import FileOrganizer, OrganizationResult

__all__ = [
    "FileOrganizer",
    "OrganizationResult",
]

# Names re-exported lazily from file_organizer.core.organizer.
_LAZY_EXPORTS = frozenset(__all__)


def __getattr__(name: str) -> Any:
    """Lazily import the heavy ``organizer`` submodule on first access (PEP 562).

    Importing ``file_organizer.core.organizer`` at package-init time pulls in
    the audio services stack (``ctranslate2`` → ``torch``). That made even a
    trivial ``import file_organizer.core.path_guard`` drag in torch — slow, and
    the trigger for a coverage-instrumentation segfault when a dotted
    ``--cov``/``--source`` target resolved through this package. Deferring the
    import keeps lightweight ``file_organizer.core.*`` modules torch-free while
    preserving the ``from file_organizer.core import FileOrganizer`` public API.
    """
    if name in _LAZY_EXPORTS:
        from file_organizer.core import organizer

        # Cache on the package so subsequent lookups skip __getattr__ entirely.
        value = getattr(organizer, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Include the lazily-exported names in ``dir()`` for discoverability."""
    return sorted(set(globals()) | _LAZY_EXPORTS)
