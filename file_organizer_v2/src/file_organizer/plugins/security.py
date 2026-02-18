"""Plugin sandbox policy primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from file_organizer.plugins.errors import PluginPermissionError


def _normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


@dataclass(frozen=True)
class PluginSecurityPolicy:
    """Sandbox policy used by plugin runtime checks."""

    allowed_paths: frozenset[Path] = field(default_factory=frozenset)
    allowed_operations: frozenset[str] = field(default_factory=frozenset)
    allow_all_paths: bool = False
    allow_all_operations: bool = False

    @classmethod
    def unrestricted(cls) -> PluginSecurityPolicy:
        """Create a fully permissive policy."""
        return cls(allow_all_paths=True, allow_all_operations=True)

    @classmethod
    def from_permissions(
        cls,
        *,
        allowed_paths: Iterable[str | Path] = (),
        allowed_operations: Iterable[str] = (),
        allow_all_paths: bool = False,
        allow_all_operations: bool = False,
    ) -> PluginSecurityPolicy:
        """Create a policy from user permissions/config values."""
        normalized_paths = frozenset(_normalize_path(path) for path in allowed_paths)
        normalized_operations = frozenset(
            operation.strip().lower() for operation in allowed_operations
        )
        return cls(
            allowed_paths=normalized_paths,
            allowed_operations=normalized_operations,
            allow_all_paths=allow_all_paths,
            allow_all_operations=allow_all_operations,
        )


class PluginSandbox:
    """Runtime policy checker for plugin capabilities."""

    def __init__(
        self,
        plugin_name: str,
        policy: PluginSecurityPolicy | None = None,
    ) -> None:
        self.plugin_name = plugin_name
        self.policy = policy or PluginSecurityPolicy.unrestricted()

    def validate_file_access(self, path: str | Path) -> bool:
        """Return whether the plugin may access the provided path."""
        if self.policy.allow_all_paths:
            return True
        if not self.policy.allowed_paths:
            return False
        candidate = _normalize_path(path)
        return any(
            candidate == root or candidate.is_relative_to(root)
            for root in self.policy.allowed_paths
        )

    def validate_operation(self, operation: str) -> bool:
        """Return whether the plugin may execute the provided operation."""
        if self.policy.allow_all_operations:
            return True
        normalized = operation.strip().lower()
        return normalized in self.policy.allowed_operations

    def require_file_access(self, path: str | Path) -> None:
        """Raise an error when file access is denied by policy."""
        if not self.validate_file_access(path):
            raise PluginPermissionError(
                f"Plugin '{self.plugin_name}' cannot access path: {Path(path)}"
            )

    def require_operation(self, operation: str) -> None:
        """Raise an error when operation execution is denied by policy."""
        if not self.validate_operation(operation):
            raise PluginPermissionError(
                f"Plugin '{self.plugin_name}' cannot execute operation: {operation}"
            )
