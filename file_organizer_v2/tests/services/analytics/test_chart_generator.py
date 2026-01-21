"""Tests for ChartGenerator."""

import pytest
from file_organizer.utils.chart_generator import ChartGenerator


class TestChartGenerator:
    """Test suite for ChartGenerator."""

    def test_initialization_unicode(self):
        """Test initialization with Unicode support."""
        chart_gen = ChartGenerator(use_unicode=True)
        assert chart_gen.use_unicode is True

    def test_initialization_ascii(self):
        """Test initialization with ASCII only."""
        chart_gen = ChartGenerator(use_unicode=False)
        assert chart_gen.use_unicode is False

    def test_create_pie_chart(self):
        """Test pie chart creation."""
        chart_gen = ChartGenerator()
        data = {"Python": 45.0, "JavaScript": 30.0, "Go": 15.0, "Rust": 10.0}

        chart = chart_gen.create_pie_chart(data, "Languages", width=40)

        assert isinstance(chart, str)
        assert "Languages" in chart
        assert "Python" in chart
        assert "45.0%" in chart

    def test_create_pie_chart_empty(self):
        """Test pie chart with empty data."""
        chart_gen = ChartGenerator()
        chart = chart_gen.create_pie_chart({}, "Empty Chart", width=40)

        assert "No data" in chart

    def test_create_pie_chart_zero_total(self):
        """Test pie chart with zero total."""
        chart_gen = ChartGenerator()
        data = {"Item1": 0, "Item2": 0}

        chart = chart_gen.create_pie_chart(data, "Zero Chart", width=40)

        assert "No data" in chart

    def test_create_bar_chart(self):
        """Test bar chart creation."""
        chart_gen = ChartGenerator()
        data = {"images": 150, "videos": 80, "documents": 200, "audio": 50}

        chart = chart_gen.create_bar_chart(data, "File Types", width=50)

        assert isinstance(chart, str)
        assert "File Types" in chart
        assert "images" in chart
        assert "200" in chart  # documents count

    def test_create_bar_chart_empty(self):
        """Test bar chart with empty data."""
        chart_gen = ChartGenerator()
        chart = chart_gen.create_bar_chart({}, "Empty Bar", width=50)

        assert "No data" in chart

    def test_create_bar_chart_zero_max(self):
        """Test bar chart with all zero values."""
        chart_gen = ChartGenerator()
        data = {"Item1": 0, "Item2": 0}

        chart = chart_gen.create_bar_chart(data, "Zero Bar", width=50)

        assert "No data" in chart

    def test_create_trend_line(self):
        """Test trend line creation."""
        chart_gen = ChartGenerator()
        data = [("Jan", 10.0), ("Feb", 15.0), ("Mar", 12.0), ("Apr", 20.0)]

        chart = chart_gen.create_trend_line(data, "Monthly Trend", height=10)

        assert isinstance(chart, str)
        assert "Monthly Trend" in chart
        # Should contain some visual representation

    def test_create_trend_line_insufficient_data(self):
        """Test trend line with insufficient data points."""
        chart_gen = ChartGenerator()
        data = [("Jan", 10.0)]

        chart = chart_gen.create_trend_line(data, "Insufficient Data", height=10)

        assert "Insufficient data" in chart

    def test_create_trend_line_no_variation(self):
        """Test trend line with no variation."""
        chart_gen = ChartGenerator()
        data = [("Jan", 10.0), ("Feb", 10.0), ("Mar", 10.0)]

        chart = chart_gen.create_trend_line(data, "No Variation", height=10)

        assert "No variation" in chart

    def test_create_sparkline(self):
        """Test sparkline creation."""
        chart_gen = ChartGenerator(use_unicode=True)
        values = [1.0, 2.0, 3.0, 2.5, 4.0, 3.0, 5.0]

        sparkline = chart_gen.create_sparkline(values)

        assert isinstance(sparkline, str)
        assert len(sparkline) == len(values)

    def test_create_sparkline_empty(self):
        """Test sparkline with empty values."""
        chart_gen = ChartGenerator()
        sparkline = chart_gen.create_sparkline([])

        assert sparkline == ""

    def test_create_sparkline_no_variation(self):
        """Test sparkline with no variation."""
        chart_gen = ChartGenerator()
        values = [5.0, 5.0, 5.0, 5.0]

        sparkline = chart_gen.create_sparkline(values)

        assert len(sparkline) == len(values)

    def test_create_sparkline_ascii_fallback(self):
        """Test sparkline ASCII fallback."""
        chart_gen = ChartGenerator(use_unicode=False)
        values = [1.0, 2.0, 3.0, 2.0, 1.0]

        sparkline = chart_gen.create_sparkline(values)

        assert isinstance(sparkline, str)

    def test_unicode_vs_ascii_pie_chart(self):
        """Test difference between Unicode and ASCII pie charts."""
        data = {"A": 50.0, "B": 30.0, "C": 20.0}

        chart_unicode = ChartGenerator(use_unicode=True).create_pie_chart(
            data, "Test", width=20
        )
        chart_ascii = ChartGenerator(use_unicode=False).create_pie_chart(
            data, "Test", width=20
        )

        # Both should produce output
        assert len(chart_unicode) > 0
        assert len(chart_ascii) > 0

        # Unicode version should contain block characters
        assert "█" in chart_unicode or "▓" in chart_unicode
        # ASCII version should use # character
        assert "#" in chart_ascii

    def test_unicode_vs_ascii_bar_chart(self):
        """Test difference between Unicode and ASCII bar charts."""
        data = {"X": 100, "Y": 50, "Z": 75}

        chart_unicode = ChartGenerator(use_unicode=True).create_bar_chart(
            data, "Test", width=30
        )
        chart_ascii = ChartGenerator(use_unicode=False).create_bar_chart(
            data, "Test", width=30
        )

        # Both should produce output
        assert len(chart_unicode) > 0
        assert len(chart_ascii) > 0

    def test_chart_sorting(self):
        """Test that charts sort data by value."""
        chart_gen = ChartGenerator()
        data = {"Small": 10, "Large": 100, "Medium": 50}

        chart = chart_gen.create_bar_chart(data, "Sorted", width=30)

        # Find positions of each item
        lines = chart.split("\n")
        large_pos = next(i for i, line in enumerate(lines) if "Large" in line)
        medium_pos = next(i for i, line in enumerate(lines) if "Medium" in line)
        small_pos = next(i for i, line in enumerate(lines) if "Small" in line)

        # Should be sorted descending
        assert large_pos < medium_pos < small_pos

    def test_chart_width_parameter(self):
        """Test that width parameter affects chart output."""
        chart_gen = ChartGenerator()
        data = {"Item": 100.0}

        chart_narrow = chart_gen.create_pie_chart(data, "Test", width=10)
        chart_wide = chart_gen.create_pie_chart(data, "Test", width=50)

        # Wide chart should have more characters (though exact length varies)
        assert len(chart_wide) >= len(chart_narrow)

    def test_trend_line_height_parameter(self):
        """Test that height parameter affects trend line."""
        chart_gen = ChartGenerator()
        data = [("A", 1.0), ("B", 2.0), ("C", 3.0)]

        chart_short = chart_gen.create_trend_line(data, "Test", height=5)
        chart_tall = chart_gen.create_trend_line(data, "Test", height=15)

        # Taller chart should have more lines
        assert chart_tall.count("\n") > chart_short.count("\n")
