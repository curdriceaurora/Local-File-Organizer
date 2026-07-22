"""Tests for the canonical cross-surface capability registry."""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from typing import cast

import pytest

from file_organizer.client.async_client import AsyncFileOrganizerClient
from file_organizer.client.endpoint_spec import PUBLIC_ENDPOINTS
from file_organizer.client.sync_client import FileOrganizerClient
from file_organizer.core.capabilities import (
    CapabilityRegistry,
    CapabilityRegistryError,
    ConformanceStatus,
    ImplementationStatus,
    Surface,
    get_capability_registry,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def _registry_data() -> dict[str, object]:
    registry = get_capability_registry()
    return copy.deepcopy(registry.to_dict())


def test_packaged_registry_is_complete_and_queryable() -> None:
    registry = get_capability_registry()

    assert len(registry.capabilities) >= 30
    assert registry.get("organization.execute").name == "Organization execution"
    for capability in registry.capabilities:
        assert {status.surface for status in capability.surfaces} == set(Surface)


def test_packaged_registry_loader_is_cached() -> None:
    """Runtime consumers reuse the immutable parsed registry."""
    assert get_capability_registry() is get_capability_registry()


def test_organization_conformance_matches_exercised_corpus_scope() -> None:
    registry = get_capability_registry()

    for capability_id in ("organization.scan", "organization.preview"):
        capability = registry.get(capability_id)
        assert (
            capability.support_for(Surface.REST_API).conformance_status
            is ConformanceStatus.VERIFIED
        )
        assert (
            capability.support_for(Surface.PYTHON_SDK).conformance_status
            is ConformanceStatus.VERIFIED
        )

    for capability_id in ("organization.execute", "organization.suggest"):
        capability = registry.get(capability_id)
        assert (
            capability.support_for(Surface.REST_API).conformance_status
            is ConformanceStatus.UNVERIFIED
        )
        assert (
            capability.support_for(Surface.PYTHON_SDK).conformance_status
            is ConformanceStatus.UNVERIFIED
        )


def test_target_implementation_and_conformance_are_independent() -> None:
    registry = get_capability_registry()
    planned = registry.get("deduplication.manage").support_for(Surface.WEB_DESKTOP)

    assert planned.target_support.value == "full"
    assert planned.implementation_status is ImplementationStatus.NOT_IMPLEMENTED
    assert planned.conformance_status is ConformanceStatus.UNVERIFIED


def test_serialization_is_deterministic_and_round_trips() -> None:
    registry = get_capability_registry()
    serialized = registry.to_json()

    assert CapabilityRegistry.from_json(serialized) == registry
    assert CapabilityRegistry.from_dict(registry.to_dict()).to_json() == serialized
    ids = [item["id"] for item in json.loads(serialized)["capabilities"]]
    assert ids == sorted(ids)


def test_packaged_registry_uses_canonical_serialization() -> None:
    registry_path = Path("src") / "file_organizer" / "core" / "capability_registry.json"

    assert registry_path.read_text(encoding="utf-8") == get_capability_registry().to_json()


def test_duplicate_capability_ids_are_rejected() -> None:
    data = _registry_data()
    capabilities = cast(list[dict[str, object]], data["capabilities"])
    capabilities.append(copy.deepcopy(capabilities[0]))

    with pytest.raises(CapabilityRegistryError, match="duplicate capability ID"):
        CapabilityRegistry.from_dict(data)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("{", "invalid registry JSON"),
        ("[]", "registry root must be an object"),
        ('{"schema_version": true, "capabilities": []}', "schema_version must be an integer"),
        ('{"schema_version": 1, "capabilities": {}}', "capabilities must be a list"),
        ('{"schema_version": 1, "capabilities": [1]}', "each capability must be an object"),
    ],
)
def test_malformed_registry_payload_is_rejected(payload: str, message: str) -> None:
    with pytest.raises(CapabilityRegistryError, match=message):
        CapabilityRegistry.from_json(payload)


def test_unsupported_or_empty_registry_is_rejected() -> None:
    data = _registry_data()
    data["schema_version"] = 999
    with pytest.raises(CapabilityRegistryError, match="unsupported capability registry schema"):
        CapabilityRegistry.from_dict(data)

    data["schema_version"] = 1
    data["capabilities"] = []
    with pytest.raises(CapabilityRegistryError, match="at least one capability"):
        CapabilityRegistry.from_dict(data)


def test_missing_surface_is_rejected() -> None:
    data = _registry_data()
    capability = data["capabilities"][0]  # type: ignore[index]
    del capability["surfaces"][Surface.TUI.value]

    with pytest.raises(CapabilityRegistryError, match="surfaces are incomplete"):
        CapabilityRegistry.from_dict(data)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "INVALID", "invalid stable ID"),
        ("execution_scopes", [], "at least one execution scope"),
        ("execution_scopes", ["local-only", "local-only"], "duplicate execution scopes"),
        ("platforms", [], "unique supported platforms"),
        ("optional_dependencies", ["audio", "audio"], "optional dependencies"),
    ],
)
def test_invalid_capability_metadata_is_rejected(field: str, value: object, message: str) -> None:
    data = _registry_data()
    capability = data["capabilities"][0]  # type: ignore[index]
    capability[field] = value

    with pytest.raises(CapabilityRegistryError, match=message):
        CapabilityRegistry.from_dict(data)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            {
                "target_support": "not-applicable",
                "implementation_status": "implemented",
                "conformance_status": "unverified",
                "entry_points": ["fo invalid"],
            },
            "not-applicable and cannot have implementation evidence",
        ),
        (
            {
                "target_support": "full",
                "implementation_status": "implemented",
                "conformance_status": "unverified",
                "entry_points": [],
            },
            "implemented but has no entry point evidence",
        ),
        (
            {
                "target_support": "full",
                "implementation_status": "partial",
                "conformance_status": "verified",
                "entry_points": ["fo partial"],
            },
            "cannot be verified until implementation is complete",
        ),
        (
            {
                "target_support": "full",
                "implementation_status": "not-applicable",
                "conformance_status": "not-applicable",
                "entry_points": [],
            },
            "applicable target support but a not-applicable status",
        ),
        (
            {
                "target_support": "full",
                "implementation_status": "not-implemented",
                "conformance_status": "unverified",
                "entry_points": ["fo impossible"],
            },
            "not implemented but declares entry points",
        ),
        (
            {
                "target_support": "full",
                "implementation_status": "implemented",
                "conformance_status": "unverified",
                "entry_points": ["fo duplicate", "fo duplicate"],
            },
            "invalid or duplicate entry points",
        ),
    ],
)
def test_invalid_surface_state_is_rejected(mutation: dict[str, object], message: str) -> None:
    data = _registry_data()
    capability = data["capabilities"][0]  # type: ignore[index]
    capability["surfaces"][Surface.CLI.value] = mutation

    with pytest.raises(CapabilityRegistryError, match=message):
        CapabilityRegistry.from_dict(data)


def test_auth_gated_scope_requires_remote_scope() -> None:
    data = _registry_data()
    capability = data["capabilities"][0]  # type: ignore[index]
    capability["execution_scopes"] = ["auth-gated"]

    with pytest.raises(CapabilityRegistryError, match="auth-gated without remote"):
        CapabilityRegistry.from_dict(data)


def test_unknown_capability_lookup_raises_key_error() -> None:
    with pytest.raises(KeyError, match="missing.capability"):
        get_capability_registry().get("missing.capability")


def test_optional_dependencies_name_project_extras() -> None:
    registry = get_capability_registry()
    project_extras = {
        "audio",
        "claude",
        "cloud",
        "dedup",
        "desktop",
        "llama",
        "mlx",
        "parsers",
        "search",
        "video",
    }

    declared = {
        dependency
        for capability in registry.capabilities
        for dependency in capability.optional_dependencies
    }
    assert declared <= project_extras


def test_official_client_product_methods_are_inventoried() -> None:
    ignored_methods = {"aclose", "close", "set_token"}
    registered = {
        entry_point
        for capability in get_capability_registry().capabilities
        for entry_point in capability.support_for(Surface.PYTHON_SDK).entry_points
    }
    live: set[str] = set()

    for client_type in (FileOrganizerClient, AsyncFileOrganizerClient):
        live.update(
            f"{client_type.__name__}.{name}"
            for name, member in inspect.getmembers(client_type, inspect.isfunction)
            if not name.startswith("_") and name not in ignored_methods
        )

    missing = live - registered
    stale = registered - live
    assert not missing, f"unregistered Python client methods: {sorted(missing)}"
    assert not stale, f"stale Python SDK registry entry points: {sorted(stale)}"


def test_typescript_client_product_methods_are_inventoried() -> None:
    inventory_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "file_organizer"
        / "client"
        / "typescript"
        / "methods.generated.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    methods = inventory["methods"]
    assert inventory["schema_version"] == 1
    assert methods == sorted(set(methods))

    generated = {f"FileOrganizerClient.{name}" for name in methods}
    specified = {
        f"FileOrganizerClient.{endpoint.typescript_method}" for endpoint in PUBLIC_ENDPOINTS
    }
    registered = {
        entry_point
        for capability in get_capability_registry().capabilities
        for entry_point in capability.support_for(Surface.TYPESCRIPT_SDK).entry_points
    }

    assert generated == specified
    assert generated == registered
