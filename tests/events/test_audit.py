"""
Unit tests for AuditLogger.

Tests JSON-based audit logging including log_event, query_audit_log,
and filtering. Uses temporary files for all I/O.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.events.audit import AuditEntry, AuditFilter, AuditLogger
from file_organizer.events.stream import Event

# --- Fixtures ---


@pytest.fixture
def tmp_log_path(tmp_path: Path) -> Path:
    """Create a temporary log file path."""
    return tmp_path / "audit" / "events.jsonl"


@pytest.fixture
def audit_logger(tmp_log_path: Path) -> AuditLogger:
    """Create an AuditLogger with a temporary log path."""
    return AuditLogger(tmp_log_path)


@pytest.fixture
def sample_event() -> Event:
    """Create a sample Event for testing."""
    return Event(
        id="1704067200000-0",
        stream="fileorg:file-events",
        data={"event_type": "file.created", "file_path": "/test/a.txt"},
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )


# --- AuditEntry Tests ---


@pytest.mark.unit
class TestAuditEntry:
    """Tests for the AuditEntry dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        entry = AuditEntry(
            timestamp=now,
            event_id="1-0",
            stream="test:stream",
            action="consumed",
            metadata={"key": "value"},
        )

        result = entry.to_dict()

        assert result["timestamp"] == "2024-01-15T12:00:00+00:00"
        assert result["event_id"] == "1-0"
        assert result["stream"] == "test:stream"
        assert result["action"] == "consumed"
        assert result["metadata"] == {"key": "value"}

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "timestamp": "2024-01-15T12:00:00+00:00",
            "event_id": "1-0",
            "stream": "test:stream",
            "action": "consumed",
            "metadata": {"key": "value"},
        }

        entry = AuditEntry.from_dict(data)

        assert entry.event_id == "1-0"
        assert entry.stream == "test:stream"
        assert entry.action == "consumed"
        assert entry.metadata == {"key": "value"}

    def test_from_dict_without_metadata(self):
        """Test deserialization without metadata field."""
        data = {
            "timestamp": "2024-01-15T12:00:00+00:00",
            "event_id": "1-0",
            "stream": "test:stream",
            "action": "consumed",
        }

        entry = AuditEntry.from_dict(data)
        assert entry.metadata == {}

    def test_roundtrip(self):
        """Test serialization roundtrip preserves data."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        original = AuditEntry(
            timestamp=now,
            event_id="1-0",
            stream="test:stream",
            action="consumed",
            metadata={"key": "value"},
        )

        restored = AuditEntry.from_dict(original.to_dict())

        assert restored.event_id == original.event_id
        assert restored.stream == original.stream
        assert restored.action == original.action
        assert restored.metadata == original.metadata


# --- AuditLogger Tests ---


@pytest.mark.unit
class TestAuditLoggerInit:
    """Tests for AuditLogger initialization."""

    def test_init(self, tmp_log_path: Path):
        """Test basic initialization."""
        logger = AuditLogger(tmp_log_path)
        assert logger.log_path == tmp_log_path

    def test_repr(self, audit_logger: AuditLogger):
        """Test string representation."""
        result = repr(audit_logger)
        assert "AuditLogger" in result
        assert "events.jsonl" in result


@pytest.mark.unit
class TestLogEvent:
    """Tests for the log_event method."""

    def test_log_event_creates_entry(self, audit_logger: AuditLogger, sample_event: Event):
        """Test logging an event creates an audit entry."""
        entry = audit_logger.log_event(sample_event, "consumed")

        assert entry.event_id == "1704067200000-0"
        assert entry.stream == "fileorg:file-events"
        assert entry.action == "consumed"
        assert entry.metadata == sample_event.data

    def test_log_event_creates_file(self, audit_logger: AuditLogger, sample_event: Event):
        """Test that log_event creates the log file."""
        assert not audit_logger.log_path.exists()

        audit_logger.log_event(sample_event, "consumed")

        assert audit_logger.log_path.exists()

    def test_log_event_creates_parent_dirs(self, tmp_path: Path, sample_event: Event):
        """Test that log_event creates parent directories."""
        deep_path = tmp_path / "a" / "b" / "c" / "audit.jsonl"
        logger = AuditLogger(deep_path)

        logger.log_event(sample_event, "consumed")

        assert deep_path.exists()

    def test_log_event_appends_to_file(self, audit_logger: AuditLogger, sample_event: Event):
        """Test that multiple events are appended."""
        audit_logger.log_event(sample_event, "consumed")
        audit_logger.log_event(sample_event, "replayed")

        lines = audit_logger.log_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_log_event_writes_valid_json(self, audit_logger: AuditLogger, sample_event: Event):
        """Test that each line is valid JSON."""
        audit_logger.log_event(sample_event, "consumed")

        line = audit_logger.log_path.read_text().strip()
        data = json.loads(line)

        assert data["event_id"] == "1704067200000-0"
        assert data["action"] == "consumed"

    def test_log_event_different_actions(self, audit_logger: AuditLogger, sample_event: Event):
        """Test logging different action types."""
        actions = ["published", "consumed", "replayed", "failed"]
        for action in actions:
            audit_logger.log_event(sample_event, action)

        entries = audit_logger.query_audit_log()
        logged_actions = [e.action for e in entries]
        assert logged_actions == actions


@pytest.mark.unit
class TestQueryAuditLog:
    """Tests for the query_audit_log method."""

    def test_query_all_entries(self, audit_logger: AuditLogger, sample_event: Event):
        """Test querying all entries without filters."""
        audit_logger.log_event(sample_event, "consumed")
        audit_logger.log_event(sample_event, "replayed")

        entries = audit_logger.query_audit_log()

        assert len(entries) == 2

    def test_query_with_action_filter(self, audit_logger: AuditLogger, sample_event: Event):
        """Test filtering by action."""
        audit_logger.log_event(sample_event, "consumed")
        audit_logger.log_event(sample_event, "replayed")
        audit_logger.log_event(sample_event, "consumed")

        entries = audit_logger.query_audit_log(AuditFilter(action="consumed"))

        assert len(entries) == 2
        assert all(e.action == "consumed" for e in entries)

    def test_query_with_stream_filter(
        self,
        audit_logger: AuditLogger,
    ):
        """Test filtering by stream."""
        event_a = Event(
            id="1-0",
            stream="stream-a",
            data={},
            timestamp=datetime.now(UTC),
        )
        event_b = Event(
            id="2-0",
            stream="stream-b",
            data={},
            timestamp=datetime.now(UTC),
        )

        audit_logger.log_event(event_a, "consumed")
        audit_logger.log_event(event_b, "consumed")

        entries = audit_logger.query_audit_log(AuditFilter(stream="stream-a"))

        assert len(entries) == 1
        assert entries[0].stream == "stream-a"

    def test_query_with_event_id_filter(self, audit_logger: AuditLogger, sample_event: Event):
        """Test filtering by event ID."""
        other_event = Event(
            id="9999-0",
            stream="fileorg:file-events",
            data={},
            timestamp=datetime.now(UTC),
        )

        audit_logger.log_event(sample_event, "consumed")
        audit_logger.log_event(other_event, "consumed")

        entries = audit_logger.query_audit_log(AuditFilter(event_id="1704067200000-0"))

        assert len(entries) == 1
        assert entries[0].event_id == "1704067200000-0"

    def test_query_with_time_range_filter(self, audit_logger: AuditLogger, tmp_log_path: Path):
        """Test filtering by time range."""
        # Write entries with known timestamps directly
        entries_data = [
            {
                "timestamp": "2024-01-01T10:00:00+00:00",
                "event_id": "1-0",
                "stream": "s",
                "action": "consumed",
                "metadata": {},
            },
            {
                "timestamp": "2024-01-01T12:00:00+00:00",
                "event_id": "2-0",
                "stream": "s",
                "action": "consumed",
                "metadata": {},
            },
            {
                "timestamp": "2024-01-01T14:00:00+00:00",
                "event_id": "3-0",
                "stream": "s",
                "action": "consumed",
                "metadata": {},
            },
        ]
        tmp_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_log_path, "w") as f:
            for entry in entries_data:
                f.write(json.dumps(entry) + "\n")

        result = audit_logger.query_audit_log(
            AuditFilter(
                start_time=datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC),
                end_time=datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC),
            )
        )

        assert len(result) == 1
        assert result[0].event_id == "2-0"

    def test_query_nonexistent_file(self, audit_logger: AuditLogger):
        """Test querying when log file doesn't exist."""
        entries = audit_logger.query_audit_log()
        assert entries == []

    def test_query_skips_malformed_lines(self, audit_logger: AuditLogger, tmp_log_path: Path):
        """Test that malformed JSON lines are skipped."""
        tmp_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_log_path, "w") as f:
            f.write(
                '{"timestamp":"2024-01-01T00:00:00+00:00","event_id":"1-0","stream":"s","action":"ok","metadata":{}}\n'
            )
            f.write("not valid json\n")
            f.write(
                '{"timestamp":"2024-01-02T00:00:00+00:00","event_id":"2-0","stream":"s","action":"ok","metadata":{}}\n'
            )

        entries = audit_logger.query_audit_log()
        assert len(entries) == 2

    def test_query_combined_filters(self, audit_logger: AuditLogger, sample_event: Event):
        """Test combining multiple filters."""
        other_event = Event(
            id="9999-0",
            stream="other-stream",
            data={},
            timestamp=datetime.now(UTC),
        )

        audit_logger.log_event(sample_event, "consumed")
        audit_logger.log_event(sample_event, "replayed")
        audit_logger.log_event(other_event, "consumed")

        entries = audit_logger.query_audit_log(
            AuditFilter(
                stream="fileorg:file-events",
                action="consumed",
            )
        )

        assert len(entries) == 1
        assert entries[0].event_id == "1704067200000-0"
        assert entries[0].action == "consumed"


@pytest.mark.unit
class TestAuditLoggerUtilities:
    """Tests for utility methods."""

    def test_get_entry_count(self, audit_logger: AuditLogger, sample_event: Event):
        """Test counting entries."""
        assert audit_logger.get_entry_count() == 0

        audit_logger.log_event(sample_event, "consumed")
        audit_logger.log_event(sample_event, "replayed")

        assert audit_logger.get_entry_count() == 2

    def test_clear_removes_log(self, audit_logger: AuditLogger, sample_event: Event):
        """Test clearing the audit log."""
        audit_logger.log_event(sample_event, "consumed")
        assert audit_logger.log_path.exists()

        audit_logger.clear()
        assert not audit_logger.log_path.exists()

    def test_clear_nonexistent_file(self, audit_logger: AuditLogger):
        """Test clearing when log file doesn't exist."""
        audit_logger.clear()  # Should not raise

    def test_log_after_clear(self, audit_logger: AuditLogger, sample_event: Event):
        """Test logging after clearing starts fresh."""
        audit_logger.log_event(sample_event, "consumed")
        audit_logger.clear()
        audit_logger.log_event(sample_event, "replayed")

        entries = audit_logger.query_audit_log()
        assert len(entries) == 1
        assert entries[0].action == "replayed"
