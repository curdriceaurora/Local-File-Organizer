"""Service bus for inter-service communication.

Provides request/response and broadcast messaging patterns on top
of the existing pub/sub layer.  Services register handlers and
communicate through a shared bus with automatic request tracking,
timeout support, and error handling.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from file_organizer.events.pubsub import PubSubManager

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceRequest:
    """A request sent between services via the bus.

    Attributes:
        id: Unique identifier for this request.
        source: Name of the service sending the request.
        target: Name of the target service.
        action: The action to invoke on the target.
        payload: Arbitrary data accompanying the request.
        timestamp: UTC timestamp when the request was created.
    """

    id: str
    source: str
    target: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize the request to a plain dictionary.

        Returns:
            Dictionary representation suitable for JSON encoding.
        """
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "action": self.action,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class ServiceResponse:
    """A response returned by a service after handling a request.

    Attributes:
        request_id: The ``id`` of the originating :class:`ServiceRequest`.
        success: Whether the request was handled without error.
        data: Response payload on success.
        error: Error description on failure.
        duration_ms: Time taken to handle the request in milliseconds.
    """

    request_id: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the response to a plain dictionary.

        Returns:
            Dictionary representation suitable for JSON encoding.
        """
        return {
            "request_id": self.request_id,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


# ------------------------------------------------------------------
# Service bus
# ------------------------------------------------------------------


class ServiceBus:
    """Message bus enabling request/response and broadcast communication.

    Services register themselves with a handler callable.  Other
    services can then send targeted requests or broadcast messages
    to all registered services.

    The bus is built on top of :class:`PubSubManager` for transport,
    but adds request tracking and synchronous request/response
    semantics.

    Example::

        bus = ServiceBus(name="gateway")

        def handle_echo(request: ServiceRequest) -> dict:
            return {"echo": request.payload}

        bus.register_service("echo", handle_echo)
        response = bus.send_request("echo", "ping", {"msg": "hello"})
        assert response.success
    """

    def __init__(
        self,
        name: str = "default",
        pubsub: PubSubManager | None = None,
    ) -> None:
        """Initialize the service bus.

        Args:
            name: Name of this bus node (used as the ``source`` in
                outgoing requests).
            pubsub: Optional :class:`PubSubManager` for underlying
                message transport.  A default instance is created if
                not provided.
        """
        self._name = name
        self._pubsub = pubsub or PubSubManager()
        self._services: dict[str, Callable[..., Any]] = {}
        self._request_count = 0
        self._error_count = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Name of this bus node."""
        return self._name

    @property
    def services(self) -> dict[str, Callable[..., Any]]:
        """Registered services (read-only snapshot)."""
        return dict(self._services)

    @property
    def request_count(self) -> int:
        """Total number of requests processed."""
        return self._request_count

    @property
    def error_count(self) -> int:
        """Total number of requests that resulted in errors."""
        return self._error_count

    # ------------------------------------------------------------------
    # Service registration
    # ------------------------------------------------------------------

    def register_service(self, name: str, handler: Callable[..., Any]) -> None:
        """Register a service handler on this bus.

        Args:
            name: Unique service name.
            handler: Callable that accepts a :class:`ServiceRequest`
                and returns a dict (or raises on error).

        Raises:
            ValueError: If a service with the same *name* is already
                registered.
        """
        if name in self._services:
            raise ValueError(f"Service '{name}' is already registered")
        self._services[name] = handler
        logger.info("Registered service '%s' on bus '%s'", name, self._name)

    def deregister_service(self, name: str) -> bool:
        """Remove a registered service.

        Args:
            name: Service name to remove.

        Returns:
            ``True`` if the service was found and removed.
        """
        if name in self._services:
            del self._services[name]
            logger.info("Deregistered service '%s' from bus '%s'", name, self._name)
            return True
        return False

    def has_service(self, name: str) -> bool:
        """Check whether a service is registered.

        Args:
            name: Service name.

        Returns:
            ``True`` if the service is registered.
        """
        return name in self._services

    # ------------------------------------------------------------------
    # Request / Response
    # ------------------------------------------------------------------

    def send_request(
        self,
        target: str,
        action: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 5.0,
    ) -> ServiceResponse:
        """Send a request to a registered service.

        The handler is invoked **synchronously** and its return value
        is wrapped in a :class:`ServiceResponse`.  If the handler
        raises, the exception is caught and an error response is
        returned.

        Args:
            target: Name of the target service.
            action: Action to perform.
            payload: Data to send with the request.
            timeout: Maximum time in seconds to wait for a response.
                Currently enforced via a simple wall-clock check
                after handler execution.

        Returns:
            :class:`ServiceResponse` with the result.
        """
        request = ServiceRequest(
            id=str(uuid.uuid4()),
            source=self._name,
            target=target,
            action=action,
            payload=payload or {},
            timestamp=datetime.now(timezone.utc),
        )

        self._request_count += 1

        # Check service exists
        handler = self._services.get(target)
        if handler is None:
            self._error_count += 1
            logger.warning("Service '%s' not found on bus '%s'", target, self._name)
            return ServiceResponse(
                request_id=request.id,
                success=False,
                error=f"Service '{target}' not found",
            )

        # Publish the request event (fire-and-forget for auditing)
        topic = f"service.request.{target}.{action}"
        self._pubsub.publish(topic, request.to_dict())

        # Execute handler
        start = time.monotonic()
        try:
            result = handler(request)
            elapsed_ms = (time.monotonic() - start) * 1000.0

            # Timeout check (after execution)
            if elapsed_ms > timeout * 1000.0:
                self._error_count += 1
                logger.warning(
                    "Request to '%s.%s' exceeded timeout (%.1f ms > %.1f ms)",
                    target,
                    action,
                    elapsed_ms,
                    timeout * 1000.0,
                )
                return ServiceResponse(
                    request_id=request.id,
                    success=False,
                    error=f"Request timed out after {elapsed_ms:.1f}ms",
                    duration_ms=elapsed_ms,
                )

            response_data = result if isinstance(result, dict) else {}
            response = ServiceResponse(
                request_id=request.id,
                success=True,
                data=response_data,
                duration_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            self._error_count += 1
            logger.error(
                "Handler error for '%s.%s': %s",
                target,
                action,
                exc,
                exc_info=True,
            )
            response = ServiceResponse(
                request_id=request.id,
                success=False,
                error=str(exc),
                duration_ms=elapsed_ms,
            )

        # Publish the response event
        resp_topic = f"service.response.{target}.{action}"
        self._pubsub.publish(resp_topic, response.to_dict())

        return response

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def broadcast(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, ServiceResponse]:
        """Broadcast a request to all registered services.

        Each service receives the same action and payload.  Responses
        are collected into a dictionary keyed by service name.

        Args:
            action: Action to broadcast.
            payload: Data to include in every request.

        Returns:
            Dictionary mapping service name to its response.
        """
        results: dict[str, ServiceResponse] = {}
        for service_name in list(self._services):
            results[service_name] = self.send_request(
                target=service_name,
                action=action,
                payload=payload or {},
            )
        return results

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def list_services(self) -> list[str]:
        """Return the names of all registered services.

        Returns:
            Sorted list of service names.
        """
        return sorted(self._services.keys())

    def __repr__(self) -> str:
        return (
            f"ServiceBus(name={self._name!r}, "
            f"services={len(self._services)}, "
            f"requests={self._request_count}, "
            f"errors={self._error_count})"
        )
