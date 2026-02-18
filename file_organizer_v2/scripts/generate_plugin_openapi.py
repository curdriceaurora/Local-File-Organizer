"""Generate plugin API OpenAPI reference JSON for docs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app

DOCS_OUTPUT = Path("docs/phase-6/plugin-development/api/openapi-plugin.json")


def _build_docs_settings() -> ApiSettings:
    return ApiSettings(
        environment="docs",
        enable_docs=True,
        allowed_paths=["."],
        auth_enabled=False,
        rate_limit_enabled=False,
    )


def _filter_plugin_paths(schema: dict[str, Any]) -> dict[str, Any]:
    plugin_paths = {
        path: value
        for path, value in schema.get("paths", {}).items()
        if path.startswith("/api/v1/plugins/")
    }
    filtered = dict(schema)
    filtered["paths"] = plugin_paths
    return filtered


def generate() -> Path:
    app = create_app(_build_docs_settings())
    schema = app.openapi()
    filtered_schema = _filter_plugin_paths(schema)

    DOCS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DOCS_OUTPUT.write_text(
        json.dumps(filtered_schema, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return DOCS_OUTPUT


def main() -> int:
    destination = generate()
    print(f"Generated plugin OpenAPI schema: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
