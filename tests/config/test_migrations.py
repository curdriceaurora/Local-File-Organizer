"""Tests for the config-schema migration registry (config/migrations.py)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from file_organizer.config import migrations
from file_organizer.config.migrations import (
    Migration,
    _version_key,
    compare_versions,
    migrate_to_current,
)


@contextmanager
def _capture_migration_logs(level: int) -> Iterator[list[logging.LogRecord]]:
    """Collect migration logger records without inheriting leaked logging state."""
    target = logging.getLogger("file_organizer.config.migrations")
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collector(level=level)
    prev_disable = logging.root.manager.disable
    prev_level = target.level
    prev_disabled = target.disabled
    logging.disable(logging.NOTSET)
    target.addHandler(handler)
    target.setLevel(level)
    target.disabled = False
    try:
        yield records
    finally:
        target.removeHandler(handler)
        target.setLevel(prev_level)
        target.disabled = prev_disabled
        logging.disable(prev_disable)


# ---------------------------------------------------------------------------
# _version_key
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVersionKey:
    """Tests for dotted-version → ordering-tuple parsing."""

    def test_simple_numeric_version(self) -> None:
        assert _version_key("1.5") == (1, 5)

    def test_numeric_ordering_beats_lexicographic(self) -> None:
        # "10.0" < "2.0" lexicographically; numerically it must be greater.
        assert _version_key("10.0") > _version_key("2.0")

    def test_trailing_zeros_trimmed(self) -> None:
        assert _version_key("1.0") == _version_key("1.0.0")

    def test_all_zero_version_collapses(self) -> None:
        assert _version_key("0.0.0") == (0,)

    def test_midstream_zeros_preserved(self) -> None:
        assert _version_key("1.0.1") == (1, 0, 1)
        assert _version_key("1.0.1") > _version_key("1.0")

    def test_non_numeric_version_falls_back_to_zero(self) -> None:
        with _capture_migration_logs(logging.WARNING) as records:
            assert _version_key("garbage") == (0,)
        assert any("Non-numeric config version" in record.getMessage() for record in records)

    def test_partially_numeric_version_falls_back_to_zero(self) -> None:
        assert _version_key("1.beta") == (0,)


# ---------------------------------------------------------------------------
# compare_versions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCompareVersions:
    """Tests for the public three-way version comparison."""

    def test_less_than(self) -> None:
        assert compare_versions("0.5", "1.0") == -1

    def test_equal(self) -> None:
        assert compare_versions("1.0", "1.0") == 0

    def test_greater_than(self) -> None:
        assert compare_versions("2.0", "1.0") == 1

    def test_numeric_ordering(self) -> None:
        assert compare_versions("10.0", "2.0") == 1

    def test_equivalent_textual_variants_compare_equal(self) -> None:
        assert compare_versions("1.0", "1.0.0") == 0


# ---------------------------------------------------------------------------
# migrate_to_current
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMigrateToCurrent:
    """Tests for the registry walker."""

    def test_equal_versions_short_circuit(self) -> None:
        data = {"key": "value"}
        result = migrate_to_current(data, from_version="1.0", to_version="1.0")
        assert result is data

    def test_textually_different_equal_versions_short_circuit(self) -> None:
        data = {"key": "value"}
        result = migrate_to_current(data, from_version="1.0.0", to_version="1.0")
        assert result is data

    def test_newer_on_disk_version_returned_unchanged(self) -> None:
        # Future-version configs cannot be migrated; loaded best-effort.
        data = {"key": "value"}
        result = migrate_to_current(data, from_version="2.0", to_version="1.0")
        assert result is data

    def test_single_migration_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def rename_field(data: dict[str, object]) -> dict[str, object]:
            data["new_name"] = data.pop("old_name")
            return data

        monkeypatch.setattr(
            migrations,
            "MIGRATIONS",
            {"0.5": Migration(to_version="1.0", transform=rename_field)},
        )
        result = migrate_to_current({"old_name": 42}, from_version="0.5", to_version="1.0")
        assert result == {"new_name": 42}

    def test_migrations_chain_in_sequence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        order: list[str] = []

        def step_a(data: dict[str, object]) -> dict[str, object]:
            order.append("0.5->1.0")
            return {**data, "a": True}

        def step_b(data: dict[str, object]) -> dict[str, object]:
            order.append("1.0->1.5")
            return {**data, "b": True}

        monkeypatch.setattr(
            migrations,
            "MIGRATIONS",
            {
                "0.5": Migration(to_version="1.0", transform=step_a),
                "1.0": Migration(to_version="1.5", transform=step_b),
            },
        )
        result = migrate_to_current({}, from_version="0.5", to_version="1.5")
        assert order == ["0.5->1.0", "1.0->1.5"]
        assert result == {"a": True, "b": True}

    def test_registry_gap_warns_and_returns_data_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            migrations,
            "MIGRATIONS",
            {"2.0": Migration(to_version="3.0", transform=lambda d: d)},
        )
        data = {"key": "value"}
        with _capture_migration_logs(logging.WARNING) as records:
            result = migrate_to_current(data, from_version="0.5", to_version="3.0")
        assert result is data
        assert any("No migration registered" in record.getMessage() for record in records)

    def test_chain_stops_at_gap_after_partial_progress(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 0.5 -> 1.0 exists, but nothing from 1.0 onwards: the walker
        # applies the first step, then bails with a gap warning.
        monkeypatch.setattr(
            migrations,
            "MIGRATIONS",
            {"0.5": Migration(to_version="1.0", transform=lambda d: {**d, "a": 1})},
        )
        with _capture_migration_logs(logging.WARNING) as records:
            result = migrate_to_current({}, from_version="0.5", to_version="2.0")
        assert result == {"a": 1}
        assert any("No migration registered" in record.getMessage() for record in records)

    def test_non_increasing_target_stops_walk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            migrations,
            "MIGRATIONS",
            {"1.0": Migration(to_version="1.0", transform=lambda d: d)},
        )
        data = {"key": "value"}
        with _capture_migration_logs(logging.ERROR) as records:
            result = migrate_to_current(data, from_version="1.0", to_version="2.0")
        assert result is data
        assert any("non-increasing target" in record.getMessage() for record in records)

    def test_failing_transform_logs_and_reraises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken(data: dict[str, object]) -> dict[str, object]:
            raise ValueError("boom")

        monkeypatch.setattr(
            migrations,
            "MIGRATIONS",
            {"0.5": Migration(to_version="1.0", transform=broken)},
        )
        with _capture_migration_logs(logging.ERROR) as records:
            with pytest.raises(ValueError, match="boom"):
                migrate_to_current({}, from_version="0.5", to_version="1.0")
        assert any("migration from version 0.5 failed" in record.getMessage() for record in records)

    def test_safety_limit_exhaustion_warns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The safety limit is computed once (len(MIGRATIONS) + 1) before the
        # walk. A transform that grows the registry mid-walk can therefore
        # outrun the limit without ever reaching the target version.
        registry: dict[str, Migration] = {}

        def make_step(src_major: int) -> Migration:
            def transform(data: dict[str, object]) -> dict[str, object]:
                nxt = src_major + 1
                registry[f"{nxt}.0"] = make_step(nxt)
                return data

            return Migration(to_version=f"{src_major + 1}.0", transform=transform)

        registry["1.0"] = make_step(1)
        monkeypatch.setattr(migrations, "MIGRATIONS", registry)
        data = {"key": "value"}
        with _capture_migration_logs(logging.WARNING) as records:
            result = migrate_to_current(data, from_version="1.0", to_version="99.0")
        assert result is data
        assert any("did not reach target version" in record.getMessage() for record in records)
