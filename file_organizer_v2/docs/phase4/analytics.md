# Analytics Guide

> **Phase 4 Feature** - Comprehensive analytics dashboard (#56) for storage insights, quality metrics, and organization patterns.

## Overview

The Analytics system provides detailed insights into your file organization:

1. **Storage Analytics** - Size, distribution, and space usage
2. **Quality Metrics** - Organization quality scores
3. **Pattern Analysis** - Discover organization patterns
4. **Trend Tracking** - Monitor changes over time

## Quick Start

### CLI Dashboard

```bash
# Show analytics dashboard
python -m file_organizer.cli.analytics ~/Documents

# Export analytics report
python -m file_organizer.cli.analytics ~/Documents --export report.json

# Specific analysis
python -m file_organizer.cli.analytics ~/Documents --storage-only
python -m file_organizer.cli.analytics ~/Documents --quality-only
```

### Python API

```python
from file_organizer.services.analytics import AnalyticsService
from pathlib import Path

# Initialize analytics service
analytics = AnalyticsService()

# Analyze directory
results = analytics.analyze_directory(Path("~/Documents"))

# View storage stats
print(f"Total size: {results.storage.formatted_total_size}")
print(f"File count: {results.storage.file_count}")
print(f"Space saved: {results.storage.formatted_saved_size}")

# View quality metrics
print(f"Quality score: {results.quality.quality_score}/100")
print(f"Organization: {results.quality.organization_score:.1%}")
print(f"Naming: {results.quality.naming_score:.1%}")
```

## Storage Analytics

### Overview Statistics

```python
# Get storage statistics
storage = analytics.get_storage_stats(Path("~/Documents"))

print(f"Total Size: {storage.formatted_total_size}")
print(f"Files: {storage.file_count}")
print(f"Directories: {storage.directory_count}")
print(f"Average file size: {storage.avg_file_size}")
```

### Size Distribution

**By File Type**
```python
# Size distribution by file type
type_dist = storage.size_by_type

for file_type, size in sorted(type_dist.items(), key=lambda x: x[1], reverse=True):
    percentage = (size / storage.total_size) * 100
    print(f"{file_type}: {format_size(size)} ({percentage:.1f}%)")

# Example output:
# video: 15.2 GB (45.3%)
# image: 8.7 GB (25.9%)
# document: 5.1 GB (15.2%)
# audio: 3.2 GB (9.5%)
```

**By Directory**
```python
# Size by directory
dir_dist = storage.size_by_directory

for directory, size in sorted(dir_dist.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"{directory}: {format_size(size)}")
```

### Space Savings

```python
# Track space savings from deduplication
savings = storage.space_saved

print(f"Space saved: {storage.formatted_saved_size}")
print(f"Savings percentage: {storage.savings_percentage:.1f}%")
print(f"Duplicates removed: {storage.duplicates_removed}")
```

### Largest Files

```python
# Find largest files
largest = storage.largest_files

print("Top 10 largest files:")
for file_info in largest[:10]:
    print(f"{format_size(file_info.size)}: {file_info.path.name}")
    print(f"  Type: {file_info.type}")
    print(f"  Modified: {file_info.modified}")
```

### Growth Tracking

```python
# Track storage growth over time
growth = analytics.get_growth_stats(
    directory=Path("~/Documents"),
    period_days=30
)

print(f"Files added: {growth.files_added}")
print(f"Files removed: {growth.files_removed}")
print(f"Net change: {growth.net_change}")
print(f"Size change: {growth.size_change}")
```

## Quality Metrics

### Overall Quality Score

The quality score (0-100) measures how well-organized your files are:

```python
quality = analytics.get_quality_metrics(Path("~/Documents"))

print(f"Overall Quality: {quality.quality_score}/100")

# Quality breakdown
print(f"\nBreakdown:")
print(f"  Organization: {quality.organization_score:.1%}")
print(f"  Naming: {quality.naming_score:.1%}")
print(f"  Consistency: {quality.consistency_score:.1%}")
print(f"  Completeness: {quality.completeness_score:.1%}")
```

**Score Interpretation:**
- **90-100**: Excellent - Well-organized, consistent structure
- **70-89**: Good - Generally organized with minor issues
- **50-69**: Fair - Some organization, needs improvement
- **Below 50**: Poor - Requires significant organization

### Component Scores

**Organization Score**
Measures directory structure quality:
```python
org_score = quality.organization_score

# Factors:
# - Depth (too shallow/deep)
# - Categorization clarity
# - Logical grouping
# - Directory naming
```

**Naming Score**
Measures file naming quality:
```python
naming_score = quality.naming_score

# Factors:
# - Consistency
# - Descriptiveness
# - Special characters
# - Length appropriateness
# - Case consistency
```

**Consistency Score**
Measures pattern consistency:
```python
consistency_score = quality.consistency_score

# Factors:
# - Naming patterns
# - Directory structure
# - File placement
# - Categorization logic
```

**Completeness Score**
Measures metadata completeness:
```python
completeness_score = quality.completeness_score

# Factors:
# - Tags present
# - Descriptions
# - Categorization
# - Metadata fields
```

### Quality Issues

```python
# Get quality issues
issues = quality.issues

print(f"Found {len(issues)} quality issues:")
for issue in issues:
    print(f"\n{issue.severity}: {issue.title}")
    print(f"  Description: {issue.description}")
    print(f"  Affected files: {issue.file_count}")
    print(f"  Recommendation: {issue.recommendation}")

# Example issues:
# - "Inconsistent naming": 23 files use different patterns
# - "Deep nesting": 15 files are 8+ levels deep
# - "Poor categorization": 45 files in wrong categories
```

### Quality Recommendations

```python
# Get improvement recommendations
recommendations = quality.recommendations

for rec in recommendations:
    print(f"\n{rec.priority}: {rec.title}")
    print(f"  Impact: {rec.impact}")
    print(f"  Effort: {rec.effort}")
    print(f"  Action: {rec.action}")

# Example:
# Priority: High
# Title: "Consolidate duplicate naming patterns"
# Impact: +15 quality points
# Effort: Medium
# Action: "Rename 23 files to follow primary pattern"
```

## Pattern Analysis

### Discover Patterns

```python
# Analyze organization patterns
patterns = analytics.analyze_patterns(Path("~/Documents"))

print(f"Discovered {len(patterns.patterns)} patterns:")

for pattern in patterns.patterns:
    print(f"\nPattern: {pattern.name}")
    print(f"  Type: {pattern.type}")
    print(f"  Frequency: {pattern.frequency}")
    print(f"  Confidence: {pattern.confidence:.1%}")
    print(f"  Examples: {pattern.examples[:3]}")
```

### Pattern Types

**Naming Patterns**
```python
naming_patterns = patterns.naming_patterns

# Example patterns:
# - "Report_{year}_{month}.pdf" (used 45 times)
# - "IMG_{date}_{sequence}.jpg" (used 234 times)
# - "{project}_{version}.docx" (used 67 times)
```

**Folder Patterns**
```python
folder_patterns = patterns.folder_patterns

# Example patterns:
# - "Documents/{category}/{year}" (confidence: 0.95)
# - "Projects/{client}/{project}" (confidence: 0.88)
# - "Media/{type}/{date}" (confidence: 0.82)
```

**Category Patterns**
```python
category_patterns = patterns.category_patterns

# Shows how files are categorized:
# - "*.pdf" → "Documents" (92% consistency)
# - "IMG_*" → "Photos" (87% consistency)
# - "*_report.docx" → "Work" (95% consistency)
```

### Pattern Violations

```python
# Find files that don't follow patterns
violations = patterns.violations

print(f"Found {len(violations)} pattern violations:")
for violation in violations[:10]:
    print(f"\n{violation.file}: {violation.issue}")
    print(f"  Expected: {violation.expected_pattern}")
    print(f"  Suggestion: {violation.suggestion}")
```

## Trend Tracking

### Time Series Analysis

```python
from datetime import datetime, timedelta

# Get trends over time
trends = analytics.get_trends(
    directory=Path("~/Documents"),
    start_date=datetime.now() - timedelta(days=90),
    end_date=datetime.now(),
    granularity="week"  # or "day", "month"
)

# Plot storage growth
for point in trends.storage_over_time:
    print(f"{point.date}: {format_size(point.size)}")

# Plot quality score changes
for point in trends.quality_over_time:
    print(f"{point.date}: {point.score}/100")
```

### Activity Analysis

```python
# Analyze file activity
activity = analytics.get_activity_stats(
    directory=Path("~/Documents"),
    period_days=30
)

print(f"Activity Summary (last 30 days):")
print(f"  Files created: {activity.files_created}")
print(f"  Files modified: {activity.files_modified}")
print(f"  Files deleted: {activity.files_deleted}")
print(f"  Average daily activity: {activity.avg_daily_activity}")

# Most active days
for day, count in activity.most_active_days[:5]:
    print(f"  {day}: {count} operations")
```

### File Type Trends

```python
# Track file type growth
type_trends = analytics.get_type_trends(
    directory=Path("~/Documents"),
    period_days=90
)

for file_type, trend in type_trends.items():
    change = trend.current_count - trend.previous_count
    change_pct = (change / trend.previous_count) * 100 if trend.previous_count > 0 else 0

    print(f"{file_type}:")
    print(f"  Current: {trend.current_count} files ({format_size(trend.current_size)})")
    print(f"  Change: {change:+d} files ({change_pct:+.1f}%)")
```

## Visualization

### Generate Charts

```python
from file_organizer.utils.chart_generator import ChartGenerator

chart_gen = ChartGenerator()

# Pie chart: size by type
pie_chart = chart_gen.create_pie_chart(
    storage.size_by_type,
    title="Storage by File Type"
)
print(pie_chart)

# Bar chart: files by directory
bar_chart = chart_gen.create_bar_chart(
    storage.files_by_directory,
    title="Files by Directory"
)
print(bar_chart)

# Line chart: growth over time
line_chart = chart_gen.create_line_chart(
    trends.storage_over_time,
    title="Storage Growth",
    x_label="Date",
    y_label="Size (GB)"
)
print(line_chart)
```

### Export Visualizations

```python
# Export charts as images
chart_gen.export_chart(pie_chart, "storage_dist.png")
chart_gen.export_chart(bar_chart, "files_by_dir.png")
chart_gen.export_chart(line_chart, "growth_trend.png")

# Or export to PDF report
chart_gen.export_report(
    charts=[pie_chart, bar_chart, line_chart],
    output_path="analytics_report.pdf"
)
```

## Reporting

### Generate Reports

```python
# Generate comprehensive report
report = analytics.generate_report(
    directory=Path("~/Documents"),
    include_visualizations=True,
    format="html"  # or "pdf", "json", "markdown"
)

# Save report
report.save("analytics_report.html")

# Or get report data
report_data = report.to_dict()
```

### Report Sections

**Executive Summary**
```python
summary = report.executive_summary

print(f"Total Files: {summary.file_count}")
print(f"Total Size: {summary.total_size}")
print(f"Quality Score: {summary.quality_score}/100")
print(f"Key Findings: {summary.key_findings}")
```

**Storage Analysis**
```python
storage_section = report.storage_analysis

# Includes:
# - Size distributions
# - Largest files
# - Space savings
# - Growth trends
```

**Quality Analysis**
```python
quality_section = report.quality_analysis

# Includes:
# - Quality scores
# - Issues found
# - Recommendations
# - Comparison to best practices
```

**Pattern Analysis**
```python
pattern_section = report.pattern_analysis

# Includes:
# - Discovered patterns
# - Pattern violations
# - Consistency metrics
# - Suggestions
```

### Scheduled Reports (Planned Feature)

> **Note**: This feature is not yet implemented. It is planned for a future release.

The scheduled reports feature will enable automatic generation and delivery of analytics reports. This will require:
- `ReportScheduler` class implementation
- Background job scheduling system
- Email delivery integration
- Report format exporters (HTML, PDF)

For now, you can generate reports manually using `StorageAnalyzer`, `MetricsCalculator`, and `AnalyticsService`:

```python
# Current manual report generation
from file_organizer.services.analytics import AnalyticsService
from pathlib import Path

analytics = AnalyticsService()
stats = analytics.get_storage_stats(Path("~/Documents"))
# Process and save stats manually
```

## CLI Reference

### Basic Commands

```bash
# Show dashboard
python -m file_organizer.cli.analytics ~/Documents

# Storage analysis only
python -m file_organizer.cli.analytics ~/Documents --storage

# Quality analysis only
python -m file_organizer.cli.analytics ~/Documents --quality

# Pattern analysis only
python -m file_organizer.cli.analytics ~/Documents --patterns

# Trends analysis
python -m file_organizer.cli.analytics ~/Documents --trends --days 90
```

### Export Options

```bash
# Export to JSON
python -m file_organizer.cli.analytics ~/Documents --export report.json

# Export to HTML
python -m file_organizer.cli.analytics ~/Documents --export report.html

# Export to PDF
python -m file_organizer.cli.analytics ~/Documents --export report.pdf

# Export to Markdown
python -m file_organizer.cli.analytics ~/Documents --export report.md
```

### Filtering

```bash
# Analyze specific file types
python -m file_organizer.cli.analytics ~/Documents --types pdf,docx

# Analyze date range
python -m file_organizer.cli.analytics ~/Documents \
    --since "2024-01-01" \
    --until "2024-12-31"

# Exclude directories
python -m file_organizer.cli.analytics ~/Documents \
    --exclude ".git,node_modules,__pycache__"
```

### Comparison

```bash
# Compare two directories
python -m file_organizer.cli.analytics compare \
    ~/Documents/before \
    ~/Documents/after

# Compare over time
python -m file_organizer.cli.analytics compare \
    ~/Documents \
    --baseline "2024-01-01" \
    --current "2024-12-31"
```

## Integration Examples

### With Intelligence System

```python
from file_organizer.services.intelligence import PreferenceTracker

# Track organization effectiveness
tracker = PreferenceTracker()
analytics = AnalyticsService()

# Analyze quality improvement
initial_quality = analytics.get_quality_metrics(directory)
# ... organization work ...
final_quality = analytics.get_quality_metrics(directory)

improvement = final_quality.quality_score - initial_quality.quality_score
print(f"Quality improved by {improvement} points")
```

### With Deduplication

```python
from file_organizer.services.deduplication import HashDeduplicator

# Track space savings from deduplication
deduper = HashDeduplicator()

# Before deduplication
before_stats = analytics.get_storage_stats(directory)

# Deduplicate
duplicates = deduper.find_duplicates(directory)
# ... remove duplicates ...

# After deduplication
after_stats = analytics.get_storage_stats(directory)

space_saved = before_stats.total_size - after_stats.total_size
print(f"Saved {format_size(space_saved)} by removing duplicates")
```

### Dashboard Integration

```python
# Real-time dashboard
from file_organizer.dashboard import DashboardServer

dashboard = DashboardServer(
    analytics_service=analytics
)

# Start dashboard server
dashboard.start(
    host="localhost",
    port=8080,
    directory=Path("~/Documents"),
    refresh_interval=60  # seconds
)

# Access at: http://localhost:8080
```

## Best Practices

### 1. Regular Analysis

```bash
# Run analytics weekly
python -m file_organizer.cli.analytics ~/Documents --export weekly_report.json
```

### 2. Track Trends

```python
# Store analytics snapshots
snapshot = analytics.get_storage_stats(directory)
store_snapshot(snapshot, datetime.now())

# Compare over time
current = analytics.get_storage_stats(directory)
previous = load_snapshot(datetime.now() - timedelta(days=30))

compare_snapshots(current, previous)
```

### 3. Act on Recommendations

```python
# Get and implement recommendations
quality = analytics.get_quality_metrics(directory)

for rec in quality.recommendations:
    if rec.priority == "high" and rec.effort == "low":
        print(f"Quick win: {rec.title}")
        # Implement recommendation
```

### 4. Monitor Key Metrics

```python
# Define KPIs to track
kpis = {
    "quality_score": 75,  # Target: 75+
    "duplicate_ratio": 0.05,  # Target: <5%
    "naming_consistency": 0.8,  # Target: 80%+
}

# Check against targets
current = analytics.get_quality_metrics(directory)

for metric, target in kpis.items():
    actual = getattr(current, metric)
    status = "✓" if actual >= target else "✗"
    print(f"{status} {metric}: {actual:.1%} (target: {target:.1%})")
```

## Troubleshooting

### Slow Analysis

**Problem**: Analytics takes too long

**Solutions**:
```python
# Use sampling for large directories
analytics = AnalyticsService(sample_size=10000)

# Exclude large directories
analytics.analyze_directory(
    directory,
    exclude_patterns=["*.app", "node_modules"]
)

# Use caching
analytics = AnalyticsService(cache_enabled=True)
```

### Inaccurate Metrics

**Problem**: Metrics seem wrong

**Solutions**:
```bash
# Refresh cache
python -m file_organizer.cli.analytics ~/Documents --refresh-cache

# Verify file access
python -m file_organizer.cli.analytics ~/Documents --verify

# Check exclusions
python -m file_organizer.cli.analytics ~/Documents --show-excluded
```

## Performance Tips

### 1. Use Incremental Analysis

```python
# Only analyze changes since last run
analytics.analyze_incremental(
    directory,
    last_analysis_time=last_run
)
```

### 2. Cache Results

```python
# Enable caching
analytics = AnalyticsService(
    cache_enabled=True,
    cache_ttl=3600  # 1 hour
)
```

### 3. Parallel Processing

```python
# Use multiple workers
analytics = AnalyticsService(workers=4)
```

## API Reference

### AnalyticsService

```python
class AnalyticsService:
    def analyze_directory(
        self,
        directory: Path,
        include_subdirs: bool = True,
    ) -> AnalysisResults:
        """Analyze a directory."""

    def get_storage_stats(self, directory: Path) -> StorageStats:
        """Get storage statistics."""

    def get_quality_metrics(self, directory: Path) -> QualityMetrics:
        """Get quality metrics."""

    def analyze_patterns(self, directory: Path) -> PatternAnalysis:
        """Analyze organization patterns."""

    def get_trends(
        self,
        directory: Path,
        start_date: datetime,
        end_date: datetime,
    ) -> TrendAnalysis:
        """Get trend analysis."""
```

## Related Documentation

- [Intelligence Guide](./intelligence.md) - Learn from analytics
- [Deduplication Guide](./deduplication.md) - Track space savings
- [Smart Features Guide](./smart-features.md) - Improve based on metrics
