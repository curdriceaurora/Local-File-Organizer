"""Transport-neutral capability registry contracts.

The registry records product intent and current evidence without importing any
presentation framework.  Consumers such as conformance tests and documentation
generators should load :func:`get_capability_registry` instead of maintaining a
surface-specific capability list.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, TypeVar

from file_organizer._compat import StrEnum

CAPABILITY_REGISTRY_SCHEMA_VERSION = 1
_EnumT = TypeVar("_EnumT", bound=StrEnum)


class Surface(StrEnum):
    """Public product surfaces governed by the parity program."""

    CLI = "cli"
    REST_API = "rest-api"
    PYTHON_SDK = "python-sdk"
    TYPESCRIPT_SDK = "typescript-sdk"
    WEB_DESKTOP = "web-desktop"
    TUI = "tui"


class SupportLevel(StrEnum):
    """The intended support level for a capability on a surface."""

    FULL = "full"
    READ_ONLY = "read-only"
    REDIRECT_DEEP_LINK = "redirect/deep-link"
    NOT_APPLICABLE = "not-applicable"


class ImplementationStatus(StrEnum):
    """Whether the intended adapter behavior currently exists."""

    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    NOT_IMPLEMENTED = "not-implemented"
    NOT_APPLICABLE = "not-applicable"


class ConformanceStatus(StrEnum):
    """Whether executable parity evidence currently exists."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not-applicable"


class CapabilityMaturity(StrEnum):
    """Product maturity of a capability independent of surface support."""

    EXPERIMENTAL = "experimental"
    BETA = "beta"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class ExecutionScope(StrEnum):
    """Available execution modes or access boundaries for a capability."""

    LOCAL_ONLY = "local-only"
    REMOTE = "remote"
    AUTH_GATED = "auth-gated"


class Platform(StrEnum):
    """Platforms on which a capability is intended to be available."""

    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"


class CapabilityRegistryError(ValueError):
    """Raised when registry data violates the capability contract."""


@dataclass(frozen=True, slots=True)
class SurfaceCapabilityStatus:
    """Intent, implementation, and evidence for one capability surface."""

    surface: Surface
    target_support: SupportLevel
    implementation_status: ImplementationStatus
    conformance_status: ConformanceStatus
    entry_points: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, surface: Surface, data: Mapping[str, Any]) -> SurfaceCapabilityStatus:
        """Parse one serialized surface status."""
        return cls(
            surface=surface,
            target_support=_enum_value(SupportLevel, data, "target_support"),
            implementation_status=_enum_value(ImplementationStatus, data, "implementation_status"),
            conformance_status=_enum_value(ConformanceStatus, data, "conformance_status"),
            entry_points=_string_tuple(data.get("entry_points", ()), "entry_points"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""
        return {
            "target_support": self.target_support.value,
            "implementation_status": self.implementation_status.value,
            "conformance_status": self.conformance_status.value,
            "entry_points": list(self.entry_points),
        }


@dataclass(frozen=True, slots=True)
class Capability:
    """A stable product capability and its cross-surface support decisions."""

    capability_id: str
    name: str
    description: str
    maturity: CapabilityMaturity
    execution_scopes: tuple[ExecutionScope, ...]
    surfaces: tuple[SurfaceCapabilityStatus, ...]
    optional_dependencies: tuple[str, ...] = ()
    platforms: tuple[Platform, ...] = tuple(Platform)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Capability:
        """Parse one serialized capability."""
        raw_surfaces = data.get("surfaces")
        if not isinstance(raw_surfaces, Mapping):
            raise CapabilityRegistryError("capability surfaces must be an object")
        expected_surface_names = {surface.value for surface in Surface}
        if not all(isinstance(key, str) for key in raw_surfaces):
            raise CapabilityRegistryError("capability surface names must be strings")
        declared_surface_names = set(raw_surfaces)
        if declared_surface_names != expected_surface_names:
            missing = ", ".join(sorted(expected_surface_names - declared_surface_names)) or "none"
            extra = ", ".join(sorted(declared_surface_names - expected_surface_names)) or "none"
            raise CapabilityRegistryError(
                f"capability surfaces are incomplete (missing: {missing}; extra: {extra})"
            )
        if not all(isinstance(value, Mapping) for value in raw_surfaces.values()):
            raise CapabilityRegistryError("each capability surface must be an object")
        raw_scopes = data.get("execution_scopes")
        if not isinstance(raw_scopes, Sequence) or isinstance(raw_scopes, (str, bytes)):
            raise CapabilityRegistryError("execution_scopes must be a list")
        raw_platforms = data.get("platforms", [platform.value for platform in Platform])
        if not isinstance(raw_platforms, Sequence) or isinstance(raw_platforms, (str, bytes)):
            raise CapabilityRegistryError("platforms must be a list")
        try:
            return cls(
                capability_id=_required_string(data, "id"),
                name=_required_string(data, "name"),
                description=_required_string(data, "description"),
                maturity=_enum_value(CapabilityMaturity, data, "maturity"),
                execution_scopes=tuple(ExecutionScope(value) for value in raw_scopes),
                surfaces=tuple(
                    SurfaceCapabilityStatus.from_dict(surface, raw_surfaces[surface.value])
                    for surface in Surface
                    if surface.value in raw_surfaces
                ),
                optional_dependencies=_string_tuple(
                    data.get("optional_dependencies", ()), "optional_dependencies"
                ),
                platforms=tuple(Platform(value) for value in raw_platforms),
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, CapabilityRegistryError):
                raise
            raise CapabilityRegistryError(str(exc)) from exc

    def support_for(self, surface: Surface) -> SurfaceCapabilityStatus:
        """Return the declared status for ``surface``."""
        for status in self.surfaces:
            if status.surface is surface:
                return status
        raise CapabilityRegistryError(
            f"capability {self.capability_id!r} does not declare surface {surface.value!r}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""
        return {
            "id": self.capability_id,
            "name": self.name,
            "description": self.description,
            "maturity": self.maturity.value,
            "execution_scopes": [scope.value for scope in self.execution_scopes],
            "optional_dependencies": list(self.optional_dependencies),
            "platforms": [platform.value for platform in self.platforms],
            "surfaces": {
                status.surface.value: status.to_dict()
                for status in sorted(self.surfaces, key=lambda item: item.surface.value)
            },
        }


@dataclass(frozen=True, slots=True)
class CapabilityRegistry:
    """Validated collection of product capabilities."""

    schema_version: int
    capabilities: tuple[Capability, ...]

    def __post_init__(self) -> None:
        """Reject invalid state as soon as a registry is constructed."""
        _validate_registry(self)
        object.__setattr__(
            self,
            "capabilities",
            tuple(sorted(self.capabilities, key=lambda item: item.capability_id)),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CapabilityRegistry:
        """Parse and validate serialized registry data."""
        schema_version = data.get("schema_version")
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise CapabilityRegistryError("schema_version must be an integer")
        raw_capabilities = data.get("capabilities")
        if not isinstance(raw_capabilities, Sequence) or isinstance(raw_capabilities, (str, bytes)):
            raise CapabilityRegistryError("capabilities must be a list")
        if not all(isinstance(item, Mapping) for item in raw_capabilities):
            raise CapabilityRegistryError("each capability must be an object")
        return cls(
            schema_version=schema_version,
            capabilities=tuple(Capability.from_dict(item) for item in raw_capabilities),
        )

    @classmethod
    def from_json(cls, content: str) -> CapabilityRegistry:
        """Parse and validate a serialized JSON registry."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise CapabilityRegistryError(f"invalid registry JSON: {exc}") from exc
        if not isinstance(data, Mapping):
            raise CapabilityRegistryError("registry root must be an object")
        return cls.from_dict(data)

    def get(self, capability_id: str) -> Capability:
        """Return a capability by stable ID."""
        for capability in self.capabilities:
            if capability.capability_id == capability_id:
                return capability
        raise KeyError(capability_id)

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministically ordered JSON-compatible representation."""
        return {
            "schema_version": self.schema_version,
            "surfaces": [surface.value for surface in Surface],
            "capabilities": [
                capability.to_dict()
                for capability in sorted(self.capabilities, key=lambda item: item.capability_id)
            ],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the registry deterministically for tests and generators."""
        separators = (",", ":") if indent is None else None
        return (
            json.dumps(self.to_dict(), indent=indent, sort_keys=True, separators=separators) + "\n"
        )


def get_capability_registry() -> CapabilityRegistry:
    """Load the packaged canonical capability registry."""
    resource = files("file_organizer.core").joinpath("capability_registry.json")
    return CapabilityRegistry.from_json(resource.read_text(encoding="utf-8"))


def _validate_registry(registry: CapabilityRegistry) -> None:
    """Validate registry-level invariants and each capability."""
    if registry.schema_version != CAPABILITY_REGISTRY_SCHEMA_VERSION:
        raise CapabilityRegistryError(
            "unsupported capability registry schema version "
            f"{registry.schema_version}; expected {CAPABILITY_REGISTRY_SCHEMA_VERSION}"
        )
    if not registry.capabilities:
        raise CapabilityRegistryError("registry must contain at least one capability")

    seen_ids: set[str] = set()
    for capability in registry.capabilities:
        _validate_capability(capability)
        if capability.capability_id in seen_ids:
            raise CapabilityRegistryError(f"duplicate capability ID: {capability.capability_id}")
        seen_ids.add(capability.capability_id)


_CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$")


def _validate_capability(capability: Capability) -> None:
    """Validate identifiers, metadata, scopes, and the complete surface matrix."""
    prefix = f"capability {capability.capability_id!r}"
    if not _CAPABILITY_ID_PATTERN.fullmatch(capability.capability_id):
        raise CapabilityRegistryError(f"{prefix} has an invalid stable ID")
    if not capability.name.strip() or not capability.description.strip():
        raise CapabilityRegistryError(f"{prefix} must have a name and description")
    if not capability.execution_scopes:
        raise CapabilityRegistryError(f"{prefix} must declare at least one execution scope")
    if len(set(capability.execution_scopes)) != len(capability.execution_scopes):
        raise CapabilityRegistryError(f"{prefix} has duplicate execution scopes")
    if (
        ExecutionScope.AUTH_GATED in capability.execution_scopes
        and ExecutionScope.REMOTE not in capability.execution_scopes
    ):
        raise CapabilityRegistryError(f"{prefix} cannot be auth-gated without remote execution")
    if not capability.platforms or len(set(capability.platforms)) != len(capability.platforms):
        raise CapabilityRegistryError(f"{prefix} must declare unique supported platforms")
    if len(set(capability.optional_dependencies)) != len(capability.optional_dependencies) or any(
        not dependency.strip() for dependency in capability.optional_dependencies
    ):
        raise CapabilityRegistryError(f"{prefix} has invalid or duplicate optional dependencies")

    declared_surfaces = [status.surface for status in capability.surfaces]
    if len(set(declared_surfaces)) != len(declared_surfaces):
        raise CapabilityRegistryError(f"{prefix} declares a surface more than once")
    missing = set(Surface) - set(declared_surfaces)
    extra = set(declared_surfaces) - set(Surface)
    if missing or extra:
        missing_names = ", ".join(sorted(item.value for item in missing)) or "none"
        extra_names = ", ".join(sorted(item.value for item in extra)) or "none"
        raise CapabilityRegistryError(
            f"{prefix} has an incomplete surface matrix (missing: {missing_names}; extra: {extra_names})"
        )

    for status in capability.surfaces:
        _validate_surface_status(capability.capability_id, status)


def _validate_surface_status(capability_id: str, status: SurfaceCapabilityStatus) -> None:
    """Validate one surface decision and its implementation evidence."""
    prefix = f"capability {capability_id!r} surface {status.surface.value!r}"
    target_is_na = status.target_support is SupportLevel.NOT_APPLICABLE
    implementation_is_na = status.implementation_status is ImplementationStatus.NOT_APPLICABLE
    conformance_is_na = status.conformance_status is ConformanceStatus.NOT_APPLICABLE
    if len(set(status.entry_points)) != len(status.entry_points) or any(
        not entry.strip() for entry in status.entry_points
    ):
        raise CapabilityRegistryError(f"{prefix} has invalid or duplicate entry points")
    if target_is_na:
        if not implementation_is_na or not conformance_is_na or status.entry_points:
            raise CapabilityRegistryError(
                f"{prefix} is not-applicable and cannot have implementation evidence"
            )
        return
    if implementation_is_na or conformance_is_na:
        raise CapabilityRegistryError(
            f"{prefix} has applicable target support but a not-applicable status"
        )
    if status.implementation_status is ImplementationStatus.NOT_IMPLEMENTED:
        if status.entry_points:
            raise CapabilityRegistryError(f"{prefix} is not implemented but declares entry points")
    elif not status.entry_points:
        raise CapabilityRegistryError(f"{prefix} is implemented but has no entry point evidence")
    if (
        status.conformance_status is ConformanceStatus.VERIFIED
        and status.implementation_status is not ImplementationStatus.IMPLEMENTED
    ):
        raise CapabilityRegistryError(
            f"{prefix} cannot be verified until implementation is complete"
        )


def _required_string(data: Mapping[str, Any], key: str) -> str:
    """Read a required non-empty string from serialized data."""
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CapabilityRegistryError(f"{key} must be a non-empty string")
    return value


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    """Convert a serialized string list to an immutable tuple."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise CapabilityRegistryError(f"{field} must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise CapabilityRegistryError(f"{field} must be a list of strings")
    return tuple(value)


def _enum_value(enum_type: type[_EnumT], data: Mapping[str, Any], key: str) -> _EnumT:
    """Read and validate one string enum value from serialized data."""
    value = data.get(key)
    if not isinstance(value, str):
        allowed = ", ".join(item.value for item in enum_type)
        raise CapabilityRegistryError(f"{key} must be one of: {allowed}")
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise CapabilityRegistryError(f"{key} must be one of: {allowed}") from exc


__all__ = [
    "CAPABILITY_REGISTRY_SCHEMA_VERSION",
    "Capability",
    "CapabilityMaturity",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "ConformanceStatus",
    "ExecutionScope",
    "ImplementationStatus",
    "Platform",
    "SupportLevel",
    "Surface",
    "SurfaceCapabilityStatus",
    "get_capability_registry",
]
