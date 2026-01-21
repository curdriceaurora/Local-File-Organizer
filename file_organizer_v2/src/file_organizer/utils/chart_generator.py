"""
Chart generation module for terminal-based visualizations.
"""

from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generates ASCII/Unicode charts for terminal display."""

    def __init__(self, use_unicode: bool = True):
        """
        Initialize chart generator.

        Args:
            use_unicode: Use Unicode characters for better visuals
        """
        self.use_unicode = use_unicode

    def create_pie_chart(
        self,
        data: Dict[str, float],
        title: str,
        width: int = 40
    ) -> str:
        """
        Create ASCII pie chart.

        Args:
            data: Dictionary of labels to values
            title: Chart title
            width: Chart width

        Returns:
            Formatted chart string
        """
        if not data:
            return f"{title}\n(No data)"

        total = sum(data.values())
        if total == 0:
            return f"{title}\n(No data)"

        lines = [title, "=" * len(title)]

        for label, value in sorted(data.items(), key=lambda x: x[1], reverse=True):
            percentage = (value / total) * 100
            bar_length = int((percentage / 100) * width)
            bar = "█" * bar_length if self.use_unicode else "#" * bar_length
            lines.append(f"{label:20s} {bar} {percentage:5.1f}%")

        return "\n".join(lines)

    def create_bar_chart(
        self,
        data: Dict[str, int],
        title: str,
        width: int = 50
    ) -> str:
        """
        Create ASCII bar chart.

        Args:
            data: Dictionary of labels to counts
            title: Chart title
            width: Maximum bar width

        Returns:
            Formatted chart string
        """
        if not data:
            return f"{title}\n(No data)"

        max_value = max(data.values())
        if max_value == 0:
            return f"{title}\n(No data)"

        lines = [title, "=" * len(title)]

        for label, value in sorted(data.items(), key=lambda x: x[1], reverse=True):
            bar_length = int((value / max_value) * width)
            bar = "█" * bar_length if self.use_unicode else "#" * bar_length
            lines.append(f"{label:20s} {bar} {value}")

        return "\n".join(lines)

    def create_trend_line(
        self,
        data: List[Tuple[str, float]],
        title: str,
        height: int = 10
    ) -> str:
        """
        Create ASCII trend line.

        Args:
            data: List of (label, value) tuples
            title: Chart title
            height: Chart height

        Returns:
            Formatted chart string
        """
        if not data or len(data) < 2:
            return f"{title}\n(Insufficient data)"

        values = [v for _, v in data]
        min_val = min(values)
        max_val = max(values)

        if max_val == min_val:
            return f"{title}\n(No variation)"

        lines = [title, "=" * len(title)]

        # Normalize values to height
        normalized = [
            int(((v - min_val) / (max_val - min_val)) * (height - 1))
            for v in values
        ]

        # Build chart from top to bottom
        for level in range(height - 1, -1, -1):
            line = ""
            for val in normalized:
                if val == level:
                    line += "●" if self.use_unicode else "*"
                elif val > level:
                    line += "│" if self.use_unicode else "|"
                else:
                    line += " "
            lines.append(line)

        # Add labels
        labels = " ".join([l[:3] for l, _ in data])
        lines.append(labels)

        return "\n".join(lines)

    def create_sparkline(self, values: List[float]) -> str:
        """
        Create compact sparkline.

        Args:
            values: List of numeric values

        Returns:
            Sparkline string
        """
        if not values:
            return ""

        if not self.use_unicode:
            # ASCII fallback
            return "".join(["▴" if v > 0 else "▾" for v in values])

        min_val = min(values)
        max_val = max(values)

        if max_val == min_val:
            return "▄" * len(values)

        chars = "▁▂▃▄▅▆▇█"
        sparkline = ""

        for val in values:
            normalized = (val - min_val) / (max_val - min_val)
            index = int(normalized * (len(chars) - 1))
            sparkline += chars[index]

        return sparkline
