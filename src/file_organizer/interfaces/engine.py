"""Unified engine lifecycle protocol.

``EngineProtocol`` provides a common lifecycle contract (init / process /
shutdown / health_check) that unifies the different lifecycle patterns
used across the codebase:

- ``BaseModel``: initialize / generate / cleanup
- ``Plugin``: on_load / on_enable / on_disable / on_unload
- ``Integration``: connect / disconnect / validate_auth / get_status

Implementations only need to satisfy the structural interface — no
inheritance changes are required.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EngineProtocol(Protocol):
    """Unified lifecycle contract for models, plugins, and integrations.

    Provides a 4-method lifecycle:
    - ``init``: Acquire resources and prepare for work.
    - ``process``: Perform the engine's primary operation.
    - ``shutdown``: Release resources cleanly.
    - ``health_check``: Report runtime readiness.
    """

    def init(self) -> None:
        """Acquire resources and prepare for work."""
        ...

    def process(self, input_data: Any, **kwargs: Any) -> Any:
        """Perform the engine's primary operation."""
        ...

    def shutdown(self) -> None:
        """Release resources cleanly."""
        ...

    def health_check(self) -> dict[str, Any]:
        """Report runtime readiness and status."""
        ...
