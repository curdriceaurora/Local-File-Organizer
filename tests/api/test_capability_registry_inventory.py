"""Guard public HTTP and Web entry points against capability-registry drift."""

from __future__ import annotations

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app
from file_organizer.core.capabilities import Surface, get_capability_registry
from tests.api.route_inventory import iter_effective_routes

pytestmark = [pytest.mark.ci, pytest.mark.unit]


@pytest.mark.parametrize(
    ("path_prefix", "surface"),
    [
        ("/api/v1", Surface.REST_API),
        ("/ui", Surface.WEB_DESKTOP),
    ],
)
def test_public_routes_match_registered_entry_points(path_prefix: str, surface: Surface) -> None:
    app = create_app(ApiSettings(environment="test", auth_enabled=False, enable_docs=False))
    registered_entry_points = {
        entry_point
        for capability in get_capability_registry().capabilities
        for entry_point in capability.support_for(surface).entry_points
    }
    public_routes: set[str] = set()
    for route in iter_effective_routes(app):
        path = getattr(route, "path", "")
        if not path.startswith(path_prefix):
            continue
        methods = getattr(route, "methods", None) or {"WS"}
        public_routes.update(f"{method} {path}" for method in methods)

    missing = public_routes - registered_entry_points
    stale = registered_entry_points - public_routes
    assert not missing, f"{surface.value} routes missing capability ownership: {sorted(missing)}"
    assert not stale, f"stale {surface.value} registry entry points: {sorted(stale)}"
