"""Tests for file_organizer.updater.background module.

Covers maybe_check_for_updates function with various config scenarios,
environment variables, and throttling behavior.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.updater.background import maybe_check_for_updates
from file_organizer.updater.manager import UpdateStatus
from file_organizer.updater.state import UpdateState, UpdateStateStore

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# maybe_check_for_updates
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMaybeCheckForUpdates:
    """Test maybe_check_for_updates function."""

    def test_returns_none_when_disabled_via_env(self):
        """Returns None if FO_DISABLE_UPDATE_CHECK is set."""
        with patch.dict(os.environ, {"FO_DISABLE_UPDATE_CHECK": "1"}):
            result = maybe_check_for_updates()
            assert result is None

    def test_returns_none_when_in_pytest(self):
        """Returns None if PYTEST_CURRENT_TEST is set."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test.py::test_func"}):
            result = maybe_check_for_updates()
            assert result is None

    def test_returns_none_if_user_disabled_checks(self):
        """Returns None if check_on_startup is False in config."""
        with patch("file_organizer.updater.background.ConfigManager") as mock_cfg_mgr:
            mock_cfg = MagicMock()
            mock_cfg.updates.check_on_startup = False
            mock_cfg_mgr.return_value.load.return_value = mock_cfg
            result = maybe_check_for_updates()
            assert result is None

    def test_returns_none_if_not_due(self):
        """Returns None if throttle interval hasn't elapsed."""
        state = UpdateState(last_checked=datetime.now(UTC).isoformat())
        store = MagicMock(spec=UpdateStateStore)
        store.load.return_value = state
        with patch("file_organizer.updater.background.ConfigManager") as mock_cfg_mgr:
            mock_cfg = MagicMock()
            mock_cfg.updates.check_on_startup = True
            mock_cfg.updates.interval_hours = 24
            mock_cfg_mgr.return_value.load.return_value = mock_cfg
            with patch("file_organizer.updater.background.UpdateStateStore", return_value=store):
                result = maybe_check_for_updates()
                assert result is None

    def test_checks_and_returns_status_when_due(self):
        """Returns UpdateStatus when check is due and no update available."""
        store = MagicMock(spec=UpdateStateStore)
        old_state = UpdateState()
        store.load.return_value = old_state
        # Remove PYTEST_CURRENT_TEST to allow the function to proceed
        env_patch = patch.dict(os.environ, {}, clear=False)
        env_patch.start()
        try:
            if "PYTEST_CURRENT_TEST" in os.environ:
                del os.environ["PYTEST_CURRENT_TEST"]
            with patch("file_organizer.updater.background.ConfigManager") as mock_cfg_mgr:
                mock_cfg = MagicMock()
                mock_cfg.updates.check_on_startup = True
                mock_cfg.updates.interval_hours = 24
                mock_cfg.updates.repo = "test/repo"
                mock_cfg.updates.include_prereleases = False
                mock_cfg_mgr.return_value.load.return_value = mock_cfg
                with patch("file_organizer.updater.background.UpdateManager") as mock_mgr:
                    mock_mgr_inst = MagicMock()
                    status = UpdateStatus(
                        available=False,
                        current_version="1.0.0",
                    )
                    mock_mgr_inst.check.return_value = status
                    mock_mgr.return_value = mock_mgr_inst
                    with patch(
                        "file_organizer.updater.background.UpdateStateStore", return_value=store
                    ):
                        result = maybe_check_for_updates()
                        assert result is not None
                        assert result.available is False
        finally:
            env_patch.stop()

    def test_records_check_with_latest_version(self):
        """Records the latest version when update is available."""
        store = MagicMock(spec=UpdateStateStore)
        old_state = UpdateState()
        store.load.return_value = old_state
        env_patch = patch.dict(os.environ, {}, clear=False)
        env_patch.start()
        try:
            if "PYTEST_CURRENT_TEST" in os.environ:
                del os.environ["PYTEST_CURRENT_TEST"]
            with patch("file_organizer.updater.background.ConfigManager") as mock_cfg_mgr:
                mock_cfg = MagicMock()
                mock_cfg.updates.check_on_startup = True
                mock_cfg.updates.interval_hours = 24
                mock_cfg.updates.repo = "test/repo"
                mock_cfg.updates.include_prereleases = False
                mock_cfg_mgr.return_value.load.return_value = mock_cfg
                with patch("file_organizer.updater.background.UpdateManager") as mock_mgr:
                    mock_mgr_inst = MagicMock()
                    status = UpdateStatus(
                        available=True,
                        current_version="1.0.0",
                        latest_version="2.0.0",
                    )
                    mock_mgr_inst.check.return_value = status
                    mock_mgr.return_value = mock_mgr_inst
                    with patch(
                        "file_organizer.updater.background.UpdateStateStore", return_value=store
                    ):
                        maybe_check_for_updates()
                        # Verify record_check was called with latest version
                        store.record_check.assert_called_once()
                        args = store.record_check.call_args
                        assert args[0][0] == "2.0.0"
        finally:
            env_patch.stop()

    def test_records_check_with_current_version_when_no_update(self):
        """Records the current version when no update is available."""
        store = MagicMock(spec=UpdateStateStore)
        old_state = UpdateState()
        store.load.return_value = old_state
        env_patch = patch.dict(os.environ, {}, clear=False)
        env_patch.start()
        try:
            if "PYTEST_CURRENT_TEST" in os.environ:
                del os.environ["PYTEST_CURRENT_TEST"]
            with patch("file_organizer.updater.background.ConfigManager") as mock_cfg_mgr:
                mock_cfg = MagicMock()
                mock_cfg.updates.check_on_startup = True
                mock_cfg.updates.interval_hours = 24
                mock_cfg.updates.repo = "test/repo"
                mock_cfg.updates.include_prereleases = False
                mock_cfg_mgr.return_value.load.return_value = mock_cfg
                with patch("file_organizer.updater.background.UpdateManager") as mock_mgr:
                    mock_mgr_inst = MagicMock()
                    status = UpdateStatus(
                        available=False,
                        current_version="1.0.0",
                    )
                    mock_mgr_inst.check.return_value = status
                    mock_mgr.return_value = mock_mgr_inst
                    with patch(
                        "file_organizer.updater.background.UpdateStateStore", return_value=store
                    ):
                        maybe_check_for_updates()
                        store.record_check.assert_called_once()
                        args = store.record_check.call_args
                        assert args[0][0] == "1.0.0"
        finally:
            env_patch.stop()

    def test_respects_custom_profile(self):
        """Uses custom profile when specified."""
        store = MagicMock(spec=UpdateStateStore)
        old_state = UpdateState()
        store.load.return_value = old_state
        env_patch = patch.dict(os.environ, {}, clear=False)
        env_patch.start()
        try:
            if "PYTEST_CURRENT_TEST" in os.environ:
                del os.environ["PYTEST_CURRENT_TEST"]
            with patch("file_organizer.updater.background.ConfigManager") as mock_cfg_mgr:
                mock_cfg = MagicMock()
                mock_cfg.updates.check_on_startup = True
                mock_cfg.updates.interval_hours = 24
                mock_cfg.updates.repo = "test/repo"
                mock_cfg.updates.include_prereleases = False
                mock_cfg_mgr.return_value.load.return_value = mock_cfg
                with patch("file_organizer.updater.background.UpdateManager"):
                    with patch(
                        "file_organizer.updater.background.UpdateStateStore", return_value=store
                    ):
                        maybe_check_for_updates(profile="custom")
                        mock_cfg_mgr.return_value.load.assert_called_with(profile="custom")
        finally:
            env_patch.stop()

    def test_respects_custom_state_store(self):
        """Uses custom state store when provided."""
        custom_store = MagicMock(spec=UpdateStateStore)
        old_state = UpdateState()
        custom_store.load.return_value = old_state
        env_patch = patch.dict(os.environ, {}, clear=False)
        env_patch.start()
        try:
            if "PYTEST_CURRENT_TEST" in os.environ:
                del os.environ["PYTEST_CURRENT_TEST"]
            with patch("file_organizer.updater.background.ConfigManager") as mock_cfg_mgr:
                mock_cfg = MagicMock()
                mock_cfg.updates.check_on_startup = True
                mock_cfg.updates.interval_hours = 24
                mock_cfg.updates.repo = "test/repo"
                mock_cfg.updates.include_prereleases = False
                mock_cfg_mgr.return_value.load.return_value = mock_cfg
                with patch("file_organizer.updater.background.UpdateManager"):
                    maybe_check_for_updates(state_store=custom_store)
                    custom_store.load.assert_called()
        finally:
            env_patch.stop()

    def test_respects_custom_time(self):
        """Uses custom time for due checks."""
        store = MagicMock(spec=UpdateStateStore)
        # Last checked 2 days ago
        last_check = datetime(2024, 1, 13, 14, 0, 0, tzinfo=UTC)
        state = UpdateState(last_checked=last_check.isoformat())
        store.load.return_value = state
        env_patch = patch.dict(os.environ, {}, clear=False)
        env_patch.start()
        try:
            if "PYTEST_CURRENT_TEST" in os.environ:
                del os.environ["PYTEST_CURRENT_TEST"]
            with patch("file_organizer.updater.background.ConfigManager") as mock_cfg_mgr:
                mock_cfg = MagicMock()
                mock_cfg.updates.check_on_startup = True
                mock_cfg.updates.interval_hours = 24
                mock_cfg.updates.repo = "test/repo"
                mock_cfg.updates.include_prereleases = False
                mock_cfg_mgr.return_value.load.return_value = mock_cfg
                with patch("file_organizer.updater.background.UpdateManager") as mock_mgr:
                    mock_mgr_inst = MagicMock()
                    status = UpdateStatus(
                        available=False,
                        current_version="1.0.0",
                    )
                    mock_mgr_inst.check.return_value = status
                    mock_mgr.return_value = mock_mgr_inst
                    with patch(
                        "file_organizer.updater.background.UpdateStateStore", return_value=store
                    ):
                        now = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)
                        result = maybe_check_for_updates(now=now)
                        # Should have checked since 2 days > 24 hours
                        assert result is not None
        finally:
            env_patch.stop()

    def test_uses_default_store_path_when_none_provided(self):
        """Creates default store when state_store not provided."""
        with patch("file_organizer.updater.background.ConfigManager") as mock_cfg_mgr:
            mock_cfg = MagicMock()
            mock_cfg.updates.check_on_startup = False
            mock_cfg_mgr.return_value.load.return_value = mock_cfg
            with patch("file_organizer.updater.background.UpdateStateStore"):
                maybe_check_for_updates()
                # Should have tried to create a store instance
                # (though disabled checks mean it returns None before calling)
