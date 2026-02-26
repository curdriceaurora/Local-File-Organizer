"""Tests for AdaptiveBatchSizer - memory-aware dynamic batch sizing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer


@pytest.mark.unit
class TestAdaptiveBatchSizerInit:
    """Tests for AdaptiveBatchSizer initialization."""

    def test_default_init(self) -> None:
        """Test default initialization with 70% target."""
        sizer = AdaptiveBatchSizer()
        assert sizer.target_memory_percent == 70.0
        assert sizer.min_batch_size == 1
        assert sizer.max_batch_size == 1000

    def test_custom_target(self) -> None:
        """Test custom target percentage."""
        sizer = AdaptiveBatchSizer(target_memory_percent=50.0)
        assert sizer.target_memory_percent == 50.0

    def test_invalid_target_zero(self) -> None:
        """Test that target_memory_percent=0 raises ValueError."""
        with pytest.raises(ValueError, match="target_memory_percent"):
            AdaptiveBatchSizer(target_memory_percent=0.0)

    def test_invalid_target_negative(self) -> None:
        """Test that negative target raises ValueError."""
        with pytest.raises(ValueError, match="target_memory_percent"):
            AdaptiveBatchSizer(target_memory_percent=-10.0)

    def test_invalid_target_over_100(self) -> None:
        """Test that target over 100 raises ValueError."""
        with pytest.raises(ValueError, match="target_memory_percent"):
            AdaptiveBatchSizer(target_memory_percent=101.0)

    def test_target_100_is_valid(self) -> None:
        """Test that target_memory_percent=100.0 is valid."""
        sizer = AdaptiveBatchSizer(target_memory_percent=100.0)
        assert sizer.target_memory_percent == 100.0


@pytest.mark.unit
class TestAdaptiveBatchSizerBounds:
    """Tests for set_bounds method."""

    def test_set_bounds(self) -> None:
        """Test setting custom bounds."""
        sizer = AdaptiveBatchSizer()
        sizer.set_bounds(min_size=5, max_size=50)
        assert sizer.min_batch_size == 5
        assert sizer.max_batch_size == 50

    def test_invalid_min_zero(self) -> None:
        """Test that min_size=0 raises ValueError."""
        sizer = AdaptiveBatchSizer()
        with pytest.raises(ValueError, match="min_size must be >= 1"):
            sizer.set_bounds(min_size=0, max_size=100)

    def test_invalid_max_less_than_min(self) -> None:
        """Test that max_size < min_size raises ValueError."""
        sizer = AdaptiveBatchSizer()
        with pytest.raises(ValueError, match="max_size.*must be >= min_size"):
            sizer.set_bounds(min_size=10, max_size=5)


@pytest.mark.unit
class TestAdaptiveBatchSizerCalculate:
    """Tests for calculate_batch_size method."""

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,  # 1 GB available
    )
    def test_basic_calculation(self, mock_mem: MagicMock) -> None:
        """Test basic batch size calculation with round numbers."""
        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        # 70% of 1GB = 700,000,000 byte budget
        # Files of 10,000,000 bytes each (not MiB) + 0 overhead = 70 files
        file_sizes = [10_000_000] * 100
        batch_size = sizer.calculate_batch_size(file_sizes, overhead_per_file=0)
        assert batch_size == 70

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_calculation_with_overhead(self, mock_mem: MagicMock) -> None:
        """Test batch size calculation with per-file overhead."""
        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        # 700,000,000 budget, 10M files + 10M overhead = 20M per file = 35 files
        file_sizes = [10_000_000] * 100
        batch_size = sizer.calculate_batch_size(file_sizes, overhead_per_file=10_000_000)
        assert batch_size == 35

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_capped_by_file_count(self, mock_mem: MagicMock) -> None:
        """Test that batch size doesn't exceed number of files."""
        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        # Only 5 files, but budget allows many more
        file_sizes = [1024] * 5  # 5 tiny files
        batch_size = sizer.calculate_batch_size(file_sizes)
        assert batch_size == 5

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_respects_max_bound(self, mock_mem: MagicMock) -> None:
        """Test that batch size respects max_batch_size."""
        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        sizer.set_bounds(min_size=1, max_size=10)
        file_sizes = [1024] * 1000  # 1000 tiny files
        batch_size = sizer.calculate_batch_size(file_sizes)
        assert batch_size <= 10

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=100,  # Very little memory
    )
    def test_respects_min_bound(self, mock_mem: MagicMock) -> None:
        """Test that batch size respects min_batch_size."""
        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        sizer.set_bounds(min_size=5, max_size=100)
        file_sizes = [10_000_000] * 100  # Large files
        batch_size = sizer.calculate_batch_size(file_sizes)
        assert batch_size >= 5

    def test_empty_file_list(self) -> None:
        """Test with empty file list returns min batch size."""
        sizer = AdaptiveBatchSizer()
        batch_size = sizer.calculate_batch_size([], overhead_per_file=0)
        assert batch_size == sizer.min_batch_size

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=0,
    )
    def test_zero_available_memory(self, mock_mem: MagicMock) -> None:
        """Test with zero available memory returns min batch size."""
        sizer = AdaptiveBatchSizer()
        file_sizes = [1024] * 10
        batch_size = sizer.calculate_batch_size(file_sizes)
        assert batch_size == sizer.min_batch_size

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=500_000_000,
    )
    def test_half_memory_halves_batch(self, mock_mem: MagicMock) -> None:
        """Test that half the memory results in roughly half the batch."""
        sizer = AdaptiveBatchSizer(target_memory_percent=100.0)
        # 100% of 500M = 500M budget, 10M per file = 50 files
        file_sizes = [10_000_000] * 200
        batch_size = sizer.calculate_batch_size(file_sizes)
        assert batch_size == 50

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_mixed_file_sizes_uses_average(self, mock_mem: MagicMock) -> None:
        """Test that mixed file sizes use the average for estimation."""
        sizer = AdaptiveBatchSizer(target_memory_percent=100.0)
        # Average = (5M + 15M) / 2 = 10M per file
        # Budget = 1GB, so 1_000_000_000 / 10_000_000 = 100 files
        file_sizes = [5_000_000, 15_000_000] * 50  # 100 files, avg 10M
        batch_size = sizer.calculate_batch_size(file_sizes)
        assert batch_size == 100


@pytest.mark.unit
class TestAdaptiveBatchSizerFeedback:
    """Tests for adjust_from_feedback method."""

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_adjust_increases_batch_when_low_memory(self, mock_mem: MagicMock) -> None:
        """Test that feedback adjusts batch size up when actual usage is low."""
        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        # Budget is 700M, actual usage was 100M for 10 files
        # = 10M per file, so new batch = 700M / 10M = 70
        new_size = sizer.adjust_from_feedback(actual_memory=100_000_000, batch_size=10)
        assert new_size == 70

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_adjust_decreases_batch_when_high_memory(self, mock_mem: MagicMock) -> None:
        """Test that feedback adjusts batch size down when actual usage is high."""
        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        # Budget is 700M, actual usage was 700M for 10 files
        # = 70M per file, so new batch = 700M / 70M = 10
        new_size = sizer.adjust_from_feedback(actual_memory=700_000_000, batch_size=10)
        assert new_size == 10

    def test_adjust_with_zero_batch_size(self) -> None:
        """Test adjust_from_feedback with zero batch size."""
        sizer = AdaptiveBatchSizer()
        result = sizer.adjust_from_feedback(actual_memory=1024, batch_size=0)
        assert result == sizer.min_batch_size

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_feedback_recorded_in_history(self, mock_mem: MagicMock) -> None:
        """Test that feedback is recorded in history."""
        sizer = AdaptiveBatchSizer()
        sizer.adjust_from_feedback(actual_memory=1024, batch_size=5)
        sizer.adjust_from_feedback(actual_memory=2048, batch_size=10)

        history = sizer.get_history()
        assert len(history) == 2
        assert history[0] == (1024, 5)
        assert history[1] == (2048, 10)

    def test_clear_history(self) -> None:
        """Test clearing feedback history."""
        sizer = AdaptiveBatchSizer()
        with patch.object(
            AdaptiveBatchSizer,
            "_get_available_memory",
            return_value=1_000_000_000,
        ):
            sizer.adjust_from_feedback(actual_memory=1024, batch_size=5)
        sizer.clear_history()
        assert sizer.get_history() == []

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=0,
    )
    def test_adjust_with_zero_available_memory(self, mock_mem: MagicMock) -> None:
        """Test adjust_from_feedback when no memory info available."""
        sizer = AdaptiveBatchSizer()
        result = sizer.adjust_from_feedback(actual_memory=1024, batch_size=10)
        assert result == sizer.min_batch_size

    @patch.object(
        AdaptiveBatchSizer,
        "_get_available_memory",
        return_value=1_000_000_000,
    )
    def test_adjust_respects_max_bound(self, mock_mem: MagicMock) -> None:
        """Test that adjusted size respects max_batch_size."""
        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        sizer.set_bounds(min_size=1, max_size=20)
        # Budget=700M, actual=1M for 1 file => per_file=1M => new=700
        # But capped at max=20
        new_size = sizer.adjust_from_feedback(actual_memory=1_000_000, batch_size=1)
        assert new_size == 20
