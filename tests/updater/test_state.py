"""Tests for file_organizer.updater.state module.

Covers UpdateState.last_checked_at, due, UpdateStateStore.load, save,
record_check, and state file persistence.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.updater.state import UpdateState, UpdateStateStore

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# UpdateState
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateState:
    """Test UpdateState dataclass."""

    def test_defaults(self):
        state = UpdateState()
        assert state.last_checked == ""
        assert state.last_version == ""

    def test_with_values(self):
        state = UpdateState(
            last_checked="2024-01-15T14:30:45+00:00",
            last_version="2.0.0",
        )
        assert state.last_checked == "2024-01-15T14:30:45+00:00"
        assert state.last_version == "2.0.0"


# ---------------------------------------------------------------------------
# UpdateState.last_checked_at
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateStateLastCheckedAt:
    """Test UpdateState.last_checked_at method."""

    def test_empty_last_checked(self):
        state = UpdateState()
        assert state.last_checked_at() is None

    def test_valid_iso_timestamp(self):
        timestamp = "2024-01-15T14:30:45+00:00"
        state = UpdateState(last_checked=timestamp)
        result = state.last_checked_at()
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_iso_with_z_suffix(self):
        timestamp = "2024-01-15T14:30:45Z"
        state = UpdateState(last_checked=timestamp)
        result = state.last_checked_at()
        assert result is not None
        assert result.year == 2024

    def test_invalid_timestamp(self):
        state = UpdateState(last_checked="not-a-timestamp")
        assert state.last_checked_at() is None

    def test_malformed_date(self):
        state = UpdateState(last_checked="2024-13-45T99:99:99Z")
        assert state.last_checked_at() is None


# ---------------------------------------------------------------------------
# UpdateState.due
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateStateDue:
    """Test UpdateState.due method."""

    def test_no_previous_check(self):
        state = UpdateState()
        assert state.due(interval_hours=24) is True

    def test_due_if_interval_zero(self):
        """Zero interval means always due."""
        state = UpdateState(last_checked="2024-01-01T00:00:00Z")
        assert state.due(interval_hours=0) is True

    def test_due_if_interval_negative(self):
        """Negative interval means always due."""
        state = UpdateState(last_checked="2024-01-01T00:00:00Z")
        assert state.due(interval_hours=-1) is True

    def test_due_after_interval_elapsed(self):
        now = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)
        last_check = datetime(2024, 1, 13, 14, 0, 0, tzinfo=UTC)
        state = UpdateState(last_checked=last_check.isoformat())
        # 2 days have passed, interval is 24 hours, so due
        assert state.due(interval_hours=24, now=now) is True

    def test_not_due_before_interval_elapsed(self):
        now = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)
        last_check = datetime(2024, 1, 15, 13, 0, 0, tzinfo=UTC)
        state = UpdateState(last_checked=last_check.isoformat())
        # Only 1 hour has passed, interval is 24 hours, so not due
        assert state.due(interval_hours=24, now=now) is False

    def test_due_exactly_at_interval_boundary(self):
        now = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)
        last_check = datetime(2024, 1, 14, 14, 0, 0, tzinfo=UTC)
        state = UpdateState(last_checked=last_check.isoformat())
        # Exactly 24 hours have passed, so due
        assert state.due(interval_hours=24, now=now) is True

    def test_invalid_timestamp_treated_as_due(self):
        state = UpdateState(last_checked="invalid")
        assert state.due(interval_hours=24) is True


# ---------------------------------------------------------------------------
# UpdateStateStore.init
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateStateStoreInit:
    """Test UpdateStateStore initialization."""

    def test_default_path(self):
        store = UpdateStateStore()
        assert store.state_path.name == "update_state.json"

    def test_custom_path(self, tmp_path):
        custom_path = tmp_path / "custom_state.json"
        store = UpdateStateStore(state_path=custom_path)
        assert store.state_path == custom_path

    def test_string_path_conversion(self, tmp_path):
        store = UpdateStateStore(state_path=str(tmp_path / "state.json"))
        assert isinstance(store.state_path, Path)


# ---------------------------------------------------------------------------
# UpdateStateStore.load
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateStateStoreLoad:
    """Test UpdateStateStore.load method."""

    def test_load_nonexistent_file(self, tmp_path):
        store = UpdateStateStore(state_path=tmp_path / "nonexistent.json")
        state = store.load()
        assert state.last_checked == ""
        assert state.last_version == ""

    def test_load_valid_file(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "last_checked": "2024-01-15T14:30:45Z",
                    "last_version": "2.0.0",
                }
            )
        )
        store = UpdateStateStore(state_path=state_file)
        state = store.load()
        assert state.last_checked == "2024-01-15T14:30:45Z"
        assert state.last_version == "2.0.0"

    def test_load_invalid_json(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text("not valid json {")
        store = UpdateStateStore(state_path=state_file)
        state = store.load()
        assert state.last_checked == ""
        assert state.last_version == ""

    def test_load_non_dict_json(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(["array", "not", "dict"]))
        store = UpdateStateStore(state_path=state_file)
        state = store.load()
        assert state.last_checked == ""
        assert state.last_version == ""

    def test_load_partial_fields(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"last_checked": "2024-01-15T14:30:45Z"}))
        store = UpdateStateStore(state_path=state_file)
        state = store.load()
        assert state.last_checked == "2024-01-15T14:30:45Z"
        assert state.last_version == ""

    def test_load_with_extra_fields(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "last_checked": "2024-01-15T14:30:45Z",
                    "last_version": "2.0.0",
                    "extra_field": "ignored",
                }
            )
        )
        store = UpdateStateStore(state_path=state_file)
        state = store.load()
        assert state.last_checked == "2024-01-15T14:30:45Z"
        assert state.last_version == "2.0.0"


# ---------------------------------------------------------------------------
# UpdateStateStore.save
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateStateStoreSave:
    """Test UpdateStateStore.save method."""

    def test_save_creates_file(self, tmp_path):
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        state = UpdateState(
            last_checked="2024-01-15T14:30:45Z",
            last_version="2.0.0",
        )
        store.save(state)
        assert state_file.exists()

    def test_save_creates_parent_directories(self, tmp_path):
        state_file = tmp_path / "nested" / "dir" / "state.json"
        store = UpdateStateStore(state_path=state_file)
        state = UpdateState(
            last_checked="2024-01-15T14:30:45Z",
            last_version="2.0.0",
        )
        store.save(state)
        assert state_file.exists()
        assert state_file.parent.exists()

    def test_save_content_is_valid_json(self, tmp_path):
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        state = UpdateState(
            last_checked="2024-01-15T14:30:45Z",
            last_version="2.0.0",
        )
        store.save(state)
        content = state_file.read_text()
        data = json.loads(content)
        assert data["last_checked"] == "2024-01-15T14:30:45Z"
        assert data["last_version"] == "2.0.0"

    def test_save_overwrites_existing(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"last_version": "1.0.0"}))
        store = UpdateStateStore(state_path=state_file)
        state = UpdateState(
            last_checked="2024-01-15T14:30:45Z",
            last_version="2.0.0",
        )
        store.save(state)
        data = json.loads(state_file.read_text())
        assert data["last_version"] == "2.0.0"

    def test_save_empty_state(self, tmp_path):
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        state = UpdateState()
        store.save(state)
        data = json.loads(state_file.read_text())
        assert data["last_checked"] == ""
        assert data["last_version"] == ""


# ---------------------------------------------------------------------------
# UpdateStateStore.record_check
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateStateStoreRecordCheck:
    """Test UpdateStateStore.record_check method."""

    def test_record_check_with_explicit_time(self, tmp_path):
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        now = datetime(2024, 1, 15, 14, 30, 45, tzinfo=UTC)
        state = store.record_check("2.0.0", now=now)
        assert state.last_version == "2.0.0"
        assert state.last_checked is not None
        assert "2024-01-15" in state.last_checked

    def test_record_check_saves_to_file(self, tmp_path):
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        now = datetime(2024, 1, 15, 14, 30, 45, tzinfo=UTC)
        store.record_check("2.0.0", now=now)
        # Reload and verify
        loaded_state = store.load()
        assert loaded_state.last_version == "2.0.0"

    def test_record_check_uses_current_time_if_not_provided(self, tmp_path):
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        state = store.record_check("2.0.0")
        assert state.last_checked is not None
        # Should be roughly recent
        parsed = state.last_checked_at()
        assert parsed is not None
        now = datetime.now(UTC)
        assert abs((now - parsed).total_seconds()) < 5

    def test_record_check_multiple_times(self, tmp_path):
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        now1 = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)
        state1 = store.record_check("1.0.0", now=now1)
        assert state1.last_version == "1.0.0"
        now2 = datetime(2024, 1, 16, 14, 0, 0, tzinfo=UTC)
        state2 = store.record_check("2.0.0", now=now2)
        assert state2.last_version == "2.0.0"
        # Verify only latest is persisted
        loaded = store.load()
        assert loaded.last_version == "2.0.0"


# ---------------------------------------------------------------------------
# Atomic write and fsync
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateStateStoreAtomicWrite:
    """Test atomic write with fsync in UpdateStateStore.save."""

    def test_save_atomic_write(self, tmp_path):
        """Verify save uses temp file + replace (atomic write pattern)."""
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        state = UpdateState(last_checked="2024-01-15T14:30:45Z", last_version="2.0.0")
        store.save(state)
        # Verify data is correct
        data = json.loads(state_file.read_text())
        assert data["last_checked"] == "2024-01-15T14:30:45Z"
        assert data["last_version"] == "2.0.0"
        # Verify no temp file left behind
        assert not state_file.with_suffix(".tmp").exists()

    def test_save_calls_fsync(self, tmp_path):
        """Verify os.fsync is called during save."""
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        state = UpdateState(last_checked="2024-01-15T14:30:45Z", last_version="2.0.0")
        with patch("os.fsync") as mock_fsync:
            store.save(state)
            # fsync is called twice: once on file, once on directory
            assert mock_fsync.call_count == 2
        # Verify save still works correctly
        data = json.loads(state_file.read_text())
        assert data["last_version"] == "2.0.0"

    def test_save_cleanup_on_error(self, tmp_path):
        """Verify temp file is cleaned up when write fails."""
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        state = UpdateState(last_checked="2024-01-15T14:30:45Z", last_version="2.0.0")
        with patch("builtins.open", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                store.save(state)
        # Verify no temp file left behind
        assert not state_file.with_suffix(".tmp").exists()

    def test_save_cleanup_when_replace_fails_and_temp_exists(self, tmp_path):
        """Verify temp file is cleaned up when os.replace fails but temp was written."""
        state_file = tmp_path / "state.json"
        store = UpdateStateStore(state_path=state_file)
        state = UpdateState(last_checked="2024-01-15T14:30:45Z", last_version="2.0.0")
        with patch("os.replace", side_effect=OSError("replace failed")):
            with pytest.raises(OSError, match="replace failed"):
                store.save(state)
        # Temp file should be cleaned up by the except handler (line 91)
        assert not state_file.with_suffix(".tmp").exists()
