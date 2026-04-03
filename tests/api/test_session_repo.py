"""Tests for file_organizer.api.repositories.session_repo."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from file_organizer.api.db_models import UserSession
from file_organizer.api.repositories.session_repo import SessionRepository

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestSessionRepositoryCreate:
    """Tests for SessionRepository.create."""

    def test_create_minimal(self):
        session = MagicMock(spec=Session)
        expires = datetime(2026, 6, 1, tzinfo=UTC)

        SessionRepository.create(
            session,
            user_id="user-1",
            token_hash="hash-abc",
            expires_at=expires,
        )

        session.add.assert_called_once()
        session.flush.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, UserSession)
        assert added.user_id == "user-1"
        assert added.token_hash == "hash-abc"
        assert added.expires_at == expires
        assert added.refresh_token_hash is None
        assert added.user_agent is None
        assert added.ip_address is None

    def test_create_with_all_fields(self):
        session = MagicMock(spec=Session)
        expires = datetime(2026, 6, 1, tzinfo=UTC)

        SessionRepository.create(
            session,
            user_id="user-1",
            token_hash="hash-abc",
            expires_at=expires,
            refresh_token_hash="refresh-hash",
            user_agent="Mozilla/5.0",
            ip_address="192.168.1.1",
        )

        added = session.add.call_args[0][0]
        assert added.refresh_token_hash == "refresh-hash"
        assert added.user_agent == "Mozilla/5.0"
        assert added.ip_address == "192.168.1.1"


class TestSessionRepositoryGetActiveByTokenHash:
    """Tests for SessionRepository.get_active_by_token_hash."""

    def _make_session(self, result=None):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = result
        return session

    def test_get_active_session(self):
        user_session = MagicMock(spec=UserSession)
        session = self._make_session(result=user_session)

        result = SessionRepository.get_active_by_token_hash(session, "hash-abc")
        assert result is user_session

    def test_get_returns_none_when_not_found(self):
        session = self._make_session(result=None)

        result = SessionRepository.get_active_by_token_hash(session, "missing-hash")
        assert result is None

    def test_get_uses_provided_now(self):
        session = self._make_session(result=None)
        custom_now = datetime(2026, 1, 1, tzinfo=UTC)

        with patch("file_organizer.api.repositories.session_repo.datetime") as mock_dt:
            SessionRepository.get_active_by_token_hash(session, "hash-abc", now=custom_now)
            mock_dt.now.assert_not_called()
        session.query.return_value.filter.assert_called()

    def test_get_builds_active_filters(self):
        session = self._make_session(result=None)

        SessionRepository.get_active_by_token_hash(session, "hash-abc")

        args = session.query.return_value.filter.call_args.args
        assert len(args) == 3


class TestSessionRepositoryListActiveForUser:
    """Tests for SessionRepository.list_active_for_user."""

    def test_list_active_sessions(self):
        session = MagicMock(spec=Session)
        sessions_list = [MagicMock(spec=UserSession), MagicMock(spec=UserSession)]
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = sessions_list

        result = SessionRepository.list_active_for_user(session, "user-1")
        assert result == sessions_list

    def test_list_with_custom_now(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []

        custom_now = datetime(2026, 3, 1, tzinfo=UTC)
        with patch("file_organizer.api.repositories.session_repo.datetime") as mock_dt:
            result = SessionRepository.list_active_for_user(session, "user-1", now=custom_now)
            mock_dt.now.assert_not_called()
        assert result == []

    def test_list_builds_active_filters(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []

        SessionRepository.list_active_for_user(session, "user-1")

        args = session.query.return_value.filter.call_args.args
        assert len(args) == 3


class TestSessionRepositoryRevoke:
    """Tests for SessionRepository.revoke."""

    def test_revoke_existing_session(self):
        session = MagicMock(spec=Session)
        user_session = MagicMock(spec=UserSession)
        user_session.revoked_at = None
        session.get.return_value = user_session

        result = SessionRepository.revoke(session, "session-1")
        assert result is True
        assert user_session.revoked_at is not None
        session.flush.assert_called_once()

    def test_revoke_nonexistent_returns_false(self):
        session = MagicMock(spec=Session)
        session.get.return_value = None

        result = SessionRepository.revoke(session, "missing")
        assert result is False
        session.flush.assert_not_called()


class TestSessionRepositoryPruneExpired:
    """Tests for SessionRepository.prune_expired."""

    def test_prune_returns_deleted_count(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.delete.return_value = 3

        result = SessionRepository.prune_expired(session)
        assert result == 3
        session.flush.assert_called_once()

    def test_prune_returns_zero_when_nothing_expired(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.delete.return_value = 0

        result = SessionRepository.prune_expired(session)
        assert result == 0

    def test_prune_with_custom_now(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.delete.return_value = 1

        custom_now = datetime(2026, 6, 1, tzinfo=UTC)
        with patch("file_organizer.api.repositories.session_repo.datetime") as mock_dt:
            result = SessionRepository.prune_expired(session, now=custom_now)
            mock_dt.now.assert_not_called()
        assert result == 1

    def test_prune_uses_combined_expired_or_revoked_filter(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.delete.return_value = 1

        SessionRepository.prune_expired(session)

        args = session.query.return_value.filter.call_args.args
        assert len(args) == 1
