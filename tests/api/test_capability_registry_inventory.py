"""Guard public HTTP and Web entry points against capability-registry drift."""

from __future__ import annotations

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app
from file_organizer.core.capabilities import get_capability_registry

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def test_public_routes_are_assigned_to_capabilities() -> None:
    app = create_app(ApiSettings(environment="test", auth_enabled=False, enable_docs=False))
    registered_entry_points = {
        entry_point
        for capability in get_capability_registry().capabilities
        for status in capability.surfaces
        for entry_point in status.entry_points
    }
    public_routes: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith(("/api/v1", "/ui")):
            continue
        methods = getattr(route, "methods", None) or {"WS"}
        public_routes.update(f"{method} {path}" for method in methods)

    missing = public_routes - registered_entry_points
    assert not missing, f"public routes missing capability ownership: {sorted(missing)}"
