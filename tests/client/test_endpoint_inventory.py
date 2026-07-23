"""Fail CI when public REST operations, official SDKs, or option-field parity drift apart."""

from __future__ import annotations

import inspect
import re

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app
from file_organizer.api.models import OrganizationOptionsPayload as RestOptionsPayload
from file_organizer.client.async_client import AsyncFileOrganizerClient
from file_organizer.client.endpoint_spec import INTENTIONAL_EXCLUSIONS, PUBLIC_ENDPOINTS
from file_organizer.client.models import OrganizationOptionsPayload as SdkOptionsPayload
from file_organizer.client.sync_client import FileOrganizerClient
from file_organizer.core.capabilities import Surface, get_capability_registry
from file_organizer.core.organize_options import OrganizeOptions
from tests._route_inventory import iter_effective_routes

pytestmark = [pytest.mark.ci, pytest.mark.unit]

_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _app():
    return create_app(ApiSettings(environment="test", auth_enabled=False, enable_docs=False))


def test_endpoint_spec_exactly_matches_public_openapi_routes() -> None:
    actual = {
        f"{method} {route.path}"
        for route in iter_effective_routes(_app())
        if route.path.startswith("/api/v1")
        for method in (getattr(route, "methods", None) or set())
        if method in _HTTP_METHODS
    }
    expected = {endpoint.key for endpoint in PUBLIC_ENDPOINTS}

    assert actual == expected


def test_openapi_operation_ids_are_stable_and_unique() -> None:
    operation_ids = [
        operation["operationId"]
        for route_path, path in _app().openapi()["paths"].items()
        if route_path.startswith("/api/v1")
        for method, operation in path.items()
        if method.upper() in _HTTP_METHODS
    ]

    assert len(operation_ids) == len(set(operation_ids))
    assert all(re.fullmatch(r"[a-z][a-z0-9_-]*", value) for value in operation_ids)


def test_python_sync_and_async_clients_cover_spec_with_equal_signatures() -> None:
    for endpoint in PUBLIC_ENDPOINTS:
        sync_method = getattr(FileOrganizerClient, endpoint.python_method)
        async_method = getattr(AsyncFileOrganizerClient, endpoint.python_method)
        assert inspect.signature(sync_method) == inspect.signature(async_method), endpoint.key


def test_non_openapi_transports_have_explained_exclusions() -> None:
    assert INTENTIONAL_EXCLUSIONS == {
        "WS /api/v1/ws/{client_id}": (
            "WebSocket transport is not described by OpenAPI; use job polling until "
            "a separately versioned realtime SDK contract is introduced."
        )
    }


def test_endpoint_spec_matches_capability_ownership() -> None:
    registry = get_capability_registry()
    for endpoint in PUBLIC_ENDPOINTS:
        for capability_id in endpoint.capability_ids:
            capability = registry.get(capability_id)
            assert endpoint.key in capability.support_for(Surface.REST_API).entry_points
            assert (
                f"FileOrganizerClient.{endpoint.python_method}"
                in capability.support_for(Surface.PYTHON_SDK).entry_points
            )
            assert (
                f"AsyncFileOrganizerClient.{endpoint.python_method}"
                in capability.support_for(Surface.PYTHON_SDK).entry_points
            )
            assert (
                f"FileOrganizerClient.{endpoint.typescript_method}"
                in capability.support_for(Surface.TYPESCRIPT_SDK).entry_points
            )


def test_single_file_suggestion_is_not_owned_by_plan_execution() -> None:
    suggestion = next(
        endpoint for endpoint in PUBLIC_ENDPOINTS if endpoint.key == "POST /api/v1/organize"
    )

    assert suggestion.capability_ids == ("organization.suggest",)


# ---------------------------------------------------------------------------
# Option-field parity: guard the _merge_remote_plan_options round-trip
# ---------------------------------------------------------------------------
#
# ``cli/api.py::_merge_remote_plan_options`` round-trips between the transport
# payload and the canonical contract:
#
#   OrganizationOptionsPayload  ->  OrganizeOptions.from_dict(...)
#                               ->  _merge_explicit_plan_options(...)
#                               ->  OrganizationOptionsPayload.model_validate(merged.to_dict())
#
# This only works because:
#   1. every payload field is consumable by OrganizeOptions.from_dict (subset);
#   2. OrganizeOptions.to_dict() output validates against the payload model.
#
# ``use_hardlinks`` is the sole intentional asymmetry: it lives on OrganizeOptions
# as a legacy input-only alias and is stripped by to_dict().


def test_rest_payload_fields_are_subset_of_canonical_options() -> None:
    """Every REST transport field must be consumable by OrganizeOptions.from_dict."""
    payload_fields = set(RestOptionsPayload.model_fields)
    option_fields = set(OrganizeOptions.__dataclass_fields__)
    extra = payload_fields - option_fields
    assert not extra, (
        f"REST OrganizationOptionsPayload has fields not present on OrganizeOptions: {extra}. "
        "OrganizeOptions.from_dict() will reject them, breaking _merge_remote_plan_options."
    )


def test_sdk_payload_fields_are_subset_of_canonical_options() -> None:
    """Every SDK transport field must be consumable by OrganizeOptions.from_dict."""
    payload_fields = set(SdkOptionsPayload.model_fields)
    option_fields = set(OrganizeOptions.__dataclass_fields__)
    extra = payload_fields - option_fields
    assert not extra, (
        f"SDK OrganizationOptionsPayload has fields not present on OrganizeOptions: {extra}. "
        "OrganizeOptions.from_dict() will reject them, breaking _merge_remote_plan_options."
    )


@pytest.mark.parametrize(
    "options",
    [
        OrganizeOptions(),
        OrganizeOptions(transfer_mode="copy", methodology="para", recursive=False),
        OrganizeOptions(transfer_mode="hardlink", methodology="jd", prefetch_depth=5),
    ],
)
def test_canonical_options_to_dict_validates_against_rest_payload(
    options: OrganizeOptions,
) -> None:
    """OrganizeOptions().to_dict() must validate back to the REST transport model."""
    canonical = options.to_dict()
    payload = RestOptionsPayload.model_validate(canonical)
    # Assert every canonical field survives the round-trip, not just spot-checks.
    for field in RestOptionsPayload.model_fields:
        assert getattr(payload, field) == canonical[field], (
            f"REST payload field {field!r} diverges: model={getattr(payload, field)!r} "
            f"vs canonical={canonical[field]!r}"
        )


@pytest.mark.parametrize(
    "options",
    [
        OrganizeOptions(),
        OrganizeOptions(transfer_mode="copy", methodology="para", recursive=False),
        OrganizeOptions(transfer_mode="hardlink", methodology="jd", prefetch_depth=5),
    ],
)
def test_canonical_options_to_dict_validates_against_sdk_payload(
    options: OrganizeOptions,
) -> None:
    """OrganizeOptions().to_dict() must validate back to the SDK transport model."""
    canonical = options.to_dict()
    payload = SdkOptionsPayload.model_validate(canonical)
    for field in SdkOptionsPayload.model_fields:
        assert getattr(payload, field) == canonical[field], (
            f"SDK payload field {field!r} diverges: model={getattr(payload, field)!r} "
            f"vs canonical={canonical[field]!r}"
        )


def test_to_dict_drops_use_hardlinks_legacy_alias() -> None:
    """The legacy ``use_hardlinks`` field must not leak into the canonical serialization.

    ``OrganizationOptionsPayload`` defines ``transfer_mode`` instead, so emitting
    ``use_hardlinks`` would cause ``model_validate`` to reject the dict as an extra field.
    """
    canonical = OrganizeOptions().to_dict()
    assert "use_hardlinks" not in canonical


def test_rest_and_sdk_payloads_declare_identical_fields() -> None:
    """The REST and SDK payload models must agree on exactly which fields exist."""
    rest = set(RestOptionsPayload.model_fields)
    sdk = set(SdkOptionsPayload.model_fields)
    assert rest == sdk, (
        f"REST-only: {rest - sdk}, SDK-only: {sdk - rest}. "
        "The REST and SDK OrganizationOptionsPayload models must declare the same fields."
    )
