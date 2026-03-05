"""Tests for file_organizer.api.repositories.settings_repo."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from file_organizer.api.db_models import SettingsStore
from file_organizer.api.repositories.settings_repo import SettingsRepository

pytestmark = pytest.mark.unit


class TestSettingsRepositoryGet:
    """Tests for SettingsRepository.get."""

    def _make_session(self, row=None):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = row
        return session

    def test_get_existing_global_setting(self):
        row = MagicMock(spec=SettingsStore)
        row.value = "dark"
        session = self._make_session(row=row)

        result = SettingsRepository.get(session, "theme")
        assert result == "dark"

    def test_get_nonexistent_returns_none(self):
        session = self._make_session(row=None)

        result = SettingsRepository.get(session, "missing_key")
        assert result is None

    def test_get_user_scoped_setting(self):
        row = MagicMock(spec=SettingsStore)
        row.value = "light"
        session = self._make_session(row=row)

        result = SettingsRepository.get(session, "theme", user_id="user-1")
        assert result == "light"


class TestSettingsRepositorySet:
    """Tests for SettingsRepository.set."""

    def _make_session(self, existing_row=None):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = existing_row
        return session

    def test_set_creates_new_setting(self):
        session = self._make_session(existing_row=None)

        SettingsRepository.set(session, "theme", "dark")

        session.add.assert_called_once()
        session.flush.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, SettingsStore)
        assert added.key == "theme"
        assert added.value == "dark"
        assert added.user_id is None

    def test_set_updates_existing_setting(self):
        existing = MagicMock(spec=SettingsStore)
        existing.value = "light"
        session = self._make_session(existing_row=existing)

        result = SettingsRepository.set(session, "theme", "dark")

        assert existing.value == "dark"
        session.add.assert_not_called()
        session.flush.assert_called_once()
        assert result is existing

    def test_set_with_user_id(self):
        session = self._make_session(existing_row=None)

        SettingsRepository.set(session, "theme", "dark", user_id="user-1")

        added = session.add.call_args[0][0]
        assert added.user_id == "user-1"

    def test_set_none_value(self):
        session = self._make_session(existing_row=None)

        SettingsRepository.set(session, "optional_key", None)

        added = session.add.call_args[0][0]
        assert added.value is None


class TestSettingsRepositoryDelete:
    """Tests for SettingsRepository.delete."""

    def _make_session(self, row=None):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = row
        return session

    def test_delete_existing_setting(self):
        row = MagicMock(spec=SettingsStore)
        session = self._make_session(row=row)

        result = SettingsRepository.delete(session, "theme")
        assert result is True
        session.delete.assert_called_once_with(row)
        session.flush.assert_called_once()

    def test_delete_nonexistent_returns_false(self):
        session = self._make_session(row=None)

        result = SettingsRepository.delete(session, "missing")
        assert result is False
        session.delete.assert_not_called()

    def test_delete_user_scoped(self):
        row = MagicMock(spec=SettingsStore)
        session = self._make_session(row=row)

        result = SettingsRepository.delete(session, "theme", user_id="user-1")
        assert result is True


class TestSettingsRepositoryListAll:
    """Tests for SettingsRepository.list_all."""

    def test_list_global_settings(self):
        row1 = MagicMock(spec=SettingsStore)
        row1.key = "lang"
        row1.value = "en"
        row2 = MagicMock(spec=SettingsStore)
        row2.key = "theme"
        row2.value = "dark"

        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = [row1, row2]

        result = SettingsRepository.list_all(session)
        assert result == {"lang": "en", "theme": "dark"}

    def test_list_empty(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []

        result = SettingsRepository.list_all(session)
        assert result == {}

    def test_list_user_scoped(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []

        result = SettingsRepository.list_all(session, user_id="user-1")
        # Verify filter was called with user_id condition
        query.filter.assert_called_once()
        assert result == {}
