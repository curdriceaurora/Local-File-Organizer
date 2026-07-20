"""Storage backends for ``PreferenceTracker`` (Epic D / D5).

Tracks: issue #157 (Hardening Epic D, item D5).

Two implementations of the :class:`PreferenceStorage` Protocol:

- :class:`InMemoryPreferenceStorage` — preserves the original
  ``PreferenceTracker`` behavior (in-process dicts, thread-safe via RLock).
  ``PreferenceTracker()`` with no args wires this up by default.
- :class:`SqlitePreferenceStorage` — adapter around
  :class:`PreferenceDatabaseManager` that translates the manager's
  string-keyed dict rows into ``Preference`` / ``Correction`` dataclass
  instances. Use this when corrections must persist across processes.

The Protocol is intentionally narrow — only the storage primitives the
tracker needs from a backend. Domain logic (correction → preference
extraction, best-match selection by extension, etc.) stays in
``PreferenceTracker``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, runtime_checkable

from .preference_database import PreferenceDatabaseManager
from .preference_tracker import (
    Correction,
    CorrectionType,
    Preference,
    PreferenceMetadata,
    PreferenceType,
)

# Note on imports: ``preference_tracker`` defers ``from .preference_storage
# import InMemoryPreferenceStorage`` into ``PreferenceTracker.__init__`` so
# this module can import the dataclasses at top level. The cycle is broken
# in one direction (tracker → storage uses a deferred import); module-level
# dataclass imports here are safe and required for runtime use as method
# parameter / return types. Extracting the dataclasses to a third module
# would eliminate even the deferred import but is out of scope for D5.


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class PreferenceStorage(Protocol):
    """Storage backend protocol for :class:`PreferenceTracker`.

    Designed to be narrow: the tracker keeps its domain logic (extracting
    preferences from corrections, best-match selection by file extension,
    etc.) and delegates only the storage primitives.
    """

    # Preference CRUD ------------------------------------------------------

    def save_preference(self, preference: Preference) -> None:
        """Insert or update ``preference`` (idempotent on type+key)."""
        ...

    def find_preferences(
        self,
        preference_type: PreferenceType,
        key: str | None = None,
    ) -> list[Preference]:
        """Return preferences of ``preference_type``, optionally filtered by ``key``."""
        ...

    def update_preference_confidence(
        self,
        preference: Preference,
        success: bool,
    ) -> None:
        """Adjust the preference's confidence: +0.05 cap 0.98 on success, -0.10 floor 0.10 on failure."""
        ...

    def delete_preferences(
        self,
        preference_type: PreferenceType | None = None,
    ) -> int:
        """Delete preferences (all or by type). Returns number of rows deleted."""
        ...

    # Correction history ---------------------------------------------------

    def save_correction(self, correction: Correction) -> None:
        """Append a correction to the history."""
        ...

    def get_corrections_for_file(self, file_path: Path) -> list[Correction]:
        """Return corrections whose source OR destination equals ``file_path``."""
        ...

    def get_recent_corrections(self, limit: int = 10) -> list[Correction]:
        """Return the most recent corrections, newest first, capped at ``limit``."""
        ...

    # Statistics + bulk ----------------------------------------------------

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate counters: at minimum ``total_preferences``."""
        ...

    def export_data(self) -> dict[str, Any]:
        """Serialize all storage state to a JSON-friendly dict."""
        ...

    def import_data(self, data: dict[str, Any]) -> None:
        """Replace storage state with the contents of ``data`` (from :meth:`export_data`)."""
        ...


# ---------------------------------------------------------------------------
# InMemoryPreferenceStorage — in-process dicts (the original tracker model)
# ---------------------------------------------------------------------------


class InMemoryPreferenceStorage:
    """In-process dict storage. Thread-safe via ``RLock``.

    Behavior is bit-identical to the pre-D5 ``PreferenceTracker`` storage
    layer: preferences are keyed by ``preference_type:key`` and stored
    as a list of :class:`Preference` instances; corrections are an
    append-only list.
    """

    def __init__(self) -> None:
        """Initialize empty in-memory storage with a reentrant lock."""
        self._lock = RLock()
        # ``total_preferences`` was previously a separate counter that
        # could drift from ``len(_preferences)`` on rewrite vs append
        # (CodeRabbit finding on PR #207). It's now derived in
        # ``get_statistics`` from ``sum(len(prefs) for ...)``.
        self._preferences: dict[str, list[Preference]] = {}
        self._corrections: list[Correction] = []
        self._successful_applications = 0
        self._failed_applications = 0

    @staticmethod
    def _storage_key(preference_type: PreferenceType, key: str) -> str:
        return f"{preference_type.value}:{key}"

    def save_preference(self, preference: Preference) -> None:
        """Upsert ``preference``; updates existing entry on (type, key) collision."""
        with self._lock:
            storage_key = self._storage_key(preference.preference_type, preference.key)
            existing = self._preferences.get(storage_key, [])
            for idx, existing_pref in enumerate(existing):
                if existing_pref.key == preference.key:
                    # Replace existing in place — preserves list ordering.
                    existing[idx] = preference
                    return
            existing.append(preference)
            self._preferences[storage_key] = existing

    def find_preferences(
        self,
        preference_type: PreferenceType,
        key: str | None = None,
    ) -> list[Preference]:
        """Return preferences of ``preference_type``, optionally filtered by ``key``."""
        with self._lock:
            results: list[Preference] = []
            for storage_key, prefs in self._preferences.items():
                if not storage_key.startswith(f"{preference_type.value}:"):
                    continue
                for pref in prefs:
                    if pref.preference_type != preference_type:
                        continue
                    if key is not None and pref.key != key:
                        continue
                    results.append(pref)
            return results

    def update_preference_confidence(
        self,
        preference: Preference,
        success: bool,
    ) -> None:
        """Adjust confidence (+0.05 cap 0.98 on success / -0.10 floor 0.10 on failure)."""
        with self._lock:
            now = datetime.now(UTC)
            if success:
                preference.metadata.confidence = min(0.98, preference.metadata.confidence + 0.05)
                preference.metadata.last_used = now
                self._successful_applications += 1
            else:
                preference.metadata.confidence = max(0.1, preference.metadata.confidence - 0.1)
                self._failed_applications += 1
            preference.metadata.updated = now

    def delete_preferences(
        self,
        preference_type: PreferenceType | None = None,
    ) -> int:
        """Delete preferences (all if ``None``, else only that type). Returns delete count."""
        with self._lock:
            if preference_type is None:
                count = sum(len(prefs) for prefs in self._preferences.values())
                self._preferences.clear()
                self._corrections.clear()
                return count

            count = 0
            keys_to_remove: list[str] = []
            for storage_key, prefs_list in self._preferences.items():
                kept = [p for p in prefs_list if p.preference_type != preference_type]
                count += len(prefs_list) - len(kept)
                if not kept:
                    keys_to_remove.append(storage_key)
                else:
                    self._preferences[storage_key] = kept
            for k in keys_to_remove:
                del self._preferences[k]
            return count

    def save_correction(self, correction: Correction) -> None:
        """Append a correction to the history."""
        with self._lock:
            self._corrections.append(correction)

    def get_corrections_for_file(self, file_path: Path) -> list[Correction]:
        """Return corrections matching ``file_path`` as either source or destination."""
        with self._lock:
            return [
                c for c in self._corrections if c.source == file_path or c.destination == file_path
            ]

    def get_recent_corrections(self, limit: int = 10) -> list[Correction]:
        """Return the most recent corrections (newest first), capped at ``limit``."""
        with self._lock:
            sorted_corrs = sorted(self._corrections, key=lambda c: c.timestamp, reverse=True)
            return sorted_corrs[:limit]

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate stats: total_preferences, successful/failed applications, correction count."""
        with self._lock:
            all_prefs: list[Preference] = []
            for prefs in self._preferences.values():
                all_prefs.extend(prefs)
            avg_confidence = (
                sum(p.metadata.confidence for p in all_prefs) / len(all_prefs) if all_prefs else 0.0
            )
            return {
                "total_preferences": len(all_prefs),
                "unique_preferences": len(self._preferences),
                # ``total_corrections`` is the running count of corrections
                # ever passed to ``save_correction``; ``total_correction_history``
                # is the current list length. They're always equal in this
                # backend (we never delete corrections), but the original
                # tracker exposed both keys, so we preserve both for
                # backwards-compat with existing test assertions.
                "total_corrections": len(self._corrections),
                "total_correction_history": len(self._corrections),
                "successful_applications": self._successful_applications,
                "failed_applications": self._failed_applications,
                "average_confidence": round(avg_confidence, 3),
            }

    def export_data(self) -> dict[str, Any]:
        """Serialize all preferences + corrections + counters to a JSON-friendly dict."""
        with self._lock:
            total = sum(len(prefs) for prefs in self._preferences.values())
            return {
                "preferences": {
                    key: [p.to_dict() for p in prefs] for key, prefs in self._preferences.items()
                },
                "corrections": [c.to_dict() for c in self._corrections],
                "statistics": {
                    "total_preferences": total,
                    "successful_applications": self._successful_applications,
                    "failed_applications": self._failed_applications,
                },
                "exported_at": datetime.now(UTC).isoformat(),
            }

    def import_data(self, data: dict[str, Any]) -> None:
        """Replace all storage state with ``data``'s contents."""
        with self._lock:
            self._preferences.clear()
            self._corrections.clear()
            for storage_key, prefs_list in data.get("preferences", {}).items():
                self._preferences[storage_key] = [Preference.from_dict(p) for p in prefs_list]
            for corr_data in data.get("corrections", []):
                self._corrections.append(
                    Correction(
                        correction_type=CorrectionType(corr_data["correction_type"]),
                        source=Path(corr_data["source"]),
                        destination=Path(corr_data["destination"]),
                        timestamp=datetime.fromisoformat(corr_data["timestamp"]),
                        context=corr_data.get("context", {}),
                    )
                )
            # ``total_preferences`` in the imported statistics block is
            # informational only — the live count is derived from
            # ``len(self._preferences)`` in ``get_statistics``.
            stats = data.get("statistics", {})
            self._successful_applications = stats.get("successful_applications", 0)
            self._failed_applications = stats.get("failed_applications", 0)


# ---------------------------------------------------------------------------
# SqlitePreferenceStorage — adapter over PreferenceDatabaseManager
# ---------------------------------------------------------------------------


def _row_to_preference(row: dict[str, Any]) -> Preference:
    """Translate a ``preferences`` table row (string-keyed dict) into a Preference."""
    created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
    updated = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
    last_used_raw = row.get("last_used_at")
    last_used = (
        datetime.fromisoformat(last_used_raw.replace("Z", "+00:00")) if last_used_raw else None
    )
    context = row.get("context") or {}
    if isinstance(context, str):
        context = json.loads(context)
    return Preference(
        preference_type=PreferenceType(row["preference_type"]),
        key=row["key"],
        # Stored as text; if the original was a dict/list we round-trip via JSON.
        value=_decode_pref_value(row["value"]),
        metadata=PreferenceMetadata(
            created=created,
            updated=updated,
            confidence=float(row["confidence"]),
            frequency=int(row["frequency"]),
            last_used=last_used,
            source=row.get("source", "user_correction"),
        ),
        context=context,
    )


def _encode_pref_value(value: Any) -> str:
    """Encode a preference value for SQLite TEXT storage.

    Always uses JSON so the encoding is fully reversible by
    :func:`_decode_pref_value` — strings round-trip as quoted JSON,
    numbers/bools/None as their JSON literals, dicts/lists as JSON
    objects/arrays. Without this symmetry, ``42`` would store as
    ``"42"`` and decode back as the string ``"42"`` (CodeRabbit /
    Codex P2 finding on PR #207).
    """
    return json.dumps(value)


def _decode_pref_value(stored: str) -> Any:
    """Restore a preference value from its JSON-encoded text form.

    Inverse of :func:`_encode_pref_value`. Falls back to the raw text
    only if the column predates the always-JSON encoding (defensive —
    no main-branch data exists in the legacy form yet, but the fallback
    keeps the read path robust against manually-inserted rows).
    """
    if not stored:
        return stored
    try:
        return json.loads(stored)
    except json.JSONDecodeError:
        return stored


def _iso_z(dt: datetime) -> str:
    """Render ``dt`` as ISO-8601 with the 'Z' UTC suffix (matches DB column convention)."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class SqlitePreferenceStorage:
    """Adapter exposing :class:`PreferenceDatabaseManager` as :class:`PreferenceStorage`.

    The manager handles the SQL; this class translates between the
    string-keyed dicts the manager returns and the dataclass instances the
    Protocol's callers expect.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize SQLite storage at ``db_path`` (creates parent dir if needed)."""
        self._db = PreferenceDatabaseManager(db_path)
        self._db.initialize()
        self._lock = RLock()
        # In-memory counters for stats keys the SQLite schema doesn't
        # carry — the original tracker stored these as in-process
        # counters that never persisted across restarts, so this matches
        # pre-D5 behavior. (CodeRabbit / Copilot review on PR #207.)
        self._successful_applications = 0
        self._failed_applications = 0

    def close(self) -> None:
        """Release the SQLite connection (idempotent)."""
        self._db.close()

    def __enter__(self) -> SqlitePreferenceStorage:
        """Enable ``with SqlitePreferenceStorage(...) as storage:`` usage."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Always close the underlying connection on context exit."""
        del exc_type, exc_val, exc_tb
        self.close()

    def save_preference(self, preference: Preference) -> None:
        """Upsert ``preference`` with full metadata fidelity.

        Bypasses ``PreferenceDatabaseManager.add_preference``'s
        ``ON CONFLICT … DO UPDATE SET frequency = frequency + 1`` clause
        in favor of an explicit ``INSERT … ON CONFLICT … DO UPDATE``
        that takes ALL field values from the dataclass. This gives the
        caller full control:

        - Frequency is set to ``preference.metadata.frequency`` exactly
          (idempotent for re-saves like ``get_preference``'s ``last_used``
          write-back, where the caller didn't intend to bump frequency).
        - Multi-writer atomicity is the caller's responsibility (the
          ``PreferenceTracker._tracker_lock`` makes single-process
          writes atomic; cross-process concurrent writers can lose
          increments — this matches the in-memory backend's behavior
          and is documented as a known limitation for D5).
        - All metadata timestamps round-trip without the manager
          stamping ``now``.

        Per Codex P1+P2 + CodeRabbit + Copilot findings on PR #207.
        """
        with self._lock:
            conn = self._db.get_connection()
            context_json = json.dumps(preference.context) if preference.context else None
            last_used_at = (
                _iso_z(preference.metadata.last_used) if preference.metadata.last_used else None
            )
            conn.execute(
                """
                INSERT INTO preferences (
                    preference_type, key, value, confidence, frequency,
                    created_at, updated_at, last_used_at, source, context
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(preference_type, key) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    frequency = excluded.frequency,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    last_used_at = excluded.last_used_at,
                    source = excluded.source,
                    context = excluded.context
                """,
                (
                    preference.preference_type.value,
                    preference.key,
                    _encode_pref_value(preference.value),
                    preference.metadata.confidence,
                    preference.metadata.frequency,
                    _iso_z(preference.metadata.created),
                    _iso_z(preference.metadata.updated),
                    last_used_at,
                    preference.metadata.source,
                    context_json,
                ),
            )

    def find_preferences(
        self,
        preference_type: PreferenceType,
        key: str | None = None,
    ) -> list[Preference]:
        """Look up preferences via the manager's by-type / by-key methods."""
        with self._lock:
            if key is not None:
                row = self._db.get_preference(preference_type.value, key)
                return [_row_to_preference(row)] if row else []
            rows = self._db.get_preferences_by_type(preference_type.value)
            return [_row_to_preference(r) for r in rows]

    def update_preference_confidence(
        self,
        preference: Preference,
        success: bool,
    ) -> None:
        """Apply confidence delta and persist to SQLite (raises if pref absent).

        Raises :class:`KeyError` when the preference has no row in the
        database — silently no-op'ing here would diverge from the
        in-memory backend, where the dataclass mutation always sticks.
        Callers must :meth:`save_preference` before updating confidence.

        Persists ``last_used_at`` on the success path (the manager's
        ``update_preference_confidence`` only writes ``confidence``,
        leaving ``last_used_at`` stale on the SQLite backend — Codex P2
        finding on PR #207).
        """
        with self._lock:
            # Persistence check FIRST — if the row is absent we raise
            # without mutating the dataclass or bumping the application
            # counters (Codex P2 on PR #207). Otherwise a failed call
            # would still corrupt in-memory state and ``get_statistics``
            # would report applications that never reached the DB.
            row = self._db.get_preference(preference.preference_type.value, preference.key)
            if row is None:
                raise KeyError(
                    f"No persisted preference for ({preference.preference_type.value}, "
                    f"{preference.key!r}); call save_preference first."
                )

            now = datetime.now(UTC)
            if success:
                preference.metadata.confidence = min(0.98, preference.metadata.confidence + 0.05)
                preference.metadata.last_used = now
                self._successful_applications += 1
            else:
                preference.metadata.confidence = max(0.1, preference.metadata.confidence - 0.1)
                self._failed_applications += 1
            preference.metadata.updated = now
            conn = self._db.get_connection()
            conn.execute(
                """
                UPDATE preferences
                SET confidence = ?, updated_at = ?, last_used_at = ?
                WHERE id = ?
                """,
                (
                    preference.metadata.confidence,
                    _iso_z(preference.metadata.updated),
                    _iso_z(preference.metadata.last_used)
                    if preference.metadata.last_used
                    else None,
                    int(row["id"]),
                ),
            )

    def delete_preferences(
        self,
        preference_type: PreferenceType | None = None,
    ) -> int:
        """Delete preferences (all or by type). Returns delete count.

        Wrapped in :meth:`PreferenceDatabaseManager.transaction` so the
        count + delete pair is atomic and rolls back on failure
        (CodeRabbit on PR #207). When called with ``preference_type=None``,
        also clears the ``corrections`` table to match the in-memory
        backend's semantics.
        """
        with self._lock, self._db.transaction():
            conn = self._db.get_connection()
            if preference_type is None:
                cur = conn.execute("SELECT COUNT(*) FROM preferences")
                count = int(cur.fetchone()[0])
                conn.execute("DELETE FROM preferences")
                conn.execute("DELETE FROM corrections")
                return count
            cur = conn.execute(
                "SELECT COUNT(*) FROM preferences WHERE preference_type = ?",
                (preference_type.value,),
            )
            count = int(cur.fetchone()[0])
            conn.execute(
                "DELETE FROM preferences WHERE preference_type = ?",
                (preference_type.value,),
            )
            return count

    def save_correction(self, correction: Correction) -> None:
        """Append a correction honoring ``correction.timestamp``.

        ``PreferenceDatabaseManager.add_correction`` always stamps
        ``timestamp`` with "now"; we follow up with a raw UPDATE so
        backfilled / imported corrections keep their original
        chronology. (Codex P2 + CodeRabbit + Copilot on PR #207.)
        """
        with self._lock:
            metadata = dict(correction.context) if correction.context else None
            row_id = self._db.add_correction(
                correction_type=correction.correction_type.value,
                source_path=str(correction.source),
                destination_path=str(correction.destination),
                category_old=(metadata or {}).get("old_category"),
                category_new=(metadata or {}).get("new_category"),
                metadata=metadata,
            )
            conn = self._db.get_connection()
            conn.execute(
                "UPDATE corrections SET timestamp = ? WHERE id = ?",
                (_iso_z(correction.timestamp), row_id),
            )

    def get_corrections_for_file(self, file_path: Path) -> list[Correction]:
        """Filter corrections by source OR destination matching ``file_path``."""
        with self._lock:
            conn = self._db.get_connection()
            target = str(file_path)
            cur = conn.execute(
                """
                SELECT * FROM corrections
                WHERE source_path = ? OR destination_path = ?
                ORDER BY timestamp DESC
                """,
                (target, target),
            )
            return [self._row_to_correction(dict(r)) for r in cur.fetchall()]

    def get_recent_corrections(self, limit: int = 10) -> list[Correction]:
        """Return up to ``limit`` most-recent corrections."""
        with self._lock:
            rows = self._db.get_corrections(limit=limit)
            return [self._row_to_correction(r) for r in rows]

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate stats with the same keys as the in-memory backend.

        Includes ``successful_applications`` / ``failed_applications`` /
        ``unique_preferences`` / ``average_confidence`` so callers and
        tests don't need to special-case the SQLite backend. (Codex P2 +
        Copilot finding on PR #207 — the original tracker exposed these
        keys in-memory.)
        """
        with self._lock:
            db_stats = self._db.get_preference_stats()
            conn = self._db.get_connection()
            cur = conn.execute("SELECT COUNT(*) FROM corrections")
            corrections_count = int(cur.fetchone()[0])
            cur = conn.execute(
                "SELECT COUNT(DISTINCT preference_type || ':' || key) FROM preferences"
            )
            unique_count = int(cur.fetchone()[0])
            return {
                "total_preferences": db_stats.get("total_preferences", 0),
                "unique_preferences": unique_count,
                "total_correction_history": corrections_count,
                "total_corrections": corrections_count,
                "successful_applications": self._successful_applications,
                "failed_applications": self._failed_applications,
                "average_confidence": round(db_stats.get("average_confidence", 0.0) or 0.0, 3),
                # Preserve the manager's by_type breakdown so existing
                # callers depending on it (if any) still see it.
                "by_type": db_stats.get("by_type", {}),
            }

    def export_data(self) -> dict[str, Any]:
        """Serialize SQLite contents to the same export shape as InMemoryPreferenceStorage.

        Includes the in-memory ``successful_applications`` /
        ``failed_applications`` counters in the ``statistics`` block so
        an export → import round-trip preserves them (Codex P2 on PR
        #207 — the manager's ``get_preference_stats()`` only knows
        about persisted DB columns).
        """
        with self._lock:
            conn = self._db.get_connection()
            cur = conn.execute("SELECT * FROM preferences")
            preferences: dict[str, list[dict[str, Any]]] = {}
            for r in cur.fetchall():
                row = dict(r)
                pref = _row_to_preference(row)
                storage_key = f"{pref.preference_type.value}:{pref.key}"
                preferences.setdefault(storage_key, []).append(pref.to_dict())

            cur = conn.execute("SELECT * FROM corrections ORDER BY timestamp ASC")
            corrections = [self._row_to_correction(dict(r)).to_dict() for r in cur.fetchall()]

            statistics = dict(self._db.get_preference_stats())
            statistics["successful_applications"] = self._successful_applications
            statistics["failed_applications"] = self._failed_applications

            return {
                "preferences": preferences,
                "corrections": corrections,
                "statistics": statistics,
                "exported_at": datetime.now(UTC).isoformat(),
            }

    def import_data(self, data: dict[str, Any]) -> None:
        """Replace stored preferences/corrections with ``data`` contents atomically.

        Wrapped in a single :meth:`PreferenceDatabaseManager.transaction`
        so a mid-loop insert failure rolls everything back instead of
        leaving the storage in a half-wiped state. (CodeRabbit finding
        on PR #207.)

        Also resets the in-process success/failure application counters
        and hydrates them from ``data["statistics"]`` if present —
        otherwise stale counts from the storage instance's pre-import file_organizer.history would survive into the imported state and contaminate
        ``get_statistics()`` output. (Codex P2 on PR #207.)
        """
        with self._lock, self._db.transaction():
            conn = self._db.get_connection()
            conn.execute("DELETE FROM preferences")
            conn.execute("DELETE FROM corrections")

            for prefs_list in data.get("preferences", {}).values():
                for pref_dict in prefs_list:
                    pref = Preference.from_dict(pref_dict)
                    self.save_preference(pref)

            for corr_data in data.get("corrections", []):
                self.save_correction(
                    Correction(
                        correction_type=CorrectionType(corr_data["correction_type"]),
                        source=Path(corr_data["source"]),
                        destination=Path(corr_data["destination"]),
                        timestamp=datetime.fromisoformat(corr_data["timestamp"]),
                        context=corr_data.get("context", {}),
                    )
                )

            # Reset application counters; re-hydrate from snapshot's
            # statistics block if it provides them.
            stats = data.get("statistics", {})
            self._successful_applications = stats.get("successful_applications", 0)
            self._failed_applications = stats.get("failed_applications", 0)

    @staticmethod
    def _row_to_correction(row: dict[str, Any]) -> Correction:
        """Translate a ``corrections`` row into a Correction dataclass."""
        timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return Correction(
            correction_type=CorrectionType(row["correction_type"]),
            source=Path(row["source_path"]),
            destination=Path(row.get("destination_path") or row["source_path"]),
            timestamp=timestamp,
            context=metadata,
        )


__all__ = [
    "InMemoryPreferenceStorage",
    "PreferenceStorage",
    "SqlitePreferenceStorage",
]
