"""Minimal plugin security policy for subprocess sandbox enforcement.

This module is intentionally kept simple.  Its sole purpose is to carry the
policy fields that are serialised as a plain dict and sent to the worker
child process via JSON on start-up.

All runtime policy *checking* is performed inside the worker process itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


@dataclass(frozen=True)
class PluginSecurityPolicy:
    """Sandbox policy consumed by :class:`~file_organizer.plugins.executor.PluginExecutor`.

    Attributes:
        allowed_paths: Set of filesystem paths the plugin may access.
        allowed_operations: Set of named operations the plugin may invoke.
        allow_all_paths: When ``True``, all path access is permitted.
        allow_all_operations: When ``True``, all operations are permitted.
    """

    allowed_paths: frozenset[Path] = field(default_factory=frozenset)
    allowed_operations: frozenset[str] = field(default_factory=frozenset)
    allow_all_paths: bool = False
    allow_all_operations: bool = False

    @classmethod
    def unrestricted(cls) -> PluginSecurityPolicy:
        """Return a fully permissive policy.

        Returns:
            A :class:`PluginSecurityPolicy` with all access granted.
        """
        return cls(allow_all_paths=True, allow_all_operations=True)

    @classmethod
    def from_permissions(
        cls,
        *,
        allowed_paths: list[str | Path] | tuple[str | Path, ...] = (),
        allowed_operations: list[str] | tuple[str, ...] = (),
        allow_all_paths: bool = False,
        allow_all_operations: bool = False,
    ) -> PluginSecurityPolicy:
        """Construct a policy from user-supplied permission values.

        Args:
            allowed_paths: Filesystem paths the plugin is allowed to access.
            allowed_operations: Named operations the plugin is allowed to use.
            allow_all_paths: Grant unrestricted filesystem access.
            allow_all_operations: Grant all named operations.

        Returns:
            A new :class:`PluginSecurityPolicy` instance.
        """
        normalised_paths = frozenset(_normalize_path(p) for p in allowed_paths)
        normalised_ops = frozenset(op.strip().lower() for op in allowed_operations)
        return cls(
            allowed_paths=normalised_paths,
            allowed_operations=normalised_ops,
            allow_all_paths=allow_all_paths,
            allow_all_operations=allow_all_operations,
        )
