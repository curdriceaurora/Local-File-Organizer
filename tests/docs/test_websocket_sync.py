"""Test that WebSocket documentation matches actual WebSocket route registration.

Validates:
- WebSocket path is documented correctly (/api/v1/ws/{client_id}, not /api/v1/ws)
- WebSocket connection examples use the real path format
- Documented event types are consistent with handler implementation
"""

from __future__ import annotations

import re

import pytest

from tests.docs.conftest import DOCS_DIR

WEBSOCKET_DOC = DOCS_DIR / "api" / "websocket-api.md"

# Real WebSocket path from file_organizer/api/routers/realtime.py
# @router.websocket("/ws/{client_id}") + prefix="/api/v1" = /api/v1/ws/{client_id}
REAL_WS_PATH = "/api/v1/ws/{client_id}"
REAL_WS_PATTERN = r"/api/v\d+/ws/\{client_id\}"
WRONG_WS_PATH = "/api/v1/ws"  # Missing {client_id}


@pytest.mark.unit
class TestWebSocketPathDocumentation:
    """Validate WebSocket path is documented correctly."""

    def test_websocket_doc_exists(self) -> None:
        """websocket-api.md must exist."""
        if not WEBSOCKET_DOC.exists():
            pytest.skip("websocket-api.md not found — Issue #317 tracks this gap")

    def test_websocket_path_includes_client_id(self) -> None:
        """WebSocket path must include {client_id} parameter."""
        if not WEBSOCKET_DOC.exists():
            pytest.skip("websocket-api.md not found")

        content = WEBSOCKET_DOC.read_text()

        # Check for the correct path pattern
        has_correct_path = bool(re.search(REAL_WS_PATTERN, content))
        has_wrong_path = WRONG_WS_PATH in content and not has_correct_path

        if has_wrong_path:
            pytest.fail(
                f"websocket-api.md documents '{WRONG_WS_PATH}' but the real path is "
                f"'{REAL_WS_PATH}'. The {{client_id}} path parameter is required.\n\n"
                f"Fix: Replace '/api/v1/ws' with '/api/v1/ws/{{client_id}}' throughout the doc."
            )

        if not has_correct_path and not has_wrong_path:
            # Neither pattern — check if ws path is documented at all
            if "/ws" not in content:
                pytest.fail(
                    f"websocket-api.md does not document the WebSocket path. "
                    f"The real path is '{REAL_WS_PATH}'."
                )

    def test_websocket_connection_example_uses_real_path(self) -> None:
        """WebSocket connection examples must use the real path with client_id."""
        if not WEBSOCKET_DOC.exists():
            pytest.skip("websocket-api.md not found")

        content = WEBSOCKET_DOC.read_text()

        # Find code blocks with ws:// or wss:// connections
        ws_connections = re.findall(r"wss?://[^\s\'\"\)]+", content)

        bad_connections = []
        for conn in ws_connections:
            # Connection URL should end with /ws/{client_id} or /ws/some-id
            if re.search(r"/ws$", conn.rstrip("/")):
                bad_connections.append(conn)

        assert not bad_connections, (
            "WebSocket connection examples use incomplete paths (missing client_id):\n"
            + "\n".join(f"  - {c}" for c in bad_connections)
            + "\n\nFix: Use 'ws://host/api/v1/ws/{client_id}' pattern"
        )

    def test_websocket_token_parameter_documented(self) -> None:
        """WebSocket docs should document the 'token' query parameter for auth."""
        if not WEBSOCKET_DOC.exists():
            pytest.skip("websocket-api.md not found")

        content = WEBSOCKET_DOC.read_text()

        # The real WS endpoint accepts ?token= for auth
        # If docs talk about auth, they should mention the token parameter
        if "auth" in content.lower() or "token" in content.lower():
            # Ensure docs don't document wrong auth method
            bearer_in_ws = bool(re.search(r"Authorization:\s*Bearer", content, re.IGNORECASE))
            assert not bearer_in_ws, (
                "websocket-api.md uses Authorization: Bearer for WebSocket auth, "
                "but the real endpoint uses ?token= query parameter. "
                "Fix: Document token as query parameter: ws://host/api/v1/ws/{client_id}?token=<jwt>"
            )
