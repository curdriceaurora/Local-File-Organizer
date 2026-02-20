"""Repository for :class:`~file_organizer.api.db_models.SettingsStore` CRUD."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

from file_organizer.api.db_models import SettingsStore


class SettingsRepository:
    """Data-access layer for the key/value settings store."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    def get(
        session: Session,
        key: str,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """Return the stored value for *key* (scoped to *user_id*), or ``None``.

        Args:
            session: Active SQLAlchemy session.
            key: Settings key name.
            user_id: Scope to a specific user.  ``None`` means global.

        Returns:
            The value string, or ``None`` if the key does not exist.
        """
        row = (
            session.query(SettingsStore)
            .filter(SettingsStore.key == key, SettingsStore.user_id == user_id)
            .first()
        )
        return row.value if row is not None else None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    def set(
        session: Session,
        key: str,
        value: Optional[str],
        user_id: Optional[str] = None,
    ) -> SettingsStore:
        """Create or update a setting.

        If a row with the same ``(user_id, key)`` pair already exists its
        ``value`` is updated; otherwise a new row is inserted.

        Args:
            session: Active SQLAlchemy session.
            key: Settings key name.
            value: Value to store (may be ``None``).
            user_id: Scope to a specific user.  ``None`` means global.

        Returns:
            The created or updated :class:`SettingsStore` row.
        """
        row = (
            session.query(SettingsStore)
            .filter(SettingsStore.key == key, SettingsStore.user_id == user_id)
            .first()
        )
        if row is not None:
            row.value = value
            row.updated_at = datetime.now(UTC)
        else:
            row = SettingsStore(key=key, value=value, user_id=user_id)
            session.add(row)
        session.flush()
        return row

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    @staticmethod
    def delete(
        session: Session,
        key: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """Delete a setting by key (scoped to *user_id*).

        Returns:
            ``True`` if a row was deleted, ``False`` otherwise.
        """
        row = (
            session.query(SettingsStore)
            .filter(SettingsStore.key == key, SettingsStore.user_id == user_id)
            .first()
        )
        if row is None:
            return False
        session.delete(row)
        session.flush()
        return True

    # ------------------------------------------------------------------
    # Bulk read
    # ------------------------------------------------------------------

    @staticmethod
    def list_all(
        session: Session,
        user_id: Optional[str] = None,
    ) -> dict[str, str]:
        """Return all settings for *user_id* as a ``{key: value}`` dict.

        Args:
            session: Active SQLAlchemy session.
            user_id: Scope to a specific user.  ``None`` means global.

        Returns:
            Dictionary mapping setting keys to their stored values.
        """
        rows = (
            session.query(SettingsStore)
            .filter(SettingsStore.user_id == user_id)
            .order_by(SettingsStore.key)
            .all()
        )
        return {row.key: row.value for row in rows}
