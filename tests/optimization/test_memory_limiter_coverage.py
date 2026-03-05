"""Coverage tests for file_organizer.optimization.memory_limiter module.

Targets uncovered branches: enforce with non-callable evict_callback,
_get_rss Linux/macOS paths, guarded context manager exit enforcement.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

from file_organizer.optimization.memory_limiter import (
    LimitAction,
    MemoryLimiter,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# enforce - evict_cache with non-callable callback
# ---------------------------------------------------------------------------


class TestEnforceEvictNonCallable:
    """Test enforce with EVICT_CACHE when callback is set but not callable."""

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_non_callable_callback_does_not_crash(self, mock_rss: MagicMock) -> None:
        """Non-callable evict callback should be silently ignored."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.EVICT_CACHE)
        limiter.set_evict_callback("not_a_function")
        limiter.enforce()  # Should not crash
        assert limiter.violation_count == 1

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_none_callback_does_not_crash(self, mock_rss: MagicMock) -> None:
        """None evict callback should be silently ignored."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.EVICT_CACHE)
        # Don't set callback (default is None)
        limiter.enforce()
        assert limiter.violation_count == 1


# ---------------------------------------------------------------------------
# _get_rss paths
# ---------------------------------------------------------------------------


class TestGetRssCoverage:
    """Test _get_rss with different system configurations."""

    def test_linux_proc_status(self) -> None:
        """Test reading VmRSS from /proc/self/status."""
        status = "VmPeak:   500000 kB\nVmRSS:    256000 kB\n"
        with patch("builtins.open", mock_open(read_data=status)):
            result = MemoryLimiter._get_rss()
        assert result == 256000 * 1024

    def test_macos_resource(self) -> None:
        """Test resource module on macOS (bytes)."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 500_000_000
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "darwin"),
        ):
            result = MemoryLimiter._get_rss()
        assert result == 500_000_000

    def test_linux_resource(self) -> None:
        """Test resource module on Linux (kilobytes)."""
        mock_resource = MagicMock()
        mock_resource.RUSAGE_SELF = 0
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 256000
        mock_resource.getrusage.return_value = mock_usage

        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": mock_resource}),
            patch.object(sys, "platform", "linux"),
        ):
            result = MemoryLimiter._get_rss()
        assert result == 256000 * 1024

    def test_no_rss_returns_zero(self) -> None:
        """Test when no RSS info is available."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch.dict("sys.modules", {"resource": None}),
        ):
            result = MemoryLimiter._get_rss()
        assert result == 0


# ---------------------------------------------------------------------------
# guarded context manager - additional paths
# ---------------------------------------------------------------------------


class TestGuardedCoverage:
    """Additional coverage for guarded() context manager."""

    @patch.object(MemoryLimiter, "_get_rss", return_value=100 * 1024 * 1024)
    def test_guarded_warn_action(self, mock_rss: MagicMock) -> None:
        """Test guarded with WARN action under limit — no exception."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.WARN)
        with limiter.guarded():
            pass  # Should not raise

    def test_guarded_warn_over_limit(self) -> None:
        """Test guarded with WARN action over limit — logs but no exception."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.WARN)
        with patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024):
            with limiter.guarded():
                pass
        # WARN doesn't raise, so both entry and exit enforce run
        assert limiter.violation_count == 2

    def test_guarded_block_over_limit(self) -> None:
        """Test guarded with BLOCK action over limit — no exception."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.BLOCK)
        with patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024):
            with limiter.guarded():
                pass
        assert limiter.violation_count == 2

    def test_guarded_evict_cache_over_limit(self) -> None:
        """Test guarded with EVICT_CACHE action calls callback."""
        callback = MagicMock()
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.EVICT_CACHE)
        limiter.set_evict_callback(callback)
        with patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024):
            with limiter.guarded():
                pass
        # callback called on entry and exit
        assert callback.call_count == 2
        assert limiter.violation_count == 2


# ---------------------------------------------------------------------------
# set_evict_callback
# ---------------------------------------------------------------------------


class TestSetEvictCallback:
    """Test set_evict_callback."""

    def test_set_callback(self) -> None:
        limiter = MemoryLimiter(max_memory_mb=512)
        cb = MagicMock()
        limiter.set_evict_callback(cb)
        assert limiter._evict_callback is cb

    def test_set_callback_to_none(self) -> None:
        limiter = MemoryLimiter(max_memory_mb=512)
        limiter.set_evict_callback(None)
        assert limiter._evict_callback is None
