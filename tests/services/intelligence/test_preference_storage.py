"""Protocol-contract tests for ``preference_storage`` (Epic D / D5).

Tracks: issue #157 (Hardening Epic D, item D5).

Test contract:
- One parametrized class runs against both ``InMemoryPreferenceStorage()``
  and ``SqlitePreferenceStorage(tmp_path / "test.db")``.
- Each test asserts the published shape of the Protocol — never reaches
  into private dicts, never assumes a specific implementation.
- ``PreferenceTracker(storage=mock_storage)`` test asserts ``track_correction``
  delegates to ``save_preference`` / ``save_correction`` with the right payload
  (mock-call-args, not just call_count — per anti-pattern T3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.services.intelligence.preference_storage import (
    InMemoryPreferenceStorage,
    PreferenceStorage,
    SqlitePreferenceStorage,
)
from file_organizer.services.intelligence.preference_tracker import (
    Correction,
    CorrectionType,
    Preference,
    PreferenceMetadata,
    PreferenceTracker,
    PreferenceType,
)

# Marker rationale (CodeRabbit on PR #207): the original triple
# ``[unit, ci, integration]`` would let both the ``unit`` and
# ``not integration`` lanes pull these in. Drop ``unit`` since these
# tests exercise the SQLite backend end-to-end (real file I/O); keep
# ``ci`` so they run in the PR CI lane and ``integration`` so they
# count toward integration coverage of preference_storage.py.
pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_preference(
    preference_type: PreferenceType = PreferenceType.FOLDER_MAPPING,
    key: str = "file_move|.pdf|Documents",
    # Default ``value`` is a generic relative-string folder name (not ``/home/...``)
    # so the G2 hardcoded-path rail (which scans test files for ``/home/`` /
    # ``/tmp/`` / ``/Users/`` literals) stays clean.
    value: str | dict[str, str] = "Documents",
    confidence: float = 0.5,
    frequency: int = 1,
) -> Preference:
    now = datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
    return Preference(
        preference_type=preference_type,
        key=key,
        value=value,
        metadata=PreferenceMetadata(
            created=now,
            updated=now,
            confidence=confidence,
            frequency=frequency,
            last_used=now,
            source="user_correction",
        ),
        context={"source_extension": ".pdf"},
    )


def _make_correction(
    source: Path,
    destination: Path,
    correction_type: CorrectionType = CorrectionType.FILE_MOVE,
) -> Correction:
    return Correction(
        correction_type=correction_type,
        source=source,
        destination=destination,
        timestamp=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
        context={},
    )


# ---------------------------------------------------------------------------
# Protocol-contract tests (parametrized over both implementations)
# ---------------------------------------------------------------------------


@pytest.fixture(params=["in_memory", "sqlite"])
def storage(request: pytest.FixtureRequest, tmp_path: Path):
    """Yield each storage implementation under test, finalized with ``close()``.

    SQLite cases hold an open connection; without the finalizer they
    leak under xdist or on Windows where the file lock blocks reuse
    (CodeRabbit on PR #207).
    """
    if request.param == "in_memory":
        s: PreferenceStorage = InMemoryPreferenceStorage()
    elif request.param == "sqlite":
        s = SqlitePreferenceStorage(tmp_path / "preferences.db")
    else:
        raise ValueError(f"Unknown storage param: {request.param}")
    try:
        yield s
    finally:
        # InMemoryPreferenceStorage doesn't define close(); only call
        # it on backends that do (currently only SQLite).
        if hasattr(s, "close"):
            s.close()


class TestPreferenceCRUD:
    """The four preference-CRUD methods round-trip through both backends."""

    def test_save_then_find_by_type_returns_dataclass(self, storage: PreferenceStorage) -> None:
        pref = _make_preference()
        storage.save_preference(pref)

        found = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
        assert len(found) == 1
        retrieved = found[0]
        assert isinstance(retrieved, Preference)
        assert retrieved.preference_type == PreferenceType.FOLDER_MAPPING
        assert retrieved.key == pref.key
        assert retrieved.value == pref.value
        assert retrieved.metadata.confidence == 0.5
        assert retrieved.metadata.frequency == 1

    def test_find_filters_by_key_when_provided(self, storage: PreferenceStorage) -> None:
        a = _make_preference(key="file_move|.pdf|Documents")
        b = _make_preference(key="file_move|.txt|Notes")
        storage.save_preference(a)
        storage.save_preference(b)

        only_pdf = storage.find_preferences(
            PreferenceType.FOLDER_MAPPING, key="file_move|.pdf|Documents"
        )
        assert len(only_pdf) == 1
        assert only_pdf[0].key == "file_move|.pdf|Documents"

    def test_find_returns_empty_for_unknown_type(self, storage: PreferenceStorage) -> None:
        result = storage.find_preferences(PreferenceType.NAMING_PATTERN)
        assert result == []

    def test_save_is_idempotent_for_same_type_and_key(self, storage: PreferenceStorage) -> None:
        # Saving the same (type, key) twice must NOT create two rows; the
        # second save updates the existing entry.
        first = _make_preference(value="/path/v1", confidence=0.5)
        storage.save_preference(first)

        second = _make_preference(value="/path/v2", confidence=0.7)
        storage.save_preference(second)

        all_prefs = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
        assert len(all_prefs) == 1
        assert all_prefs[0].value == "/path/v2"

    def test_update_confidence_success_increases_confidence(
        self, storage: PreferenceStorage
    ) -> None:
        pref = _make_preference(confidence=0.5)
        storage.save_preference(pref)

        storage.update_preference_confidence(pref, success=True)

        found = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
        assert len(found) == 1
        # Confidence increased by exactly 0.05 per the tracker rule
        assert found[0].metadata.confidence == pytest.approx(0.55, abs=0.001)

    def test_update_confidence_failure_decreases_confidence(
        self, storage: PreferenceStorage
    ) -> None:
        pref = _make_preference(confidence=0.5)
        storage.save_preference(pref)

        storage.update_preference_confidence(pref, success=False)

        found = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
        assert len(found) == 1
        assert found[0].metadata.confidence == pytest.approx(0.4, abs=0.001)

    def test_update_confidence_caps_at_floor(self, storage: PreferenceStorage) -> None:
        pref = _make_preference(confidence=0.1)
        storage.save_preference(pref)

        # Multiple failures should not push below the 0.1 floor
        storage.update_preference_confidence(pref, success=False)
        storage.update_preference_confidence(pref, success=False)

        found = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
        assert found[0].metadata.confidence >= 0.1

    def test_update_confidence_caps_at_ceiling(self, storage: PreferenceStorage) -> None:
        pref = _make_preference(confidence=0.97)
        storage.save_preference(pref)

        storage.update_preference_confidence(pref, success=True)

        found = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
        # Successful update caps at 0.98
        assert found[0].metadata.confidence <= 0.98

    def test_delete_all_clears_storage(self, storage: PreferenceStorage) -> None:
        a = _make_preference(key="a", preference_type=PreferenceType.FOLDER_MAPPING)
        b = _make_preference(key="b", preference_type=PreferenceType.NAMING_PATTERN)
        storage.save_preference(a)
        storage.save_preference(b)

        deleted = storage.delete_preferences()

        assert deleted == 2
        assert storage.find_preferences(PreferenceType.FOLDER_MAPPING) == []
        assert storage.find_preferences(PreferenceType.NAMING_PATTERN) == []

    def test_delete_by_type_only_clears_that_type(self, storage: PreferenceStorage) -> None:
        folder = _make_preference(key="a", preference_type=PreferenceType.FOLDER_MAPPING)
        naming = _make_preference(key="b", preference_type=PreferenceType.NAMING_PATTERN)
        storage.save_preference(folder)
        storage.save_preference(naming)

        deleted = storage.delete_preferences(PreferenceType.FOLDER_MAPPING)

        assert deleted == 1
        assert storage.find_preferences(PreferenceType.FOLDER_MAPPING) == []
        # The other type is untouched
        remaining = storage.find_preferences(PreferenceType.NAMING_PATTERN)
        assert len(remaining) == 1
        assert remaining[0].key == "b"


class TestCorrectionHistory:
    def test_save_correction_appears_in_get_corrections_for_file(
        self, storage: PreferenceStorage, tmp_path: Path
    ) -> None:
        src = tmp_path / "src.pdf"
        dst = tmp_path / "Documents" / "src.pdf"
        correction = _make_correction(src, dst)
        storage.save_correction(correction)

        results = storage.get_corrections_for_file(src)
        assert len(results) == 1
        assert results[0].source == src
        assert results[0].destination == dst
        assert results[0].correction_type == CorrectionType.FILE_MOVE

    def test_get_corrections_for_file_matches_destination_too(
        self, storage: PreferenceStorage, tmp_path: Path
    ) -> None:
        src = tmp_path / "old.pdf"
        dst = tmp_path / "new.pdf"
        storage.save_correction(_make_correction(src, dst))

        # Querying by destination should also find it
        by_destination = storage.get_corrections_for_file(dst)
        assert len(by_destination) == 1
        assert by_destination[0].destination == dst

    def test_get_recent_corrections_respects_limit(
        self, storage: PreferenceStorage, tmp_path: Path
    ) -> None:
        for i in range(5):
            storage.save_correction(
                _make_correction(tmp_path / f"f{i}.pdf", tmp_path / f"d{i}.pdf")
            )

        recent = storage.get_recent_corrections(limit=3)
        assert len(recent) == 3

    def test_get_corrections_for_file_returns_empty_when_unmatched(
        self, storage: PreferenceStorage, tmp_path: Path
    ) -> None:
        result = storage.get_corrections_for_file(tmp_path / "ghost.pdf")
        assert result == []

    def test_save_correction_with_non_empty_context_round_trips(
        self, storage: PreferenceStorage, tmp_path: Path
    ) -> None:
        """``correction.context`` (dict) must survive save→find round-trip.

        CodeRabbit on PR #207 noted the contract suite only exercised
        the ``context={}`` happy path, missing the metadata-binding
        behavior in ``SqlitePreferenceStorage.save_correction``.
        """
        src = tmp_path / "doc.txt"
        dst = tmp_path / "Documents" / "doc.txt"
        correction = Correction(
            correction_type=CorrectionType.CATEGORY_CHANGE,
            source=src,
            destination=dst,
            timestamp=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
            context={
                "old_category": "general",
                "new_category": "documents",
                "note": "manual override",
            },
        )
        storage.save_correction(correction)

        results = storage.get_corrections_for_file(src)
        assert len(results) == 1
        assert results[0].context == {
            "old_category": "general",
            "new_category": "documents",
            "note": "manual override",
        }


class TestDeleteByTypePreservesCorrections:
    """``delete_preferences(type)`` MUST NOT clear corrections (CodeRabbit on PR #207)."""

    def test_delete_by_type_leaves_corrections_intact(
        self, storage: PreferenceStorage, tmp_path: Path
    ) -> None:
        a = _make_preference(key="a", preference_type=PreferenceType.FOLDER_MAPPING)
        storage.save_preference(a)
        storage.save_correction(_make_correction(tmp_path / "x.txt", tmp_path / "y.txt"))

        deleted = storage.delete_preferences(PreferenceType.FOLDER_MAPPING)
        assert deleted == 1

        # Preferences gone, corrections preserved
        assert storage.find_preferences(PreferenceType.FOLDER_MAPPING) == []
        recent = storage.get_recent_corrections(limit=10)
        assert len(recent) == 1


class TestStatistics:
    def test_stats_includes_total_preferences(self, storage: PreferenceStorage) -> None:
        a = _make_preference(key="a", preference_type=PreferenceType.FOLDER_MAPPING)
        b = _make_preference(key="b", preference_type=PreferenceType.NAMING_PATTERN)
        storage.save_preference(a)
        storage.save_preference(b)

        stats = storage.get_statistics()

        # Both implementations expose total_preferences in some form
        # (key name normalized in the Protocol).
        assert "total_preferences" in stats
        assert stats["total_preferences"] == 2

    def test_stats_handles_empty_storage(self, storage: PreferenceStorage) -> None:
        stats = storage.get_statistics()
        assert stats["total_preferences"] == 0


class TestExportImportRoundTrip:
    def test_export_then_import_recovers_preferences_and_corrections(
        self, storage: PreferenceStorage, tmp_path: Path
    ) -> None:
        """Round-trip a preference AND a correction through export/import.

        Asserts both come back with full fidelity (CodeRabbit on PR
        #207 — the original test only asserted the preference, missing
        the SQLite-timestamp regression that this PR also fixes).
        """
        pref = _make_preference()
        ts = datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
        src_path = tmp_path / "a"
        dst_path = tmp_path / "b"
        correction = Correction(
            correction_type=CorrectionType.FILE_MOVE,
            source=src_path,
            destination=dst_path,
            timestamp=ts,
            context={"note": "round-trip"},
        )
        storage.save_preference(pref)
        storage.save_correction(correction)

        snapshot = storage.export_data()
        assert isinstance(snapshot, dict)

        # Wipe both preferences and corrections, then restore from snapshot.
        # ``delete_preferences()`` (no arg) clears corrections too.
        storage.delete_preferences()
        storage.import_data(snapshot)

        recovered = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
        assert len(recovered) == 1
        assert recovered[0].key == pref.key
        assert recovered[0].value == pref.value

        # Correction is restored with intact source/destination/timestamp/type
        recovered_corrs = storage.get_corrections_for_file(src_path)
        assert len(recovered_corrs) == 1
        rc = recovered_corrs[0]
        assert rc.source == src_path
        assert rc.destination == dst_path
        assert rc.correction_type == CorrectionType.FILE_MOVE
        assert rc.timestamp == ts


# ---------------------------------------------------------------------------
# PreferenceTracker injection tests (no parametrize: tracker uses storage)
# ---------------------------------------------------------------------------


class TestPreferenceTrackerInjection:
    """``PreferenceTracker(storage=...)`` delegates correctly to the backend."""

    def test_default_constructor_uses_in_memory(self) -> None:
        # No exception, no args needed — backwards-compat preserved.
        # The default storage is InMemoryPreferenceStorage. We assert via
        # observable behavior (no SQLite file, find returns [] cleanly)
        # rather than poking ``tracker._storage`` (CodeRabbit on PR #207).
        tracker = PreferenceTracker()
        from file_organizer.services.intelligence.preference_tracker import PreferenceType as PT

        # find round-trip works without any backing file or external setup
        assert tracker.get_all_preferences(PT.FOLDER_MAPPING) == []

    def test_track_correction_routes_to_storage_save_correction(self, tmp_path: Path) -> None:
        mock_storage = MagicMock(spec=PreferenceStorage)
        # find_preferences returns [] so tracker takes the new-pref code path
        mock_storage.find_preferences.return_value = []

        tracker = PreferenceTracker(storage=mock_storage)
        src = tmp_path / "report.pdf"
        dst = tmp_path / "Documents" / "report.pdf"
        tracker.track_correction(
            source=src,
            destination=dst,
            correction_type=CorrectionType.FILE_MOVE,
        )

        # Mock-call-args verification (T3): the correction passed to storage
        # must carry the exact path/type the caller provided.
        mock_storage.save_correction.assert_called_once()
        saved = mock_storage.save_correction.call_args.args[0]
        assert isinstance(saved, Correction)
        assert saved.source == src
        assert saved.destination == dst
        assert saved.correction_type == CorrectionType.FILE_MOVE

    def test_track_correction_routes_to_storage_save_preference(self, tmp_path: Path) -> None:
        mock_storage = MagicMock(spec=PreferenceStorage)
        mock_storage.find_preferences.return_value = []

        tracker = PreferenceTracker(storage=mock_storage)
        src = tmp_path / "doc.pdf"
        dst = tmp_path / "Archive" / "doc.pdf"
        tracker.track_correction(
            source=src,
            destination=dst,
            correction_type=CorrectionType.FILE_MOVE,
        )

        # The new preference is saved to storage (one call only — first time
        # this pattern is seen, so tracker's "extract" code path runs).
        mock_storage.save_preference.assert_called_once()
        saved_pref = mock_storage.save_preference.call_args.args[0]
        assert isinstance(saved_pref, Preference)
        assert saved_pref.preference_type == PreferenceType.FOLDER_MAPPING

    def test_explicit_in_memory_storage(self) -> None:
        """Constructing with an explicit storage instance routes calls to it.

        Asserts via observable behavior (the same Preference saved
        through the storage shows up via the tracker) rather than
        poking ``tracker._storage`` (CodeRabbit on PR #207).
        """
        storage = InMemoryPreferenceStorage()
        tracker = PreferenceTracker(storage=storage)
        # Save through the injected storage, observe via the tracker
        pref = _make_preference()
        storage.save_preference(pref)
        from file_organizer.services.intelligence.preference_tracker import PreferenceType as PT

        assert len(tracker.get_all_preferences(PT.FOLDER_MAPPING)) == 1


class TestSqliteStorageDirect:
    """SQLite-specific concerns that don't fit the Protocol contract tests."""

    def test_db_file_created_on_first_save(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "preferences.db"
        # Parent directory will be created. ``with`` ensures the
        # connection is closed on assertion failure too (CodeRabbit on
        # PR #207 — leak prevention).
        with SqlitePreferenceStorage(db_path) as storage:
            storage.save_preference(_make_preference())
            assert db_path.exists()
            assert db_path.stat().st_size > 0

    def test_round_trip_survives_storage_recreation(self, tmp_path: Path) -> None:
        db_path = tmp_path / "preferences.db"
        pref = _make_preference()

        # First storage instance writes a preference; ``with`` ensures
        # the connection closes even if the save raises (CodeRabbit on
        # PR #207).
        with SqlitePreferenceStorage(db_path) as storage1:
            storage1.save_preference(pref)

        # Second instance over the same file reads it back.
        with SqlitePreferenceStorage(db_path) as storage2:
            recovered = storage2.find_preferences(PreferenceType.FOLDER_MAPPING)
            assert len(recovered) == 1
            assert recovered[0].key == pref.key


# ---------------------------------------------------------------------------
# Regression tests for PR #207 review fixes
# ---------------------------------------------------------------------------


class TestPreviouslyMissingFidelity:
    """SQLite-only fixes that the in-memory backend never exhibited."""

    def test_sqlite_save_preference_honors_metadata_timestamps(self, tmp_path: Path) -> None:
        """``SqlitePreferenceStorage.save_preference`` must round-trip metadata timestamps."""
        storage = SqlitePreferenceStorage(tmp_path / "p.db")
        try:
            old_created = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
            old_updated = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
            old_last_used = datetime(2024, 9, 1, 12, 0, tzinfo=UTC)
            pref = Preference(
                preference_type=PreferenceType.FOLDER_MAPPING,
                key="file_move|.pdf|Documents",
                value="Documents",
                metadata=PreferenceMetadata(
                    created=old_created,
                    updated=old_updated,
                    confidence=0.5,
                    frequency=1,
                    last_used=old_last_used,
                    source="user_correction",
                ),
                context={"source_extension": ".pdf"},
            )
            storage.save_preference(pref)

            recovered = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
            assert len(recovered) == 1
            assert recovered[0].metadata.created == old_created
            assert recovered[0].metadata.updated == old_updated
            assert recovered[0].metadata.last_used == old_last_used
        finally:
            storage.close()

    def test_sqlite_save_correction_honors_timestamp(self, tmp_path: Path) -> None:
        """``SqlitePreferenceStorage.save_correction`` must persist the supplied timestamp."""
        storage = SqlitePreferenceStorage(tmp_path / "p.db")
        try:
            backfill_ts = datetime(2024, 3, 14, 9, 0, tzinfo=UTC)
            correction = Correction(
                correction_type=CorrectionType.FILE_MOVE,
                source=tmp_path / "x.pdf",
                destination=tmp_path / "Docs" / "x.pdf",
                timestamp=backfill_ts,
                context={},
            )
            storage.save_correction(correction)

            recent = storage.get_recent_corrections(limit=10)
            assert len(recent) == 1
            assert recent[0].timestamp == backfill_ts
        finally:
            storage.close()

    def test_sqlite_update_preference_confidence_raises_when_pref_absent(
        self, tmp_path: Path
    ) -> None:
        """Updating confidence on a never-saved preference must raise (not silently no-op)."""
        storage = SqlitePreferenceStorage(tmp_path / "p.db")
        try:
            pref = _make_preference()
            # No save_preference call → row doesn't exist
            with pytest.raises(KeyError, match="No persisted preference"):
                storage.update_preference_confidence(pref, success=True)
        finally:
            storage.close()

    def test_sqlite_int_value_round_trips_as_int(self, tmp_path: Path) -> None:
        """``_encode_pref_value`` / ``_decode_pref_value`` must preserve numeric types."""
        storage = SqlitePreferenceStorage(tmp_path / "p.db")
        try:
            now = datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
            pref = Preference(
                preference_type=PreferenceType.CUSTOM,
                key="numeric",
                value=42,  # int (not str)
                metadata=PreferenceMetadata(created=now, updated=now),
                context={},
            )
            storage.save_preference(pref)
            recovered = storage.find_preferences(PreferenceType.CUSTOM)
            assert len(recovered) == 1
            assert recovered[0].value == 42
            assert isinstance(recovered[0].value, int)
        finally:
            storage.close()


class TestStatsKeysParity:
    """``get_statistics`` exposes the same keys for both backends."""

    def test_sqlite_statistics_has_legacy_keys(self, tmp_path: Path) -> None:
        storage = SqlitePreferenceStorage(tmp_path / "p.db")
        try:
            stats = storage.get_statistics()
            for key in (
                "total_preferences",
                "unique_preferences",
                "total_corrections",
                "successful_applications",
                "failed_applications",
                "average_confidence",
            ):
                assert key in stats, f"missing legacy stats key: {key}"
        finally:
            storage.close()


class TestImportDataAtomic:
    """``import_data`` must be transactional (CodeRabbit on PR #207)."""

    def test_import_data_failure_rolls_back(self, tmp_path: Path) -> None:
        """If a save mid-import raises, the previous data must be preserved."""
        storage = SqlitePreferenceStorage(tmp_path / "p.db")
        try:
            # Seed: one preference + one correction
            pref = _make_preference(key="file_move|.pdf|Documents")
            storage.save_preference(pref)
            storage.save_correction(_make_correction(tmp_path / "a.pdf", tmp_path / "b.pdf"))
            assert len(storage.find_preferences(PreferenceType.FOLDER_MAPPING)) == 1

            # Construct a snapshot whose corrections list has a bad row
            # (missing required ``timestamp`` key) so save_correction
            # raises mid-import.
            bad_snapshot = {
                "preferences": {
                    "folder_mapping:new_key": [_make_preference(key="new_key").to_dict()]
                },
                "corrections": [
                    {
                        "correction_type": "file_move",
                        "source": "/x",
                        "destination": "/y",
                        # Missing 'timestamp' → datetime.fromisoformat raises
                        "context": {},
                    }
                ],
            }
            with pytest.raises((KeyError, TypeError, ValueError)):
                storage.import_data(bad_snapshot)

            # Original data should be preserved (transaction rolled back).
            preserved = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
            assert len(preserved) == 1
            assert preserved[0].key == "file_move|.pdf|Documents"
        finally:
            storage.close()


class TestLastUsedPersistedThroughTracker:
    """``PreferenceTracker.get_preference`` must persist ``last_used`` (CodeRabbit)."""

    def test_get_preference_persists_last_used_in_sqlite_backend(self, tmp_path: Path) -> None:
        storage = SqlitePreferenceStorage(tmp_path / "p.db")
        try:
            tracker = PreferenceTracker(storage=storage)
            tracker.track_correction(
                source=tmp_path / "doc.pdf",
                destination=tmp_path / "Documents" / "doc.pdf",
                correction_type=CorrectionType.FILE_MOVE,
            )

            t0 = datetime.now(UTC)
            best = tracker.get_preference(tmp_path / "another.pdf", PreferenceType.FOLDER_MAPPING)
            assert best is not None

            # Re-fetch via storage (NEW dataclass instance) and check that
            # ``last_used`` got written through to the DB.
            re_fetched = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
            assert len(re_fetched) == 1
            assert re_fetched[0].metadata.last_used is not None
            assert re_fetched[0].metadata.last_used >= t0
        finally:
            storage.close()


# ---------------------------------------------------------------------------
# Second-cycle review fixes (PR #207, Codex post-fix re-review)
# ---------------------------------------------------------------------------


class TestSavePreferenceIdempotentFrequency:
    """``save_preference`` doesn't auto-bump frequency on re-save (Codex P1 follow-up)."""

    def test_resave_preserves_frequency_in_sqlite(self, tmp_path: Path) -> None:
        with SqlitePreferenceStorage(tmp_path / "p.db") as storage:
            now = datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
            pref = Preference(
                preference_type=PreferenceType.FOLDER_MAPPING,
                key="file_move|.pdf|Documents",
                value="Documents",
                metadata=PreferenceMetadata(created=now, updated=now, confidence=0.5, frequency=11),
                context={"source_extension": ".pdf"},
            )
            storage.save_preference(pref)

            # Re-save without changing dataclass — e.g., what get_preference
            # does after mutating last_used. Frequency must NOT bump.
            storage.save_preference(pref)
            storage.save_preference(pref)

            recovered = storage.find_preferences(PreferenceType.FOLDER_MAPPING)
            assert len(recovered) == 1
            assert recovered[0].metadata.frequency == 11


class TestImportDataResetsApplicationCounters:
    """``import_data`` resets success/failure counters (Codex P2 follow-up)."""

    def test_import_clears_stale_application_counts_for_sqlite(self, tmp_path: Path) -> None:
        with SqlitePreferenceStorage(tmp_path / "p.db") as storage:
            # Build up some pre-import application history
            pref = _make_preference()
            storage.save_preference(pref)
            storage.update_preference_confidence(pref, success=True)
            storage.update_preference_confidence(pref, success=False)
            stats = storage.get_statistics()
            assert stats["successful_applications"] == 1
            assert stats["failed_applications"] == 1

            # Import a snapshot with NO statistics block — counters must reset
            storage.import_data({"preferences": {}, "corrections": []})
            stats = storage.get_statistics()
            assert stats["successful_applications"] == 0
            assert stats["failed_applications"] == 0

    def test_import_hydrates_application_counts_from_snapshot(self, tmp_path: Path) -> None:
        with SqlitePreferenceStorage(tmp_path / "p.db") as storage:
            storage.import_data(
                {
                    "preferences": {},
                    "corrections": [],
                    "statistics": {
                        "successful_applications": 7,
                        "failed_applications": 3,
                    },
                }
            )
            stats = storage.get_statistics()
            assert stats["successful_applications"] == 7
            assert stats["failed_applications"] == 3


# ---------------------------------------------------------------------------
# Third-cycle review fixes (PR #207, Codex 20:07Z re-review)
# ---------------------------------------------------------------------------


class TestUpdateConfidenceErrorAtomicity:
    """``update_preference_confidence`` is atomic w.r.t. side-effects on error.

    A failed call (no backing row) must NOT mutate ``preference.metadata``
    or bump ``_successful_applications`` / ``_failed_applications`` —
    the persistence check now runs FIRST (Codex P2 on PR #207).
    """

    def test_update_on_unsaved_pref_does_not_mutate_dataclass(self, tmp_path: Path) -> None:
        with SqlitePreferenceStorage(tmp_path / "p.db") as storage:
            pref = _make_preference(confidence=0.5)
            original_confidence = pref.metadata.confidence
            original_last_used = pref.metadata.last_used

            with pytest.raises(KeyError):
                storage.update_preference_confidence(pref, success=True)

            # Dataclass is unchanged — no mutation before the raise
            assert pref.metadata.confidence == original_confidence
            assert pref.metadata.last_used == original_last_used

    def test_update_on_unsaved_pref_does_not_bump_counters(self, tmp_path: Path) -> None:
        with SqlitePreferenceStorage(tmp_path / "p.db") as storage:
            pref_unsaved = _make_preference(key="ghost")
            pref_saved = _make_preference(key="real")
            storage.save_preference(pref_saved)

            # First do a real success so counter is at 1
            storage.update_preference_confidence(pref_saved, success=True)
            assert storage.get_statistics()["successful_applications"] == 1

            # Now attempt update on the unsaved one — must not bump
            with pytest.raises(KeyError):
                storage.update_preference_confidence(pref_unsaved, success=True)

            # Counter unchanged
            assert storage.get_statistics()["successful_applications"] == 1


class TestExportPreservesApplicationCounters:
    """``export_data`` includes in-memory application counters (Codex P2 on PR #207)."""

    def test_export_round_trip_preserves_application_counters_in_sqlite(
        self, tmp_path: Path
    ) -> None:
        with SqlitePreferenceStorage(tmp_path / "p1.db") as src_storage:
            pref = _make_preference()
            src_storage.save_preference(pref)
            src_storage.update_preference_confidence(pref, success=True)
            src_storage.update_preference_confidence(pref, success=True)
            src_storage.update_preference_confidence(pref, success=False)
            assert src_storage.get_statistics()["successful_applications"] == 2
            assert src_storage.get_statistics()["failed_applications"] == 1

            snapshot = src_storage.export_data()

        # Import into a fresh storage and verify counters survived
        with SqlitePreferenceStorage(tmp_path / "p2.db") as dst_storage:
            dst_storage.import_data(snapshot)
            stats = dst_storage.get_statistics()
            assert stats["successful_applications"] == 2
            assert stats["failed_applications"] == 1
