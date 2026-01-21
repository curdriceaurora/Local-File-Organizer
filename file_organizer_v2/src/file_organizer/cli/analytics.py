#!/usr/bin/env python3
"""
Analytics CLI - Display comprehensive analytics dashboard.

This module provides a command-line interface for viewing storage analytics,
quality metrics, and organization insights.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, List

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from loguru import logger

from ..services.analytics import AnalyticsService
from ..utils.chart_generator import ChartGenerator

console = Console()


def display_storage_stats(stats, chart_gen: ChartGenerator) -> None:
    """Display storage statistics with charts."""
    console.print("\n[bold cyan]STORAGE STATISTICS[/bold cyan]")
    console.print("=" * 70)

    # Create table for stats
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="cyan")

    table.add_row("Total Size", stats.formatted_total_size)
    table.add_row("Files", str(stats.file_count))
    table.add_row("Directories", str(stats.directory_count))
    table.add_row("Space Saved", stats.formatted_saved_size)
    table.add_row("Savings", f"{stats.savings_percentage:.1f}%")

    console.print(table)

    # Show file type distribution
    if stats.size_by_type:
        console.print("\n[bold]File Type Distribution (by size)[/bold]")
        # Convert bytes to percentages
        total_size = sum(stats.size_by_type.values())
        if total_size > 0:
            type_percentages = {
                k: (v / total_size) * 100 for k, v in stats.size_by_type.items()
            }
            chart = chart_gen.create_pie_chart(
                type_percentages, "File Types", width=40
            )
            console.print(chart)

    # Show largest files
    if stats.largest_files:
        console.print("\n[bold]Largest Files (Top 10)[/bold]")
        file_table = Table(show_header=True)
        file_table.add_column("Size", style="green", justify="right")
        file_table.add_column("Type", style="yellow")
        file_table.add_column("Path", style="cyan")

        for file_info in stats.largest_files[:10]:
            size_str = stats._format_size(file_info.size)
            file_table.add_row(
                size_str, file_info.type, str(file_info.path.name)
            )

        console.print(file_table)


def display_quality_metrics(metrics) -> None:
    """Display quality metrics."""
    console.print("\n[bold cyan]QUALITY METRICS[/bold cyan]")
    console.print("=" * 70)

    # Overall score with color coding
    score_color = "green" if metrics.quality_score >= 70 else "yellow" if metrics.quality_score >= 50 else "red"

    console.print(
        f"\n[bold]Overall Quality Score:[/bold] [{score_color}]{metrics.formatted_score}[/{score_color}]"
    )

    # Individual metrics
    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Score", style="cyan", justify="right")
    table.add_column("Bar", style="green")

    def format_percentage_bar(value: float, width: int = 20) -> str:
        """Create a simple percentage bar."""
        filled = int(value * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"{bar} {value * 100:.0f}%"

    table.add_row(
        "Naming Compliance",
        f"{metrics.naming_compliance:.2f}",
        format_percentage_bar(metrics.naming_compliance),
    )
    table.add_row(
        "Structure Consistency",
        f"{metrics.structure_consistency:.2f}",
        format_percentage_bar(metrics.structure_consistency),
    )
    table.add_row(
        "Metadata Completeness",
        f"{metrics.metadata_completeness:.2f}",
        format_percentage_bar(metrics.metadata_completeness),
    )
    table.add_row(
        "Categorization Accuracy",
        f"{metrics.categorization_accuracy:.2f}",
        format_percentage_bar(metrics.categorization_accuracy),
    )

    console.print(table)


def display_duplicate_stats(stats) -> None:
    """Display duplicate statistics."""
    console.print("\n[bold cyan]DUPLICATE STATISTICS[/bold cyan]")
    console.print("=" * 70)

    if stats.total_duplicates == 0:
        console.print("\n[green]✓ No duplicates found![/green]")
        return

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="yellow")

    table.add_row("Duplicate Groups", str(stats.duplicate_groups))
    table.add_row("Total Duplicates", str(stats.total_duplicates))
    table.add_row("Space Wasted", stats.formatted_space_wasted)
    table.add_row("Space Recoverable", stats.formatted_recoverable)

    console.print(table)

    # Show duplicates by type
    if stats.by_type:
        console.print("\n[bold]Duplicates by File Type[/bold]")
        type_table = Table(show_header=True)
        type_table.add_column("Type", style="cyan")
        type_table.add_column("Count", style="yellow", justify="right")

        for file_type, count in sorted(
            stats.by_type.items(), key=lambda x: x[1], reverse=True
        )[:10]:
            type_table.add_row(file_type, str(count))

        console.print(type_table)


def display_time_savings(savings) -> None:
    """Display time savings information."""
    console.print("\n[bold cyan]TIME SAVINGS[/bold cyan]")
    console.print("=" * 70)

    # Highlight the time saved
    console.print(
        f"\n[bold green]⏱  Estimated Time Saved: {savings.formatted_time_saved}[/bold green]"
    )

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="cyan")

    table.add_row("Total Operations", str(savings.total_operations))
    table.add_row("Automated Operations", str(savings.automated_operations))
    table.add_row("Automation Rate", f"{savings.automation_percentage:.1f}%")
    table.add_row("Manual Time", savings._format_duration(savings.manual_time_seconds))
    table.add_row("Automated Time", savings._format_duration(savings.automated_time_seconds))

    console.print(table)


def display_file_distribution(distribution, chart_gen: ChartGenerator) -> None:
    """Display file distribution charts."""
    console.print("\n[bold cyan]FILE DISTRIBUTION[/bold cyan]")
    console.print("=" * 70)

    console.print(f"\n[bold]Total Files:[/bold] {distribution.total_files}")

    # By type
    if distribution.by_type:
        # Show top 10 types
        top_types = dict(
            sorted(distribution.by_type.items(), key=lambda x: x[1], reverse=True)[:10]
        )
        chart = chart_gen.create_bar_chart(top_types, "Top File Types", width=50)
        console.print(f"\n{chart}")

    # By size range
    if distribution.by_size_range:
        console.print("\n[bold]Files by Size Range[/bold]")
        size_table = Table(show_header=True)
        size_table.add_column("Range", style="cyan")
        size_table.add_column("Count", style="yellow", justify="right")
        size_table.add_column("Percentage", style="green", justify="right")

        total = distribution.total_files
        for range_name, count in distribution.by_size_range.items():
            percentage = (count / total) * 100 if total > 0 else 0
            size_table.add_row(range_name.title(), str(count), f"{percentage:.1f}%")

        console.print(size_table)


def analytics_command(args: Optional[List[str]] = None) -> int:
    """
    Execute the analytics command.

    Args:
        args: Command-line arguments (None to use sys.argv)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="Display comprehensive analytics dashboard for file organization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show analytics for current directory
  file-organizer analytics .

  # Show analytics with depth limit
  file-organizer analytics ~/Documents --max-depth 3

  # Export analytics to JSON
  file-organizer analytics ~/Downloads --export report.json

  # Export as text report
  file-organizer analytics ~/Pictures --export report.txt --format text
        """,
    )

    parser.add_argument(
        "directory", type=str, help="Directory to analyze"
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum directory depth to analyze (default: unlimited)",
    )

    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Export analytics to file",
    )

    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "text"],
        default="json",
        help="Export format (default: json)",
    )

    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Disable chart visualizations",
    )

    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging"
    )

    parsed_args = parser.parse_args(args)

    # Configure logging
    if parsed_args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="WARNING")

    # Validate directory
    directory = Path(parsed_args.directory).resolve()
    if not directory.exists():
        console.print(f"[red]Error: Directory not found: {directory}[/red]")
        return 1

    if not directory.is_dir():
        console.print(f"[red]Error: Not a directory: {directory}[/red]")
        return 1

    try:
        # Display banner
        console.print()
        console.print("=" * 70, style="bold blue")
        console.print("File Organizer Analytics Dashboard", style="bold blue", justify="center")
        console.print("=" * 70, style="bold blue")
        console.print()

        console.print(f"[bold]Analyzing:[/bold] {directory}")
        if parsed_args.max_depth:
            console.print(f"[bold]Max Depth:[/bold] {parsed_args.max_depth}")
        console.print()

        # Initialize services
        console.print("[dim]Initializing analytics service...[/dim]")
        analytics_service = AnalyticsService()
        chart_gen = ChartGenerator(use_unicode=not parsed_args.no_charts)

        # Generate dashboard
        console.print("[dim]Analyzing directory...[/dim]")
        dashboard = analytics_service.generate_dashboard(
            directory=directory,
            max_depth=parsed_args.max_depth,
        )

        console.print("[green]✓ Analysis complete[/green]\n")

        # Display dashboard sections
        display_storage_stats(dashboard.storage_stats, chart_gen)
        display_quality_metrics(dashboard.quality_metrics)
        display_duplicate_stats(dashboard.duplicate_stats)
        display_time_savings(dashboard.time_savings)
        display_file_distribution(dashboard.file_distribution, chart_gen)

        # Export if requested
        if parsed_args.export:
            export_path = Path(parsed_args.export)
            console.print(f"\n[dim]Exporting to {export_path}...[/dim]")
            analytics_service.export_dashboard(
                dashboard, export_path, format=parsed_args.format
            )
            console.print(f"[green]✓ Exported to {export_path}[/green]")

        # Footer
        console.print("\n" + "=" * 70)
        console.print(
            f"[dim]Generated: {dashboard.generated_at.strftime('%Y-%m-%d %H:%M:%S')} UTC[/dim]"
        )
        console.print("=" * 70 + "\n")

        return 0

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Operation cancelled by user[/yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.exception("Analytics generation failed")
        return 1


def main():
    """Main entry point for standalone execution."""
    sys.exit(analytics_command())


if __name__ == "__main__":
    main()
