"""Audit logging for the Redis Streams event system.

Provides local JSON-based audit logging for tracking event actions.
Privacy-first design with no external database dependencies.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from file_organizer.events.stream import Event

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """A single audit log entry.

    Attributes:
        timestamp: UTC timestamp when the audit entry was created.
        event_id: The Redis message ID of the audited event.
        stream: The stream the event belongs to.
        action: The action performed (e.g., 'published', 'consumed',
            'replayed', 'failed').
        metadata: Additional context about the action.
    """

    timestamp: datetime
    event_id: str
    stream: str
    action: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the audit entry to a JSON-compatible dictionary.

        Returns:
            Dictionary with all fields serialized to JSON-safe types.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "stream": self.stream,
            "action": self.action,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        """Deserialize an AuditEntry from a dictionary.

        Args:
            data: Dictionary with audit entry fields.

        Returns:
            Reconstructed AuditEntry instance.
        """
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_id=data["event_id"],
            stream=data["stream"],
            action=data["action"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class AuditFilter:
    """Filter criteria for querying audit logs.

    All fields are optional. When multiple fields are set, they are
    combined with AND logic.

    Attributes:
        stream: Filter by stream name.
        action: Filter by action type.
        event_id: Filter by specific event ID.
        start_time: Filter entries on or after this time.
        end_time: Filter entries on or before this time.
    """

    stream: str | None = None
    action: str | None = None
    event_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class AuditLogger:
    """JSON file-based audit logger for event system actions.

    Stores audit entries as newline-delimited JSON (NDJSON) in a local
    file. Designed for privacy-first operation with no external
    database dependencies.

    Example:
        >>> audit = AuditLogger(Path("/var/log/events-audit.jsonl"))
        >>> audit.log_event(event, "consumed")
        >>> entries = audit.query_audit_log(
        ...     AuditFilter(action="consumed")
        ... )
    """

    def __init__(self, log_path: Path) -> None:
        """Initialize the audit logger.

        Args:
            log_path: Path to the NDJSON audit log file. Parent
                directories will be created if they don't exist.
        """
        self._log_path = log_path

    @property
    def log_path(self) -> Path:
        """The path to the audit log file."""
        return self._log_path

    def log_event(self, event: Event, action: str) -> AuditEntry:
        """Record an audit entry for an event action.

        Creates an AuditEntry and appends it to the log file as a
        JSON line. The parent directory is created if needed.

        Args:
            event: The event being audited.
            action: The action being recorded (e.g., 'published',
                'consumed', 'replayed', 'failed').

        Returns:
            The created AuditEntry.

        Raises:
            OSError: If the log file cannot be written.
        """
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            event_id=event.id,
            stream=event.stream,
            action=action,
            metadata=dict(event.data),
        )

        self._append_entry(entry)

        logger.debug(
            "Audit: %s event '%s' on stream '%s'",
            action,
            event.id,
            event.stream,
        )

        return entry

    def query_audit_log(self, filters: AuditFilter | None = None) -> list[AuditEntry]:
        """Query the audit log with optional filters.

        Reads the entire log file and applies filters in memory.
        For large logs, consider using start_time/end_time filters
        to limit results.

        Args:
            filters: Optional filter criteria. If None, all entries
                are returned.

        Returns:
            List of matching AuditEntry objects, ordered by timestamp.
            Returns empty list if the log file doesn't exist.
        """
        if not self._log_path.exists():
            return []

        entries: list[AuditEntry] = []

        try:
            with open(self._log_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entry = AuditEntry.from_dict(data)
                        if self._matches_filter(entry, filters):
                            entries.append(entry)
                    except (json.JSONDecodeError, KeyError):
                        logger.warning(
                            "Skipping malformed audit log line: %s",
                            line[:100],
                        )
                        continue
        except OSError:
            logger.error(
                "Failed to read audit log at '%s'",
                self._log_path,
                exc_info=True,
            )
            return []

        return entries

    def get_entry_count(self) -> int:
        """Get the total number of entries in the audit log.

        Returns:
            Number of valid entries, or 0 if file doesn't exist.
        """
        if not self._log_path.exists():
            return 0

        count = 0
        try:
            with open(self._log_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1
        except OSError:
            return 0
        return count

    def clear(self) -> None:
        """Clear the audit log file.

        Removes the log file entirely. A new file will be created
        on the next log_event call.
        """
        if self._log_path.exists():
            self._log_path.unlink()
            logger.info("Cleared audit log at '%s'", self._log_path)

    def _append_entry(self, entry: AuditEntry) -> None:
        """Append an audit entry to the log file.

        Creates parent directories if they don't exist.

        Args:
            entry: The audit entry to append.
        """
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    @staticmethod
    def _matches_filter(entry: AuditEntry, filters: AuditFilter | None) -> bool:
        """Check if an audit entry matches the given filters.

        Args:
            entry: The audit entry to check.
            filters: Filter criteria. If None, always matches.

        Returns:
            True if the entry matches all filter criteria.
        """
        if filters is None:
            return True

        if filters.stream is not None and entry.stream != filters.stream:
            return False

        if filters.action is not None and entry.action != filters.action:
            return False

        if filters.event_id is not None and entry.event_id != filters.event_id:
            return False

        if filters.start_time is not None and entry.timestamp < filters.start_time:
            return False

        if filters.end_time is not None and entry.timestamp > filters.end_time:
            return False

        return True

    def __repr__(self) -> str:
        """String representation."""
        return f"AuditLogger(path={self._log_path!r})"
