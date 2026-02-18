"""Tests for MemoryLimiter - memory enforcement with configurable actions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.optimization.memory_limiter import (
    LimitAction,
    MemoryLimiter,
    MemoryLimitError,
)


class TestLimitAction:
    """Tests for the LimitAction enum."""

    def test_warn_value(self) -> None:
        """Test WARN enum value."""
        assert LimitAction.WARN.value == "warn"

    def test_block_value(self) -> None:
        """Test BLOCK enum value."""
        assert LimitAction.BLOCK.value == "block"

    def test_evict_cache_value(self) -> None:
        """Test EVICT_CACHE enum value."""
        assert LimitAction.EVICT_CACHE.value == "evict_cache"

    def test_raise_value(self) -> None:
        """Test RAISE enum value."""
        assert LimitAction.RAISE.value == "raise"


class TestMemoryLimiterInit:
    """Tests for MemoryLimiter initialization."""

    def test_default_action(self) -> None:
        """Test default action is WARN."""
        limiter = MemoryLimiter(max_memory_mb=512)
        assert limiter.action == LimitAction.WARN

    def test_custom_action(self) -> None:
        """Test custom action setting."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.RAISE)
        assert limiter.action == LimitAction.RAISE

    def test_max_memory_mb_property(self) -> None:
        """Test max_memory_mb property."""
        limiter = MemoryLimiter(max_memory_mb=1024)
        assert limiter.max_memory_mb == 1024

    def test_invalid_max_memory_zero(self) -> None:
        """Test that max_memory_mb=0 raises ValueError."""
        with pytest.raises(ValueError, match="max_memory_mb must be > 0"):
            MemoryLimiter(max_memory_mb=0)

    def test_invalid_max_memory_negative(self) -> None:
        """Test that negative max_memory_mb raises ValueError."""
        with pytest.raises(ValueError, match="max_memory_mb must be > 0"):
            MemoryLimiter(max_memory_mb=-100)

    def test_initial_violation_count(self) -> None:
        """Test that violation count starts at zero."""
        limiter = MemoryLimiter(max_memory_mb=512)
        assert limiter.violation_count == 0


class TestMemoryLimiterCheck:
    """Tests for the check() method."""

    @patch.object(MemoryLimiter, "_get_rss", return_value=100 * 1024 * 1024)
    def test_check_under_limit(self, mock_rss: MagicMock) -> None:
        """Test check returns True when under limit."""
        limiter = MemoryLimiter(max_memory_mb=512)
        assert limiter.check() is True

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_check_over_limit(self, mock_rss: MagicMock) -> None:
        """Test check returns False when over limit."""
        limiter = MemoryLimiter(max_memory_mb=512)
        assert limiter.check() is False

    @patch.object(MemoryLimiter, "_get_rss", return_value=512 * 1024 * 1024)
    def test_check_at_exact_limit(self, mock_rss: MagicMock) -> None:
        """Test check returns False when exactly at limit."""
        limiter = MemoryLimiter(max_memory_mb=512)
        assert limiter.check() is False


class TestMemoryLimiterEnforce:
    """Tests for the enforce() method with different actions."""

    @patch.object(MemoryLimiter, "_get_rss", return_value=100 * 1024 * 1024)
    def test_enforce_under_limit_no_action(self, mock_rss: MagicMock) -> None:
        """Test enforce does nothing when under limit."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.RAISE)
        limiter.enforce()  # Should not raise
        assert limiter.violation_count == 0

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_enforce_warn_action(self, mock_rss: MagicMock) -> None:
        """Test enforce with WARN action logs but does not raise."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.WARN)
        limiter.enforce()  # Should not raise
        assert limiter.violation_count == 1

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_enforce_block_action(self, mock_rss: MagicMock) -> None:
        """Test enforce with BLOCK action logs but does not raise."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.BLOCK)
        limiter.enforce()  # Should not raise
        assert limiter.violation_count == 1

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_enforce_raise_action(self, mock_rss: MagicMock) -> None:
        """Test enforce with RAISE action raises MemoryLimitError."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.RAISE)
        with pytest.raises(MemoryLimitError, match="Memory limit exceeded"):
            limiter.enforce()
        assert limiter.violation_count == 1

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_enforce_evict_cache_calls_callback(self, mock_rss: MagicMock) -> None:
        """Test enforce with EVICT_CACHE calls the eviction callback."""
        callback = MagicMock()
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.EVICT_CACHE)
        limiter.set_evict_callback(callback)
        limiter.enforce()

        callback.assert_called_once()
        assert limiter.violation_count == 1

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_enforce_evict_cache_no_callback(self, mock_rss: MagicMock) -> None:
        """Test enforce with EVICT_CACHE but no callback set."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.EVICT_CACHE)
        limiter.enforce()  # Should not raise even without callback
        assert limiter.violation_count == 1

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_enforce_increments_violation_count(self, mock_rss: MagicMock) -> None:
        """Test that violation count increments on each enforcement."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.WARN)
        limiter.enforce()
        limiter.enforce()
        limiter.enforce()
        assert limiter.violation_count == 3


class TestMemoryLimiterGuarded:
    """Tests for the guarded() context manager."""

    @patch.object(MemoryLimiter, "_get_rss", return_value=100 * 1024 * 1024)
    def test_guarded_under_limit(self, mock_rss: MagicMock) -> None:
        """Test guarded context when under limit."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.RAISE)
        with limiter.guarded():
            pass  # Should not raise

    @patch.object(MemoryLimiter, "_get_rss", return_value=600 * 1024 * 1024)
    def test_guarded_over_limit_raises_on_entry(self, mock_rss: MagicMock) -> None:
        """Test guarded context raises on entry when over limit."""
        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.RAISE)
        with pytest.raises(MemoryLimitError):
            with limiter.guarded():
                pass

    def test_guarded_enforces_on_exit(self) -> None:
        """Test that guarded context enforces on exit."""
        call_count = 0

        def rss_values() -> int:
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return 100 * 1024 * 1024  # Under limit on entry
            return 600 * 1024 * 1024  # Over limit on exit

        limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.RAISE)

        with patch.object(MemoryLimiter, "_get_rss", side_effect=rss_values):
            with pytest.raises(MemoryLimitError):
                with limiter.guarded():
                    pass  # Memory grows during execution


class TestMemoryLimiterGetCurrentMemory:
    """Tests for get_current_memory_mb method."""

    @patch.object(MemoryLimiter, "_get_rss", return_value=256 * 1024 * 1024)
    def test_get_current_memory_mb(self, mock_rss: MagicMock) -> None:
        """Test get_current_memory_mb returns correct value."""
        limiter = MemoryLimiter(max_memory_mb=512)
        assert limiter.get_current_memory_mb() == 256.0

    @patch.object(MemoryLimiter, "_get_rss", return_value=0)
    def test_get_current_memory_mb_zero(self, mock_rss: MagicMock) -> None:
        """Test get_current_memory_mb when RSS is zero."""
        limiter = MemoryLimiter(max_memory_mb=512)
        assert limiter.get_current_memory_mb() == 0.0
