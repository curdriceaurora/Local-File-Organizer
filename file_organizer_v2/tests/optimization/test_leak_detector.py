"""Tests for LeakDetector - object count tracking and leak identification."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.optimization.leak_detector import (
    LeakDetector,
    LeakSuspect,
)


class TestLeakSuspect:
    """Tests for the LeakSuspect dataclass."""

    def test_create_leak_suspect(self) -> None:
        """Test creating a LeakSuspect instance."""
        suspect = LeakSuspect(
            type_name="MyClass",
            count_delta=100,
            size_delta=10240,
        )
        assert suspect.type_name == "MyClass"
        assert suspect.count_delta == 100
        assert suspect.size_delta == 10240

    def test_leak_suspect_frozen(self) -> None:
        """Test that LeakSuspect is immutable."""
        suspect = LeakSuspect(type_name="str", count_delta=5, size_delta=100)
        with pytest.raises(AttributeError):
            suspect.type_name = "int"  # type: ignore[misc]

    def test_leak_suspect_equality(self) -> None:
        """Test LeakSuspect equality comparison."""
        s1 = LeakSuspect(type_name="list", count_delta=10, size_delta=500)
        s2 = LeakSuspect(type_name="list", count_delta=10, size_delta=500)
        assert s1 == s2


class TestLeakDetectorInit:
    """Tests for LeakDetector initialization."""

    def test_default_init(self) -> None:
        """Test default initialization."""
        detector = LeakDetector()
        assert detector.is_tracking is False
        assert detector.check_count == 0

    def test_custom_min_count_delta(self) -> None:
        """Test custom min_count_delta."""
        detector = LeakDetector(min_count_delta=50)
        assert detector._min_count_delta == 50

    def test_custom_ignore_types(self) -> None:
        """Test custom ignore_types set."""
        detector = LeakDetector(ignore_types={"frame", "code"})
        assert "frame" in detector._ignore_types
        assert "code" in detector._ignore_types

    def test_invalid_min_count_delta_zero(self) -> None:
        """Test that min_count_delta=0 raises ValueError."""
        with pytest.raises(ValueError, match="min_count_delta must be >= 1"):
            LeakDetector(min_count_delta=0)

    def test_invalid_min_count_delta_negative(self) -> None:
        """Test that negative min_count_delta raises ValueError."""
        with pytest.raises(ValueError, match="min_count_delta must be >= 1"):
            LeakDetector(min_count_delta=-5)


class TestLeakDetectorStartStop:
    """Tests for start/stop lifecycle."""

    def test_start_sets_tracking(self) -> None:
        """Test that start() activates tracking."""
        detector = LeakDetector()
        detector.start()
        assert detector.is_tracking is True

    def test_stop_clears_tracking(self) -> None:
        """Test that stop() deactivates tracking."""
        detector = LeakDetector()
        detector.start()
        detector.stop()
        assert detector.is_tracking is False

    def test_stop_resets_check_count(self) -> None:
        """Test that stop() resets check count."""
        detector = LeakDetector(min_count_delta=1)
        detector.start()
        # Do a check to increment count
        detector.check()
        assert detector.check_count == 1
        detector.stop()
        assert detector.check_count == 0


class TestLeakDetectorCheck:
    """Tests for check() leak detection."""

    def test_check_without_start_raises(self) -> None:
        """Test that check() raises when not started."""
        detector = LeakDetector()
        with pytest.raises(RuntimeError, match="Leak detector not started"):
            detector.check()

    def test_check_increments_count(self) -> None:
        """Test that check() increments check_count."""
        detector = LeakDetector(min_count_delta=1)
        detector.start()
        detector.check()
        assert detector.check_count == 1
        detector.check()
        assert detector.check_count == 2

    def test_check_returns_list(self) -> None:
        """Test that check() returns a list."""
        detector = LeakDetector(min_count_delta=1)
        detector.start()
        result = detector.check()
        assert isinstance(result, list)

    def test_check_with_mocked_growth(self) -> None:
        """Test leak detection with simulated object growth."""
        detector = LeakDetector(min_count_delta=5)

        # Use a mock to simulate baseline and current snapshots
        baseline = {
            "list": MagicMock(count=100, total_size=5000, timestamp=1.0),
            "dict": MagicMock(count=50, total_size=3000, timestamp=1.0),
        }
        current = {
            "list": MagicMock(count=200, total_size=10000, timestamp=2.0),
            "dict": MagicMock(count=52, total_size=3100, timestamp=2.0),
        }

        detector._started = True
        detector._baseline = baseline  # type: ignore[assignment]

        with patch.object(LeakDetector, "_snapshot_types", return_value=current):
            suspects = detector.check()

        # "list" grew by 100 (>= 5 threshold)
        # "dict" grew by 2 (< 5 threshold, not a suspect)
        assert len(suspects) == 1
        assert suspects[0].type_name == "list"
        assert suspects[0].count_delta == 100
        assert suspects[0].size_delta == 5000

    def test_check_ignores_specified_types(self) -> None:
        """Test that ignored types are excluded from suspects."""
        detector = LeakDetector(min_count_delta=5, ignore_types={"list"})

        baseline = {
            "list": MagicMock(count=100, total_size=5000, timestamp=1.0),
        }
        current = {
            "list": MagicMock(count=200, total_size=10000, timestamp=2.0),
        }

        detector._started = True
        detector._baseline = baseline  # type: ignore[assignment]

        with patch.object(LeakDetector, "_snapshot_types", return_value=current):
            suspects = detector.check()

        assert len(suspects) == 0

    def test_check_detects_new_types(self) -> None:
        """Test detection of types that appear after baseline."""
        detector = LeakDetector(min_count_delta=5)

        baseline: dict[str, MagicMock] = {}
        current = {
            "NewClass": MagicMock(count=50, total_size=5000, timestamp=2.0),
        }

        detector._started = True
        detector._baseline = baseline  # type: ignore[assignment]

        with patch.object(LeakDetector, "_snapshot_types", return_value=current):
            suspects = detector.check()

        assert len(suspects) == 1
        assert suspects[0].type_name == "NewClass"
        assert suspects[0].count_delta == 50

    def test_check_sorted_by_count_delta(self) -> None:
        """Test that suspects are sorted by count_delta descending."""
        detector = LeakDetector(min_count_delta=5)

        baseline = {
            "TypeA": MagicMock(count=10, total_size=100, timestamp=1.0),
            "TypeB": MagicMock(count=10, total_size=100, timestamp=1.0),
            "TypeC": MagicMock(count=10, total_size=100, timestamp=1.0),
        }
        current = {
            "TypeA": MagicMock(count=30, total_size=300, timestamp=2.0),
            "TypeB": MagicMock(count=110, total_size=1100, timestamp=2.0),
            "TypeC": MagicMock(count=60, total_size=600, timestamp=2.0),
        }

        detector._started = True
        detector._baseline = baseline  # type: ignore[assignment]

        with patch.object(LeakDetector, "_snapshot_types", return_value=current):
            suspects = detector.check()

        assert len(suspects) == 3
        assert suspects[0].type_name == "TypeB"  # delta=100
        assert suspects[1].type_name == "TypeC"  # delta=50
        assert suspects[2].type_name == "TypeA"  # delta=20


class TestLeakDetectorResetBaseline:
    """Tests for reset_baseline method."""

    def test_reset_baseline_without_start_raises(self) -> None:
        """Test that reset_baseline raises when not started."""
        detector = LeakDetector()
        with pytest.raises(RuntimeError, match="Leak detector not started"):
            detector.reset_baseline()

    def test_reset_baseline_resets_check_count(self) -> None:
        """Test that reset_baseline resets check count."""
        detector = LeakDetector(min_count_delta=1)
        detector.start()
        detector.check()
        assert detector.check_count == 1
        detector.reset_baseline()
        assert detector.check_count == 0

    def test_reset_baseline_clears_previous_growth(self) -> None:
        """Test that reset_baseline establishes new comparison point."""
        detector = LeakDetector(min_count_delta=5)

        # Simulate: baseline has 100 lists, grows to 200, then reset
        baseline_initial = {
            "list": MagicMock(count=100, total_size=5000, timestamp=1.0),
        }
        after_growth = {
            "list": MagicMock(count=200, total_size=10000, timestamp=2.0),
        }
        after_reset = {
            "list": MagicMock(count=203, total_size=10150, timestamp=3.0),
        }

        detector._started = True
        detector._baseline = baseline_initial  # type: ignore[assignment]

        # First check: 100 growth (suspect)
        with patch.object(LeakDetector, "_snapshot_types", return_value=after_growth):
            suspects = detector.check()
            assert len(suspects) == 1

        # Reset baseline to current state (200 lists)
        with patch.object(LeakDetector, "_snapshot_types", return_value=after_growth):
            detector.reset_baseline()

        # Check after reset: only 3 growth (below threshold)
        with patch.object(LeakDetector, "_snapshot_types", return_value=after_reset):
            suspects = detector.check()
            assert len(suspects) == 0
