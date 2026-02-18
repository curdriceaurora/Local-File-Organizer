"""Event type definitions for the Redis Streams event system.

Defines the core event types and data structures used throughout
the event-driven architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(Enum):
    """Types of events emitted by the file organizer system."""

    FILE_CREATED = "file.created"
    FILE_MODIFIED = "file.modified"
    FILE_DELETED = "file.deleted"
    FILE_ORGANIZED = "file.organized"
    SCAN_STARTED = "scan.started"
    SCAN_COMPLETED = "scan.completed"
    ERROR = "error"


@dataclass(frozen=True)
class FileEvent:
    """Event representing a file system operation.

    Attributes:
        event_type: The type of file event.
        file_path: Absolute path to the affected file.
        metadata: Additional metadata about the event.
        timestamp: UTC timestamp when the event occurred.
    """

    event_type: EventType
    file_path: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, str]:
        """Serialize the event to a dictionary suitable for Redis Streams.

        Returns:
            Dictionary with string keys and string values for Redis.
        """
        import json

        return {
            "event_type": self.event_type.value,
            "file_path": self.file_path,
            "metadata": json.dumps(self.metadata),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> FileEvent:
        """Deserialize a FileEvent from a Redis Streams message.

        Args:
            data: Dictionary with string keys and values from Redis.

        Returns:
            Reconstructed FileEvent instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If event_type is not a valid EventType.
        """
        import json

        return cls(
            event_type=EventType(data["event_type"]),
            file_path=data["file_path"],
            metadata=json.loads(data.get("metadata", "{}")),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass(frozen=True)
class ScanEvent:
    """Event representing a scan operation.

    Attributes:
        scan_id: Unique identifier for the scan.
        status: Current status of the scan (e.g., 'started', 'completed').
        stats: Statistics about the scan operation.
        timestamp: UTC timestamp when the event occurred.
    """

    scan_id: str
    status: str
    stats: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, str]:
        """Serialize the scan event to a dictionary for Redis Streams.

        Returns:
            Dictionary with string keys and string values for Redis.
        """
        import json

        return {
            "event_type": "scan",
            "scan_id": self.scan_id,
            "status": self.status,
            "stats": json.dumps(self.stats),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> ScanEvent:
        """Deserialize a ScanEvent from a Redis Streams message.

        Args:
            data: Dictionary with string keys and values from Redis.

        Returns:
            Reconstructed ScanEvent instance.

        Raises:
            KeyError: If required fields are missing.
        """
        import json

        return cls(
            scan_id=data["scan_id"],
            status=data["status"],
            stats=json.loads(data.get("stats", "{}")),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
