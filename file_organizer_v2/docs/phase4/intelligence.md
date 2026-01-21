# Intelligence Guide

> **Phase 4 Feature** - Intelligent learning system that adapts to your file organization patterns and preferences.

## Overview

The Intelligence system learns from your actions and preferences to make smarter suggestions over time. It includes:

1. **Preference Tracking** (#50) - Learns from your corrections and choices
2. **Pattern Learning** (#49) - Identifies patterns in file organization
3. **Profile Management** (#51) - Save, share, and manage learned preferences

## Quick Start

### Track Your Preferences

The system automatically learns from your actions:

```python
from file_organizer.services.intelligence import PreferenceTracker, track_file_move
from pathlib import Path

# Create tracker
tracker = PreferenceTracker()

# System suggests moving PDF to Downloads
# You move it to Documents/Work instead
source = Path("~/Downloads/report.pdf")
destination = Path("~/Documents/Work/report.pdf")

# Track your correction
track_file_move(tracker, source, destination)

# Next time, system learns and suggests Documents/Work for similar PDFs
```

### Use Learned Preferences

```python
from file_organizer.services.intelligence import PreferenceType

# Get preference for similar file
new_file = Path("~/Downloads/proposal.pdf")
preference = tracker.get_preference(new_file, PreferenceType.FOLDER_MAPPING)

if preference:
    suggested_dest = preference.value
    confidence = preference.metadata.confidence
    print(f"Suggest moving to: {suggested_dest} (confidence: {confidence:.0%})")
```

### Manage Profiles

```bash
# Export your learned preferences
python -m file_organizer.cli.profile export my-preferences.json

# Share profile with team
python -m file_organizer.cli.profile import shared-preferences.json

# Switch between profiles
python -m file_organizer.cli.profile switch work-profile
```

## Preference Tracking

### How It Works

The preference tracker learns from:
- **File moves**: Where you move files instead of suggested locations
- **Renames**: How you rename files differently
- **Category changes**: When you override suggested categories
- **Manual overrides**: Any manual organization decisions

**Learning Process:**
1. System suggests an action based on AI analysis
2. You accept or correct the suggestion
3. Correction is tracked with metadata
4. Confidence increases with repeated patterns
5. Future suggestions adapt to your preferences

### Preference Types

**FOLDER_MAPPING**
Where files should be moved based on type/extension:
```python
# System learns: *.pdf files go to Documents/Work
tracker.add_correction(
    correction_type=CorrectionType.FILE_MOVE,
    preference_type=PreferenceType.FOLDER_MAPPING,
    key="*.pdf",
    value="Documents/Work",
    context={"file_type": "document"}
)
```

**NAMING_PATTERN**
How files should be renamed:
```python
# System learns: Screenshots should be renamed to Screenshot_{date}
tracker.add_correction(
    correction_type=CorrectionType.FILE_RENAME,
    preference_type=PreferenceType.NAMING_PATTERN,
    key="Screen Shot *",
    value="Screenshot_{date}_{time}",
    context={"original_pattern": "Screen Shot 2024-01-*"}
)
```

**CATEGORY_OVERRIDE**
Custom category assignments:
```python
# System learns: technical_spec.pdf is categorized as "Work", not "General"
tracker.add_correction(
    correction_type=CorrectionType.CATEGORY_CHANGE,
    preference_type=PreferenceType.CATEGORY_OVERRIDE,
    key="technical_spec.pdf",
    value="Work",
    context={"suggested_category": "General"}
)
```

### Confidence Scoring

Preferences have confidence scores (0.0 to 1.0) that adjust based on:

**Initial Confidence**: 0.5
- First correction creates preference with 50% confidence

**Increase Confidence**: +0.05 per success
- Each time the preference is successfully applied
- Caps at 0.98 maximum

**Decrease Confidence**: -0.1 per failure
- When preference doesn't work or is corrected again
- Floor at 0.1 minimum

**Frequency Boost**: Up to +0.45
- More corrections increase confidence faster
- Formula: `min(0.45, frequency * 0.05)`

```python
# Example confidence progression
tracker.add_correction(...)  # Confidence: 0.5
tracker.update_confidence(success=True)  # 0.55
tracker.update_confidence(success=True)  # 0.60
tracker.update_confidence(success=True)  # 0.65
tracker.update_confidence(success=False)  # 0.55 (decreased)
```

### Thread Safety

All operations are thread-safe:
```python
# Multiple threads can track corrections simultaneously
from concurrent.futures import ThreadPoolExecutor

def track_correction(file_path, destination):
    track_file_move(tracker, file_path, destination)

with ThreadPoolExecutor(max_workers=4) as executor:
    executor.map(track_correction, files, destinations)
```

### Persistence

Save and load preferences:

```python
# Export to JSON
data = tracker.export_data()
with open("preferences.json", "w") as f:
    json.dump(data, f, indent=2)

# Import from JSON
with open("preferences.json") as f:
    data = json.load(f)
tracker.import_data(data)
```

## Pattern Learning

### How It Works

Pattern learning analyzes your file organization to identify:
- **Naming conventions**: Common file naming patterns
- **Folder structures**: Directory organization patterns
- **File associations**: Which files belong together
- **Time-based patterns**: When certain actions occur

### Folder Learning

Learn folder organization patterns:

```python
from file_organizer.services.intelligence import FolderLearner

learner = FolderLearner()

# Analyze existing organization
patterns = learner.analyze_folder_structure(Path("~/Documents"))

print("Learned patterns:")
for pattern in patterns:
    print(f"  Pattern: {pattern.name}")
    print(f"  Files: {pattern.file_types}")
    print(f"  Confidence: {pattern.confidence:.2%}")
```

### Naming Pattern Analysis

Extract naming patterns from files:

```python
from file_organizer.services.intelligence import NamingAnalyzer

analyzer = NamingAnalyzer()

# Analyze file names
files = [
    "Report_2024_Q1.pdf",
    "Report_2024_Q2.pdf",
    "Report_2024_Q3.pdf",
]

patterns = analyzer.extract_patterns(files)
# Result: "Report_{year}_{quarter}.pdf"

# Apply learned pattern to new file
new_name = analyzer.apply_pattern(
    pattern=patterns[0],
    variables={"year": "2024", "quarter": "Q4"}
)
# Result: "Report_2024_Q4.pdf"
```

### Pattern Types

**Sequential Patterns**
```python
# Files: file_001.txt, file_002.txt, file_003.txt
# Pattern: file_{sequence:3d}.txt
```

**Date Patterns**
```python
# Files: backup_2024-01-15.zip, backup_2024-01-16.zip
# Pattern: backup_{date:YYYY-MM-DD}.zip
```

**Category Patterns**
```python
# Files: work_report.pdf, work_notes.txt, work_data.csv
# Pattern: {category}_{description}.{ext}
```

### Feedback Processing

Process user feedback to improve patterns:

```python
from file_organizer.services.intelligence import FeedbackProcessor

processor = FeedbackProcessor()

# User accepts suggestion
processor.track_feedback(
    action="file_move",
    suggested="Documents/Reports/report.pdf",
    actual="Documents/Reports/report.pdf",
    accepted=True
)

# User corrects suggestion
processor.track_feedback(
    action="file_move",
    suggested="Documents/General/notes.txt",
    actual="Documents/Work/notes.txt",
    accepted=False
)

# Get success rate
stats = processor.get_statistics()
print(f"Acceptance rate: {stats['acceptance_rate']:.1%}")
```

## Profile Management

### Creating Profiles

A profile contains all learned preferences and patterns:

```python
from file_organizer.services.intelligence import ProfileManager

manager = ProfileManager()

# Create new profile
profile = manager.create_profile(
    name="work-profile",
    description="Preferences for work documents"
)

# Add preferences to profile
profile.add_preference(
    preference_type=PreferenceType.FOLDER_MAPPING,
    key="*.pdf",
    value="Documents/Work/PDFs"
)

# Save profile
manager.save_profile(profile)
```

### Using CLI for Profile Management

```bash
# List all profiles
python -m file_organizer.cli.profile list

# Show profile details
python -m file_organizer.cli.profile show work-profile

# Export profile
python -m file_organizer.cli.profile export work-profile.json

# Import profile
python -m file_organizer.cli.profile import shared-profile.json

# Switch active profile
python -m file_organizer.cli.profile switch work-profile

# Merge profiles
python -m file_organizer.cli.profile merge profile1.json profile2.json -o merged.json

# Delete profile
python -m file_organizer.cli.profile delete old-profile
```

### Profile Structure

```json
{
  "name": "work-profile",
  "description": "Work organization preferences",
  "version": "1.0",
  "created": "2026-01-21T10:00:00Z",
  "updated": "2026-01-21T15:30:00Z",
  "preferences": {
    "folder_mappings": {
      "*.pdf": {
        "value": "Documents/Work/PDFs",
        "confidence": 0.85,
        "frequency": 15,
        "last_used": "2026-01-21T15:30:00Z"
      }
    },
    "naming_patterns": {
      "report_*": {
        "value": "Report_{date}_{description}",
        "confidence": 0.90,
        "frequency": 23,
        "last_used": "2026-01-21T14:00:00Z"
      }
    },
    "category_overrides": {
      "technical_docs": {
        "value": "Work",
        "confidence": 0.95,
        "frequency": 30,
        "last_used": "2026-01-21T15:00:00Z"
      }
    }
  },
  "patterns": [
    {
      "type": "folder_structure",
      "pattern": "Documents/{category}/{year}",
      "confidence": 0.88,
      "examples": [
        "Documents/Work/2024",
        "Documents/Personal/2024"
      ]
    }
  ],
  "statistics": {
    "total_corrections": 68,
    "acceptance_rate": 0.82,
    "average_confidence": 0.87,
    "most_used_preference": "*.pdf -> Documents/Work/PDFs"
  }
}
```

### Sharing Profiles

**Export for Sharing**
```python
from file_organizer.services.intelligence import ProfileExporter

exporter = ProfileExporter()

# Export with options
exporter.export(
    profile,
    output_path="team-profile.json",
    include_stats=False,        # Exclude personal statistics
    include_examples=True,      # Include pattern examples
    anonymize=True              # Remove personal file paths
)
```

**Import Shared Profile**
```python
from file_organizer.services.intelligence import ProfileImporter

importer = ProfileImporter()

# Import with conflict resolution
importer.import_profile(
    "team-profile.json",
    conflict_resolution="merge",  # or "replace", "keep"
    confidence_threshold=0.7      # Only import high-confidence preferences
)
```

### Profile Merging

Combine multiple profiles:

```python
from file_organizer.services.intelligence import ProfileMerger

merger = ProfileMerger()

# Merge two profiles
merged = merger.merge(
    profile1,
    profile2,
    conflict_resolution="highest_confidence",  # or "most_recent", "average"
    name="merged-profile"
)

# Weighted merge (prioritize one profile)
merged = merger.merge_weighted(
    profile1, weight1=0.7,
    profile2, weight2=0.3
)
```

### Profile Migration

Migrate profiles between versions:

```python
from file_organizer.services.intelligence import ProfileMigrator

migrator = ProfileMigrator()

# Migrate old profile format to new
migrated = migrator.migrate(
    old_profile_path="v1_profile.json",
    output_path="v2_profile.json",
    source_version="1.0",
    target_version="2.0"
)
```

## Preference Store

### Directory-Scoped Preferences

Store preferences per directory with inheritance:

```python
from file_organizer.services.intelligence import PreferenceStore

store = PreferenceStore()
store.load_preferences()

# Add preference for specific directory
store.add_preference(
    path=Path("~/Documents/Work"),
    preference_data={
        "folder_mappings": {"*.pdf": "PDFs"},
        "naming_patterns": {"report_*": "Report_{date}"},
        "confidence": 0.85
    }
)

# Get preference (falls back to parent directories)
pref = store.get_preference(
    path=Path("~/Documents/Work/Projects"),
    fallback_to_parent=True  # Uses ~/Documents/Work preferences
)
```

### Conflict Resolution

When multiple preferences conflict:

```python
# Preferences are weighted by:
# - Confidence (40%)
# - Recency (30%)
# - Frequency (30%)

# Example conflict:
# Preference 1: confidence=0.9, recent, frequency=10
# Preference 2: confidence=0.7, older, frequency=50
# Winner: Preference 1 (higher weighted score)
```

### Global vs. Directory Preferences

**Global Preferences**
Apply to all directories unless overridden:
```python
store.add_global_preference(
    preference_type="folder_mapping",
    key="*.jpg",
    value="Pictures"
)
```

**Directory Preferences**
Override global preferences for specific paths:
```python
store.add_preference(
    path=Path("~/Documents/Work"),
    preference_data={
        "folder_mappings": {
            "*.jpg": "Work/Screenshots"  # Overrides global
        }
    }
)
```

## Integration Examples

### With File Organization

```python
from file_organizer.core import FileOrganizer
from file_organizer.services.intelligence import PreferenceTracker

# Initialize organizer with intelligence
tracker = PreferenceTracker()
organizer = FileOrganizer(preference_tracker=tracker)

# Organize files (learns from corrections)
results = organizer.organize_directory(
    source=Path("~/Downloads"),
    destination=Path("~/Documents"),
    learn_preferences=True  # Enable learning
)

# Check learned preferences
stats = tracker.get_statistics()
print(f"Learned {stats['total_corrections']} preferences")
print(f"Average confidence: {stats['average_confidence']:.2%}")
```

### With Deduplication

```python
from file_organizer.services.deduplication import HashDeduplicator
from file_organizer.services.intelligence import PreferenceTracker

tracker = PreferenceTracker()
deduper = HashDeduplicator()

# Find duplicates
duplicates = deduper.find_duplicates(Path("~/Documents"))

# Track user's selection preferences
for group in duplicates:
    # User selects which file to keep
    selected = user_select(group)

    # Learn from selection
    tracker.add_correction(
        correction_type=CorrectionType.MANUAL_OVERRIDE,
        preference_type=PreferenceType.CUSTOM,
        key="duplicate_selection_strategy",
        value=get_selection_strategy(selected, group),
        context={"group_size": len(group)}
    )
```

## Statistics and Insights

### Preference Statistics

```python
stats = tracker.get_statistics()

print(f"Total corrections: {stats['total_corrections']}")
print(f"Total preferences: {stats['total_preferences']}")
print(f"Average confidence: {stats['average_confidence']:.2%}")
print(f"High confidence prefs: {stats['high_confidence_count']}")

# Per-type breakdown
for pref_type, count in stats['preferences_by_type'].items():
    print(f"  {pref_type}: {count}")
```

### Pattern Insights

```python
from file_organizer.services.intelligence import PatternExtractor

extractor = PatternExtractor()

# Extract insights from learned patterns
insights = extractor.get_insights(tracker)

print("Top patterns:")
for insight in insights.top_patterns:
    print(f"  {insight.pattern}: used {insight.frequency} times")

print(f"\nOrganization style: {insights.organization_style}")
print(f"Consistency score: {insights.consistency_score:.2%}")
```

## Best Practices

### 1. Let It Learn Gradually

Don't force the system to learn everything at once:
```python
# Good: Let it learn naturally over time
tracker = PreferenceTracker()
# Use normally, corrections tracked automatically

# Avoid: Bulk-loading all preferences at once
# (except when importing a trusted profile)
```

### 2. Review Confidence Scores

Check confidence before applying preferences:
```python
preference = tracker.get_preference(file_path, pref_type)

if preference and preference.metadata.confidence >= 0.7:
    # High confidence - apply automatically
    apply_preference(preference)
elif preference and preference.metadata.confidence >= 0.5:
    # Medium confidence - suggest to user
    suggest_preference(preference)
else:
    # Low confidence - don't use yet
    use_default_behavior()
```

### 3. Regular Exports

Back up learned preferences regularly:
```bash
# Weekly backup
python -m file_organizer.cli.profile export weekly-backup-$(date +%Y%m%d).json
```

### 4. Share Team Profiles

For teams with similar organization needs:
```bash
# Team lead exports profile
python -m file_organizer.cli.profile export team-profile.json --anonymize

# Team members import
python -m file_organizer.cli.profile import team-profile.json --merge
```

### 5. Monitor Learning Progress

Track how well the system is learning:
```python
# Check statistics regularly
stats = tracker.get_statistics()

if stats['average_confidence'] < 0.6:
    print("System needs more training data")
elif stats['average_confidence'] > 0.8:
    print("System is well-trained!")
```

## Troubleshooting

### Low Confidence Scores

**Problem**: Preferences stay at low confidence
**Solutions**:
- Provide more consistent corrections
- Review if patterns are actually consistent
- Check for conflicting preferences

### Incorrect Suggestions

**Problem**: System makes wrong suggestions
**Solutions**:
- Correct the suggestion (system will learn)
- Check for conflicting learned patterns
- Review preference confidence and frequency
- Reset specific preferences if needed:
  ```python
  tracker.remove_preference(pref_type, key)
  ```

### Profile Import Conflicts

**Problem**: Imported profile conflicts with existing preferences
**Solutions**:
```python
# Merge with conflict resolution
importer.import_profile(
    "new-profile.json",
    conflict_resolution="highest_confidence"
)

# Or keep existing preferences
importer.import_profile(
    "new-profile.json",
    conflict_resolution="keep"
)
```

## API Reference

See [API Reference](./api-reference.md) for complete API documentation.

## Related Documentation

- [Pattern Learning](./smart-features.md#pattern-learning) - Advanced pattern detection
- [Smart Suggestions](./smart-features.md#smart-suggestions) - Suggestion system
- [Profile Management CLI](./api-reference.md#profile-cli) - CLI reference
- [Analytics](./analytics.md) - Track learning progress
