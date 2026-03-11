"""Protocol definitions for storage and caching contracts.

Defines structural interfaces for model caches and generic key-value
storage backends.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class CacheProtocol(Protocol):
    """Structural contract for model/object caches.

    Implementations provide get-or-load semantics with a loader callable
    and expose usage statistics.
    """

    def get_or_load(
        self,
        key: str,
        loader: Callable[[], Any],
    ) -> Any:
        """Return cached value for *key*, or call *loader* to populate it."""
        ...

    def stats(self) -> Any:
        """Return cache usage statistics."""
        ...


@runtime_checkable
class StorageProtocol(Protocol):
    """Structural contract for persistent key-value storage.

    Implementations provide basic CRUD operations for storing and
    retrieving serializable data.
    """

    def get(self, key: str) -> Any | None:
        """Retrieve the value for *key*, or ``None`` if absent."""
        ...

    def put(self, key: str, value: Any) -> None:
        """Store *value* under *key*."""
        ...

    def delete(self, key: str) -> bool:
        """Remove *key* and return whether it existed."""
        ...

    def exists(self, key: str) -> bool:
        """Return whether *key* is present in storage."""
        ...
