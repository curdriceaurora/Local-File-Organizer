"""Fail CI when public REST operations and official SDKs drift apart."""

from __future__ import annotations

import inspect
import re

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app
from file_organizer.client.async_client import AsyncFileOrganizerClient
from file_organizer.client.endpoint_spec import INTENTIONAL_EXCLUSIONS, PUBLIC_ENDPOINTS
from file_organizer.client.sync_client import FileOrganizerClient
from file_organizer.core.capabilities import Surface, get_capability_registry
from tests.api.route_inventory import iter_effective_routes

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
