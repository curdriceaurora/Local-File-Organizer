"""Repository for :class:`file_organizer.api.db_models.UserSession`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from file_organizer.api.db_models import UserSession


class SessionRepository:
    """CRUD and lifecycle operations for persistent user sessions."""

    @staticmethod
    def _active_filters(
        *,
        now: datetime,
        user_id: str | None = None,
        token_hash: str | None = None,
    ) -> tuple[ColumnElement[bool], ...]:
        """Build the standard active-session predicate set."""
        filters: list[ColumnElement[bool]] = [
            cast(ColumnElement[bool], UserSession.revoked_at.is_(None)),
            cast(ColumnElement[bool], UserSession.expires_at > now),
        ]
        if token_hash is not None:
            filters.append(cast(ColumnElement[bool], UserSession.token_hash == token_hash))
        if user_id is not None:
            filters.append(cast(ColumnElement[bool], UserSession.user_id == user_id))
        return tuple(filters)

    @staticmethod
    def create(
        session: Session,
        *,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
        refresh_token_hash: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> UserSession:
        """Create and persist a session record."""
        row = cast(
            UserSession,
            cast(Any, UserSession)(
                user_id=user_id,
                token_hash=token_hash,
                refresh_token_hash=refresh_token_hash,
                expires_at=expires_at,
                user_agent=user_agent,
                ip_address=ip_address,
            ),
        )
        session.add(row)
        session.flush()
        return row

    @staticmethod
    def get_active_by_token_hash(
        session: Session,
        token_hash: str,
        *,
        now: datetime | None = None,
    ) -> UserSession | None:
        """Return an active (unrevoked, unexpired) session by token hash."""
        current = now or datetime.now(UTC)
        filters = SessionRepository._active_filters(now=current, token_hash=token_hash)
        return session.query(UserSession).filter(*filters).first()

    @staticmethod
    def list_active_for_user(
        session: Session,
        user_id: str,
        *,
        now: datetime | None = None,
    ) -> list[UserSession]:
        """List active sessions for a user."""
        current = now or datetime.now(UTC)
        filters = SessionRepository._active_filters(now=current, user_id=user_id)
        return (
            session.query(UserSession)
            .filter(*filters)
            .order_by(UserSession.created_at.desc())
            .all()
        )

    @staticmethod
    def revoke(session: Session, session_id: str) -> bool:
        """Revoke a session by id."""
        row = session.get(UserSession, session_id)
        if row is None:
            return False
        row.revoked_at = datetime.now(UTC)
        session.flush()
        return True

    @staticmethod
    def prune_expired(session: Session, *, now: datetime | None = None) -> int:
        """Delete revoked/expired sessions and return deleted row count."""
        current = now or datetime.now(UTC)
        expired_or_revoked = cast(
            ColumnElement[bool],
            (UserSession.expires_at <= current) | UserSession.revoked_at.is_not(None),
        )
        count = (
            session.query(UserSession)
            .filter(expired_or_revoked)
            .delete(synchronize_session="fetch")
        )
        session.flush()
        return int(count)
