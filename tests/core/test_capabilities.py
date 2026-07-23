"""Tests for the canonical cross-surface capability registry."""

from __future__ import annotations

import copy
import inspect
import json
from collections.abc import Iterable
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
    SupportLevel,
    Surface,
    SurfaceCapabilityStatus,
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

    for capability_id in ("organization.scan", "organization.preview", "organization.execute"):
        capability = registry.get(capability_id)
        assert (
            capability.support_for(Surface.REST_API).conformance_status
            is ConformanceStatus.VERIFIED
        )
        assert (
            capability.support_for(Surface.PYTHON_SDK).conformance_status
            is ConformanceStatus.VERIFIED
        )
        assert (
            capability.support_for(Surface.WEB_DESKTOP).conformance_status
            is ConformanceStatus.VERIFIED
        )
        # TypeScript SDK has request-only mock tests in node; response drift is unverified
        assert (
            capability.support_for(Surface.TYPESCRIPT_SDK).conformance_status
            is ConformanceStatus.UNVERIFIED
        )

    for capability_id in ("organization.execute", "organization.preview"):
        capability = registry.get(capability_id)
        assert capability.support_for(Surface.CLI).conformance_status is ConformanceStatus.VERIFIED
        assert capability.support_for(Surface.TUI).conformance_status is ConformanceStatus.VERIFIED

    for capability_id in ("organization.suggest",):
        capability = registry.get(capability_id)
        for surface in (
            Surface.REST_API,
            Surface.PYTHON_SDK,
            Surface.TYPESCRIPT_SDK,
            Surface.CLI,
            Surface.TUI,
            Surface.WEB_DESKTOP,
        ):
            assert (
                capability.support_for(surface).conformance_status is ConformanceStatus.UNVERIFIED
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


def test_capability_matrix_up_to_date() -> None:
    from scripts.generate_capability_matrix import generate_capability_matrix_markdown

    matrix_path = (
        Path(__file__).resolve().parents[2] / "docs" / "developer" / "capability-matrix.md"
    )
    assert matrix_path.exists(), f"Capability matrix file {matrix_path} missing"
    on_disk = matrix_path.read_text(encoding="utf-8")
    generated = generate_capability_matrix_markdown()

    assert on_disk == generated, (
        f"Capability matrix in {matrix_path} is out of date. Run 'python scripts/generate_capability_matrix.py' to update it."
    )


def test_capability_matrix_cell_formatting_semantic_axes() -> None:
    from scripts.generate_capability_matrix import _format_surface_cell

    unverified_status = SurfaceCapabilityStatus(
        surface=Surface.TYPESCRIPT_SDK,
        target_support=SupportLevel.FULL,
        implementation_status=ImplementationStatus.IMPLEMENTED,
        conformance_status=ConformanceStatus.UNVERIFIED,
        entry_points=("FileOrganizerClient.organize",),
    )
    verified_status = SurfaceCapabilityStatus(
        surface=Surface.REST_API,
        target_support=SupportLevel.FULL,
        implementation_status=ImplementationStatus.IMPLEMENTED,
        conformance_status=ConformanceStatus.VERIFIED,
        entry_points=("POST /api/v1/organize/execute",),
    )
    unimplemented_status = SurfaceCapabilityStatus(
        surface=Surface.CLI,
        target_support=SupportLevel.FULL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        conformance_status=ConformanceStatus.UNVERIFIED,
        entry_points=(),
    )
    na_status = SurfaceCapabilityStatus(
        surface=Surface.CLI,
        target_support=SupportLevel.NOT_APPLICABLE,
        implementation_status=ImplementationStatus.NOT_APPLICABLE,
        conformance_status=ConformanceStatus.NOT_APPLICABLE,
        entry_points=(),
    )

    # Acceptance Criterion 1: Matrix never equates target support with verified support
    assert _format_surface_cell(unverified_status) == "Full (Implemented / Unverified)"
    assert _format_surface_cell(verified_status) == "Full (Implemented / Verified)"
    assert _format_surface_cell(unimplemented_status) == "Full (Not-implemented / Unverified)"
    assert _format_surface_cell(na_status) == "N/A"
    assert _format_surface_cell(unverified_status) != _format_surface_cell(verified_status)
    assert (
        _format_surface_cell(unverified_status)
        != unverified_status.target_support.value.capitalize()
    )


def test_capability_matrix_renders_three_status_axes_for_known_capabilities() -> None:
    from scripts.generate_capability_matrix import generate_capability_matrix_markdown

    content = generate_capability_matrix_markdown()

    # Verify key rows contain explicit three-status cells for unverified vs verified surfaces
    assert (
        "| [`organization.execute`](#organizationexecute) | Organization execution | Stable | Full (Implemented / Verified) | Full (Implemented / Verified) | Full (Implemented / Verified) | Full (Implemented / Unverified) | Full (Implemented / Verified) | Full (Implemented / Verified) |"
        in content
    )
    assert (
        "| [`accounts.manage`](#accountsmanage) | Account and workspace management | Beta | N/A | Full (Not-implemented / Unverified) | Full (Not-implemented / Unverified) | Full (Not-implemented / Unverified) | Full (Implemented / Unverified) | N/A |"
        in content
    )


def test_capability_matrix_prose_important_note_matches_cell_format() -> None:
    from scripts.generate_capability_matrix import (
        _format_surface_cell,
        generate_capability_matrix_markdown,
    )

    sample_status = SurfaceCapabilityStatus(
        surface=Surface.TYPESCRIPT_SDK,
        target_support=SupportLevel.FULL,
        implementation_status=ImplementationStatus.IMPLEMENTED,
        conformance_status=ConformanceStatus.UNVERIFIED,
        entry_points=("FileOrganizerClient.organize",),
    )
    formatted_sample = _format_surface_cell(sample_status)
    content = generate_capability_matrix_markdown()

    assert f"> A surface cell formatted as `{formatted_sample}` represents" in content


def test_public_claims_freshness() -> None:
    from scripts.verify_claims_freshness import verify_public_claims

    readme_path = Path(__file__).resolve().parents[2] / "README.md"
    errors = verify_public_claims(readme_path)
    assert not errors, f"Public claims verification failed: {errors}"


def test_public_claims_freshness_stale_counts(tmp_path: Path) -> None:
    from scripts.verify_claims_freshness import verify_public_claims

    # Test stale capability count failure
    stale_readme = tmp_path / "README_stale.md"
    stale_readme.write_text(
        "## Features\n\n- **Capabilities**: Built on [35 product capabilities](docs/developer/capability-matrix.md#summary-statistics).\n",
        encoding="utf-8",
    )
    errors = verify_public_claims(stale_readme)
    assert any("stale product capability count '35'" in err for err in errors)


def test_public_claims_freshness_anchor_mismatch(tmp_path: Path) -> None:
    from scripts.verify_claims_freshness import verify_public_claims

    # Test ID and anchor mismatch failure (both individually valid, but mismatched)
    mismatched_readme = tmp_path / "README_mismatch.md"
    mismatched_readme.write_text(
        "## Features\n\n- **Analysis**: See [`analysis.inspect`](docs/developer/capability-matrix.md#audiotranscribe).\n",
        encoding="utf-8",
    )
    errors = verify_public_claims(mismatched_readme)
    assert any(
        "has mismatched anchor '#audiotranscribe' (expected '#analysisinspect')" in err
        for err in errors
    )


def _conformance_claim_readme(capability_ids: Iterable[str]) -> str:
    """Render a minimal README advertising the given capabilities as conformance-verified."""
    links = ", ".join(
        f"[`{capability_id}`](docs/developer/capability-matrix.md#{capability_id.replace('.', '')})"
        for capability_id in capability_ids
    )
    return f"## Features\n\n- **Matrix**: conformance-verified for {links}.\n"


def test_public_claims_rejects_capability_advertised_without_evidence(tmp_path: Path) -> None:
    from scripts.verify_claims_freshness import _verified_capability_ids, verify_public_claims

    verified = _verified_capability_ids()
    unverified = sorted(
        capability.capability_id
        for capability in get_capability_registry().capabilities
        if capability.capability_id not in verified
    )
    assert unverified, "registry must retain at least one capability without conformance evidence"

    readme = tmp_path / "README_overclaim.md"
    readme.write_text(_conformance_claim_readme([unverified[0]]), encoding="utf-8")

    errors = verify_public_claims(readme)
    assert any(
        f"advertises '{unverified[0]}' as conformance-verified, but it holds no verified surface"
        in err
        for err in errors
    )


def test_public_claims_rejects_omitting_a_verified_capability(tmp_path: Path) -> None:
    from scripts.verify_claims_freshness import _verified_capability_ids, verify_public_claims

    verified = sorted(_verified_capability_ids())
    assert len(verified) > 1, "registry must hold more than one verified capability"

    # Advertise every verified capability except one; the omission must be reported.
    readme = tmp_path / "README_omission.md"
    readme.write_text(_conformance_claim_readme(verified[1:]), encoding="utf-8")

    errors = verify_public_claims(readme)
    assert any(
        f"omits '{verified[0]}' from its conformance-verified claim" in err for err in errors
    )


def test_public_claims_rejects_retired_inventory_metrics(tmp_path: Path) -> None:
    from scripts.verify_claims_freshness import verify_public_claims

    readme = tmp_path / "README_metrics.md"
    readme.write_text(
        "## Features\n\n- **Support**: Operates on 840 tests, 408 modules, and 39 file types "
        "with 99.99% uptime (see [`analysis.inspect`]"
        "(docs/developer/capability-matrix.md#analysisinspect)).\n",
        encoding="utf-8",
    )

    errors = verify_public_claims(readme)
    for retired in ("840 tests", "408 modules", "39 file types", "99.99% uptime"):
        assert any(retired in err for err in errors), f"{retired} must be rejected"


def test_public_claims_rejects_capability_count_without_conformance_scope(tmp_path: Path) -> None:
    from scripts.verify_claims_freshness import verify_public_claims

    # Deleting the conformance clause must not be a way to pass while still quoting a headline total.
    readme = tmp_path / "README_unscoped.md"
    readme.write_text(
        "## Features\n\n- **Matrix**: Built on [34 product capabilities]"
        "(docs/developer/capability-matrix.md#summary-statistics).\n",
        encoding="utf-8",
    )

    errors = verify_public_claims(readme)
    assert any("no conformance-verified claim scoping" in err for err in errors)


def test_public_claims_allows_readme_making_no_capability_count_claim(tmp_path: Path) -> None:
    from scripts.verify_claims_freshness import verify_public_claims

    # Nothing to scope, so the conformance clause is not required.
    readme = tmp_path / "README_noclaim.md"
    readme.write_text(
        "## Features\n\n- **Analysis**: See [`analysis.inspect`]"
        "(docs/developer/capability-matrix.md#analysisinspect).\n",
        encoding="utf-8",
    )

    errors = verify_public_claims(readme)
    assert not any("conformance-verified" in err for err in errors), errors


def test_matrix_anchors_disambiguate_repeated_headings() -> None:
    from scripts.verify_claims_freshness import DEFAULT_MATRIX_PATH, extract_matrix_anchors

    # "#### Surface Status & Entry Points" repeats once per capability, so GitHub's -1/-2
    # disambiguation is load-bearing here rather than theoretical.
    anchors = extract_matrix_anchors(DEFAULT_MATRIX_PATH)
    base = "surface-status--entry-points"
    assert base in anchors
    assert f"{base}-1" in anchors
    assert f"{base}-33" in anchors


def test_matrix_heading_slugs_accept_both_whitespace_conventions() -> None:
    from scripts.verify_claims_freshness import _slugify_heading

    # GitHub emits one hyphen per whitespace character; other renderers collapse runs.
    assert _slugify_heading("`organization.execute` — Organization execution") == {
        "organizationexecute-organization-execution",
        "organizationexecute--organization-execution",
    }
    assert _slugify_heading("Summary Statistics") == {"summary-statistics"}
    assert _slugify_heading("!!!") == set()
