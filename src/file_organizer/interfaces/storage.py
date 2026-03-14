"""Protocol definitions for storage and caching contracts.

Defines structural interfaces for model caches and generic key-value
storage backends.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")

#: Sentinel used by :meth:`StorageProtocol.get` to distinguish a stored
#: ``None`` value from a missing key.
MISSING: Final[object] = object()


@runtime_checkable
class CacheProtocol(Protocol):
    """Structural contract for model/object caches.

    Implementations provide get-or-load semantics with a loader callable
    and expose usage statistics.
    """

    def get_or_load(
        self,
        key: str,
        /,
        loader: Callable[[], Any],
    ) -> Any:
        """Return cached value for *key*, or call *loader* to populate it.

        *key* is positional-only to match the ``ModelCache`` implementation
        and prevent callers from passing it as a keyword argument.
        """
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

    def get(self, key: str, default: Any = MISSING) -> Any:
        """Retrieve the value for *key*.

        Returns *default* if *key* is absent.  When *default* is omitted the
        module-level :data:`MISSING` sentinel is returned on a miss, allowing
        callers to distinguish a stored ``None`` from an absent key::

            value = storage.get("my_key")
            if value is MISSING:
                # key not present
                ...
        """
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
