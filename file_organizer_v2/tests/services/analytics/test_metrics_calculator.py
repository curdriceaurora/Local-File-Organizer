"""Tests for MetricsCalculator."""

import pytest
from pathlib import Path
import tempfile

from file_organizer.services.analytics import MetricsCalculator


@pytest.fixture
def temp_directory():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files with various naming patterns
        (tmp_path / "good-name.txt").write_text("test")
        (tmp_path / "another_good_name.txt").write_text("test")
        (tmp_path / "Bad Name With Spaces.txt").write_text("test")
        (tmp_path / "UPPERCASE.TXT").write_text("test")

        yield tmp_path


class TestMetricsCalculator:
    """Test suite for MetricsCalculator."""

    def test_initialization(self):
        """Test calculator initialization."""
        calculator = MetricsCalculator()
        assert calculator is not None

    def test_calculate_quality_score(self):
        """Test quality score calculation."""
        calculator = MetricsCalculator()

        score = calculator.calculate_quality_score(
            total_files=100,
            organized_files=80,
            naming_compliance=0.9,
            structure_consistency=0.85,
        )

        assert 0 <= score <= 100
        assert score > 70  # Should be relatively high with good inputs

    def test_quality_score_boundaries(self):
        """Test quality score stays within valid range."""
        calculator = MetricsCalculator()

        # Test minimum
        score_min = calculator.calculate_quality_score(
            total_files=100, organized_files=0, naming_compliance=0.0, structure_consistency=0.0
        )
        assert score_min == 0

        # Test maximum
        score_max = calculator.calculate_quality_score(
            total_files=100, organized_files=100, naming_compliance=1.0, structure_consistency=1.0
        )
        assert score_max == 100

    def test_quality_score_zero_files(self):
        """Test quality score with zero files."""
        calculator = MetricsCalculator()

        score = calculator.calculate_quality_score(
            total_files=0, organized_files=0, naming_compliance=1.0, structure_consistency=1.0
        )

        assert score == 0

    def test_measure_naming_compliance(self, temp_directory):
        """Test naming convention compliance measurement."""
        calculator = MetricsCalculator()
        files = list(temp_directory.glob("*.txt"))

        compliance = calculator.measure_naming_compliance(files)

        assert 0 <= compliance <= 1
        # Should be between 0 and 1 based on the mix of good and bad names

    def test_naming_compliance_empty_list(self):
        """Test naming compliance with empty file list."""
        calculator = MetricsCalculator()

        compliance = calculator.measure_naming_compliance([])

        assert compliance == 1.0  # No files means perfect compliance

    def test_naming_compliance_all_good(self, temp_directory):
        """Test naming compliance with all good names."""
        calculator = MetricsCalculator()

        # Create files with good names only
        good_files = []
        for i in range(5):
            f = temp_directory / f"good-name-{i}.txt"
            f.write_text("test")
            good_files.append(f)

        compliance = calculator.measure_naming_compliance(good_files)

        assert compliance > 0.8  # Should be high

    def test_calculate_efficiency_gain(self):
        """Test efficiency gain calculation."""
        calculator = MetricsCalculator()

        gain = calculator.calculate_efficiency_gain(before_operations=100, after_operations=50)

        assert gain == 50.0  # 50% reduction

    def test_efficiency_gain_zero_before(self):
        """Test efficiency gain with zero before operations."""
        calculator = MetricsCalculator()

        gain = calculator.calculate_efficiency_gain(before_operations=0, after_operations=50)

        assert gain == 0.0

    def test_efficiency_gain_negative(self):
        """Test efficiency gain caps at 0 for negative values."""
        calculator = MetricsCalculator()

        # More operations after than before (negative gain)
        gain = calculator.calculate_efficiency_gain(before_operations=50, after_operations=100)

        assert gain == 0.0  # Should not be negative

    def test_estimate_time_saved(self):
        """Test time savings estimation."""
        calculator = MetricsCalculator()

        time_saved = calculator.estimate_time_saved(automated_ops=10, avg_manual_time_per_op=30)

        assert time_saved == 300  # 10 ops * 30 seconds

    def test_estimate_time_saved_zero_ops(self):
        """Test time savings with zero operations."""
        calculator = MetricsCalculator()

        time_saved = calculator.estimate_time_saved(automated_ops=0)

        assert time_saved == 0

    def test_estimate_time_saved_custom_time(self):
        """Test time savings with custom time per operation."""
        calculator = MetricsCalculator()

        time_saved = calculator.estimate_time_saved(automated_ops=5, avg_manual_time_per_op=60)

        assert time_saved == 300  # 5 ops * 60 seconds

    def test_calculate_improvement_metrics_no_previous(self):
        """Test improvement metrics without previous score."""
        calculator = MetricsCalculator()

        metrics = calculator.calculate_improvement_metrics(current_score=85.0)

        assert metrics["current_score"] == 85.0
        assert metrics["improvement"] == 0.0
        assert metrics["trend"] == "stable"

    def test_calculate_improvement_metrics_improving(self):
        """Test improvement metrics with improvement."""
        calculator = MetricsCalculator()

        metrics = calculator.calculate_improvement_metrics(
            current_score=85.0, previous_score=75.0
        )

        assert metrics["current_score"] == 85.0
        assert metrics["improvement"] == 10.0
        assert metrics["trend"] == "improving"

    def test_calculate_improvement_metrics_declining(self):
        """Test improvement metrics with decline."""
        calculator = MetricsCalculator()

        metrics = calculator.calculate_improvement_metrics(
            current_score=70.0, previous_score=85.0
        )

        assert metrics["current_score"] == 70.0
        assert metrics["improvement"] == -15.0
        assert metrics["trend"] == "declining"

    def test_calculate_improvement_metrics_stable(self):
        """Test improvement metrics when stable."""
        calculator = MetricsCalculator()

        metrics = calculator.calculate_improvement_metrics(
            current_score=80.0, previous_score=80.5
        )

        assert metrics["current_score"] == 80.0
        assert abs(metrics["improvement"]) < 1.0
        assert metrics["trend"] == "stable"

    def test_quality_score_weighted_components(self):
        """Test that quality score properly weights components."""
        calculator = MetricsCalculator()

        # Test with high organization rate but low compliance
        score1 = calculator.calculate_quality_score(
            total_files=100, organized_files=100, naming_compliance=0.0, structure_consistency=0.0
        )

        # Test with low organization rate but high compliance
        score2 = calculator.calculate_quality_score(
            total_files=100, organized_files=0, naming_compliance=1.0, structure_consistency=1.0
        )

        # Both should be less than perfect score
        assert score1 < 100
        assert score2 < 100
        # score1 = 1.0 * 0.4 + 0.0 * 0.3 + 0.0 * 0.3 = 40
        # score2 = 0.0 * 0.4 + 1.0 * 0.3 + 1.0 * 0.3 = 60
        assert score1 == 40.0
        assert score2 == 60.0
