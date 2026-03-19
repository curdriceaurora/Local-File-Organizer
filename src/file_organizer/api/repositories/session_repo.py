"""Repository for :class:`file_organizer.api.db_models.UserSession`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from file_organizer.api.db_models import UserSession


class SessionRepository:
    """CRUD and lifecycle operations for persistent user sessions."""

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
        row = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
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
        return (
            session.query(UserSession)
            .filter(
                UserSession.token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > current,
            )
            .first()
        )

    @staticmethod
    def list_active_for_user(
        session: Session,
        user_id: str,
        *,
        now: datetime | None = None,
    ) -> list[UserSession]:
        """List active sessions for a user."""
        current = now or datetime.now(UTC)
        return (
            session.query(UserSession)
            .filter(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > current,
            )
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
        count = (
            session.query(UserSession)
            .filter((UserSession.expires_at <= current) | UserSession.revoked_at.is_not(None))
            .delete(synchronize_session="fetch")
        )
        session.flush()
        return int(count)
