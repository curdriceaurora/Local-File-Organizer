"""
Unit tests for DaemonService.

Tests daemon lifecycle (start, stop, restart), signal handling,
PID file management, callback registration, and background operation.
"""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from pathlib import Path

import pytest

from file_organizer.daemon.config import DaemonConfig
from file_organizer.daemon.service import DaemonService

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


@pytest.fixture
def watch_dir(tmp_path: Path) -> Path:
    """Create a temporary directory to watch."""
    d = tmp_path / "incoming"
    d.mkdir()
    return d


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory."""
    d = tmp_path / "organized"
    d.mkdir()
    return d


@pytest.fixture
def pid_file(tmp_path: Path) -> Path:
    """Return a temporary PID file path."""
    return tmp_path / "file_organizer.daemon.pid"


@pytest.fixture
def config(watch_dir: Path, output_dir: Path, pid_file: Path) -> DaemonConfig:
    """Create a DaemonConfig for testing."""
    return DaemonConfig(
        watch_directories=[watch_dir],
        output_directory=output_dir,
        pid_file=pid_file,
        poll_interval=0.05,
        max_concurrent=2,
        dry_run=True,
    )


@pytest.fixture
def daemon(config: DaemonConfig) -> DaemonService:
    """Create a DaemonService and ensure cleanup."""
    svc = DaemonService(config)
    yield svc
    if svc.is_running:
        svc.stop()


class TestDaemonLifecycle:
    """Tests for start/stop lifecycle."""

    def test_initial_state_not_running(self, daemon: DaemonService) -> None:
        """A fresh daemon reports is_running=False."""
        assert daemon.is_running is False

    def test_start_background_sets_running(self, daemon: DaemonService) -> None:
        """start_background brings the daemon into running state."""
        daemon.start_background()

        assert daemon.is_running is True

    def test_stop_clears_running(self, daemon: DaemonService) -> None:
        """stop() transitions from running to stopped."""
        daemon.start_background()
        assert daemon.is_running is True

        daemon.stop()
        deadline = time.monotonic() + 5.0
        while daemon.is_running and time.monotonic() < deadline:
            pass

        assert daemon.is_running is False

    def test_double_start_raises(self, daemon: DaemonService) -> None:
        """Starting an already-running daemon raises RuntimeError."""
        daemon.start_background()

        with pytest.raises(RuntimeError, match="already running"):
            daemon.start_background()

    def test_stop_idempotent(self, daemon: DaemonService) -> None:
        """stop() is safe to call when not running."""
        daemon.stop()  # Should not raise

    def test_restart_cycles_daemon(self, daemon: DaemonService) -> None:
        """restart() stops and starts the daemon."""
        daemon.start_background()
        assert daemon.is_running is True

        daemon.restart()
        deadline = time.monotonic() + 5.0
        while not daemon.is_running and time.monotonic() < deadline:
            pass

        assert daemon.is_running is True

    def test_restart_when_stopped(self, daemon: DaemonService) -> None:
        """restart() works even when the daemon is not running."""
        assert daemon.is_running is False

        daemon.restart()
        deadline = time.monotonic() + 5.0
        while not daemon.is_running and time.monotonic() < deadline:
            pass

        assert daemon.is_running is True

    def test_start_background_refuses_when_pid_file_shows_live_process(
        self, daemon: DaemonService, pid_file: Path
    ) -> None:
        """If the on-disk PID file already points at a live process (e.g.
        a prior daemon that crashed without cleaning up, or a still-running
        one), start_background() must refuse rather than spawning a second
        daemon that writes to the same PID file.

        Uses this test process's own PID/create_time as the "live process"
        the on-disk record points to, since it's guaranteed to be alive
        for the duration of the test.
        """
        daemon._pid_manager.write_pid_record(pid_file, pid=os.getpid())

        with pytest.raises(RuntimeError, match="stale PID file indicates a live process"):
            daemon.start_background()

        assert daemon.is_running is False

    def test_start_background_refuses_when_pid_file_claim_is_lost(
        self, daemon: DaemonService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A concurrent process that claims the PID file after the liveness
        check must prevent this daemon from spawning a background thread.
        """
        monkeypatch.setattr(daemon._pid_manager, "is_running", lambda _pid_file: False)

        def claim_lost(_pid_file: Path) -> None:
            raise FileExistsError("claimed by competitor")

        monkeypatch.setattr(daemon._pid_manager, "claim_pid_file", claim_lost)

        with pytest.raises(RuntimeError, match="PID file was claimed"):
            daemon.start_background()

        assert daemon.is_running is False
        assert daemon._thread is None

    def test_start_background_propagates_startup_failure(self, daemon: DaemonService) -> None:
        """If initialization in the background thread raises,
        start_background() must re-raise rather than returning a false
        success (regression: previously the caller only saw _started_event
        get set and assumed the daemon was up).
        """
        from unittest.mock import patch

        with patch.object(daemon, "_setup_default_tasks", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="Daemon failed to start"):
                daemon.start_background()

        assert daemon.is_running is False

    def test_repeated_restart_cycles_do_not_leave_scheduler_zombie(
        self,
        daemon: DaemonService,
    ) -> None:
        """Repeated start/stop cycles must not leave the scheduler in a
        zombied ``_running=True`` state.

        Regression for the ``test_restart_cycles_daemon`` flake (PR #179 CI):
        ``DaemonScheduler.run()`` used to clear ``_stop_event`` inside itself,
        which races with ``_cleanup()``'s ``scheduler.stop()`` call. Under
        xdist CI contention this caused the next ``run_in_background()`` in
        ``_background_run`` to raise ``RuntimeError("Scheduler is already
        running")``, leaving the daemon with ``is_running=False`` after
        restart.
        """
        for _ in range(5):
            daemon.start_background()
            assert daemon.is_running is True
            daemon.restart()

            # restart() already waits for the background thread to reach
            # _started_event.set(). is_running must be True immediately.
            assert daemon.is_running is True

            daemon.stop()
            deadline = time.monotonic() + 5.0
            while daemon.is_running and time.monotonic() < deadline:
                pass
            assert daemon.is_running is False


class TestPidFileManagement:
    """Tests for PID file lifecycle with the daemon."""

    def test_pid_file_created_on_start(self, daemon: DaemonService, pid_file: Path) -> None:
        """Starting the daemon creates the PID file.

        F2: the service now writes via ``write_pid_record`` so the file
        contains a JSON record (``{pid, create_time}``). The record's
        ``pid`` field must be the current process's PID.
        """
        daemon.start_background()

        assert pid_file.exists()
        data = json.loads(pid_file.read_text())
        assert data["pid"] == os.getpid()
        assert "create_time" in data

    def test_pid_file_removed_on_stop(self, daemon: DaemonService, pid_file: Path) -> None:
        """Stopping the daemon removes the PID file."""
        daemon.start_background()
        assert pid_file.exists()

        daemon.stop()
        deadline = time.monotonic() + 5.0
        while pid_file.exists() and time.monotonic() < deadline:
            pass

        assert not pid_file.exists()

    def test_no_pid_file_when_none(self, watch_dir: Path, output_dir: Path) -> None:
        """No PID file is created when pid_file is None in config."""
        config = DaemonConfig(
            watch_directories=[watch_dir],
            output_directory=output_dir,
            pid_file=None,
            poll_interval=0.05,
        )
        svc = DaemonService(config)
        svc.start_background()

        try:
            assert svc.is_running is True
        finally:
            svc.stop()


class TestCallbacks:
    """Tests for on_start and on_stop callbacks."""

    def test_on_start_callback_fires(self, daemon: DaemonService) -> None:
        """The on_start callback is invoked when the daemon starts."""
        called = threading.Event()
        daemon.on_start(called.set)

        daemon.start_background()

        assert called.wait(timeout=2.0), "on_start callback was not called"

    def test_on_stop_callback_fires(self, daemon: DaemonService) -> None:
        """The on_stop callback is invoked when the daemon stops."""
        called = threading.Event()
        daemon.on_stop(called.set)

        daemon.start_background()
        daemon.stop()

        assert called.wait(timeout=2.0), "on_stop callback was not called"

    def test_callback_exception_does_not_crash(self, daemon: DaemonService) -> None:
        """A failing on_start callback does not prevent daemon operation."""

        def bad_callback() -> None:
            raise RuntimeError("callback boom")

        daemon.on_start(bad_callback)
        daemon.start_background()

        assert daemon.is_running is True


class TestUptimeAndStats:
    """Tests for uptime and statistics tracking."""

    def test_uptime_zero_when_stopped(self, daemon: DaemonService) -> None:
        """uptime_seconds is 0 when the daemon is not running."""
        assert daemon.uptime_seconds == 0.0

    def test_uptime_increases_while_running(self, daemon: DaemonService) -> None:
        """uptime_seconds increases while the daemon runs."""
        daemon.start_background()
        deadline = time.monotonic() + 5.0
        while daemon.uptime_seconds < 0.1 and time.monotonic() < deadline:
            pass

        assert daemon.uptime_seconds >= 0.1

    def test_files_processed_starts_at_zero(self, daemon: DaemonService) -> None:
        """files_processed is 0 initially."""
        assert daemon.files_processed == 0


class TestSchedulerIntegration:
    """Tests for scheduler access from the daemon."""

    def test_scheduler_accessible(self, daemon: DaemonService) -> None:
        """The daemon exposes its scheduler for custom tasks."""
        scheduler = daemon.scheduler
        assert scheduler is not None

    def test_default_tasks_registered_on_start(self, daemon: DaemonService) -> None:
        """Default health_check and stats_report tasks are registered."""
        daemon.start_background()

        names = daemon.scheduler.task_names
        assert "health_check" in names
        assert "stats_report" in names

    def test_custom_task_runs_with_daemon(self, daemon: DaemonService) -> None:
        """A custom task registered before start runs during operation."""
        counter = {"value": 0}
        lock = threading.Lock()

        def bump() -> None:
            with lock:
                counter["value"] += 1

        daemon.scheduler.schedule_task("custom", 0.05, bump)
        daemon.start_background()
        deadline = time.monotonic() + 5.0
        while True:
            with lock:
                if counter["value"] >= 2:
                    break
            if time.monotonic() >= deadline:
                break
        daemon.stop()

        with lock:
            assert counter["value"] >= 2


class TestSignalHandling:
    """Tests for signal handler installation."""

    def test_signal_handler_restores_on_stop(self, config: DaemonConfig) -> None:
        """Signal handlers are restored after daemon stops.

        This test must run in the main thread to install signal handlers.
        Since pytest may not be on the main thread in all configurations,
        we test the handler mechanism directly.
        """
        import os

        from .conftest import wired_pipe

        svc = DaemonService(config)

        with wired_pipe(svc) as (r, _w):
            svc._stop_event.clear()
            svc._running = True

            svc._handle_signal(signal.SIGTERM, None)

            data = os.read(r, 1024)
            assert len(data) > 0

        svc._running = False

    def test_sigint_triggers_stop(self, config: DaemonConfig) -> None:
        """SIGINT triggers the stop event via the handler (writes to pipe)."""
        import os

        from .conftest import wired_pipe

        svc = DaemonService(config)

        with wired_pipe(svc) as (r, _w):
            svc._stop_event.clear()
            svc._running = True

            svc._handle_signal(signal.SIGINT, None)

            data = os.read(r, 1024)
            assert len(data) > 0

        svc._running = False

    def test_start_background_thread_creation_failure(
        self, daemon: DaemonService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If starting the background thread raises an exception, the daemon resets its state and removes the PID file."""
        import threading

        def fail_start(*args, **kwargs):
            raise RuntimeError("thread creation failed")

        monkeypatch.setattr(threading.Thread, "start", fail_start)

        with pytest.raises(RuntimeError, match="thread creation failed"):
            daemon.start_background()

        assert daemon.is_running is False
        assert daemon._thread is None
        if daemon.config.pid_file is not None:
            assert not daemon.config.pid_file.exists()
