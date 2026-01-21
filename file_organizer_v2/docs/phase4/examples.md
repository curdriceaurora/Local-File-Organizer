# Phase 4 Usage Examples

> Practical examples demonstrating Phase 4 features in real-world scenarios.

## Table of Contents

- [Complete Workflows](#complete-workflows)
- [Deduplication Examples](#deduplication-examples)
- [Intelligence Examples](#intelligence-examples)
- [History & Undo Examples](#history--undo-examples)
- [Smart Features Examples](#smart-features-examples)
- [Analytics Examples](#analytics-examples)
- [Integration Examples](#integration-examples)

## Complete Workflows

### Workflow 1: Organize Downloads with Learning

Organize your Downloads folder while learning your preferences:

```python
from pathlib import Path
from file_organizer.core import FileOrganizer
from file_organizer.services.intelligence import PreferenceTracker
from file_organizer.history import HistoryTracker, TransactionManager

# Initialize services
preference_tracker = PreferenceTracker()
history_tracker = HistoryTracker()
tx_manager = TransactionManager()
organizer = FileOrganizer(
    preference_tracker=preference_tracker,
    history_tracker=history_tracker
)

# Start transaction
with tx_manager.transaction("Organize Downloads") as tx_id:
    # Organize files
    results = organizer.organize_directory(
        source=Path("~/Downloads"),
        destination=Path("~/Documents"),
        transaction_id=tx_id,
        learn_preferences=True
    )

    print(f"Organized {results.files_moved} files")
    print(f"Learned {len(preference_tracker.get_all_preferences())} preferences")

# View learned preferences
stats = preference_tracker.get_statistics()
print(f"\nPreference Statistics:")
print(f"  Total corrections: {stats['total_corrections']}")
print(f"  Average confidence: {stats['average_confidence']:.2%}")

# If something went wrong, undo entire transaction
# undo_manager = UndoManager()
# undo_manager.undo_transaction(tx_id)
```

### Workflow 2: Clean Up with Deduplication and Analytics

Clean up a directory, remove duplicates, and analyze results:

```python
from pathlib import Path
from file_organizer.services.deduplication import HashDeduplicator
from file_organizer.services.analytics import AnalyticsService
from file_organizer.history import TransactionManager

# Initialize services
deduper = HashDeduplicator(algorithm="sha256")
analytics = AnalyticsService()
tx_manager = TransactionManager()

directory = Path("~/Documents")

# Analyze before
print("Before cleanup:")
before_stats = analytics.get_storage_stats(directory)
print(f"  Total size: {before_stats.formatted_total_size}")
print(f"  Files: {before_stats.file_count}")

# Helper function to format file sizes
def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

# Find and remove duplicates
with tx_manager.transaction("Deduplication cleanup") as tx_id:
    duplicates = deduper.find_duplicates(directory)

    removed_count = 0
    for file_hash, files in duplicates.items():
        # Use preference-aware selection to choose file to keep
        # For this example, we'll keep the first file
        to_keep = files[0]
        to_remove = files[1:]

        for file_path in to_remove:
            file_path.unlink()
            removed_count += 1

    print(f"\nRemoved {removed_count} duplicate files")

# Analyze after
print("\nAfter cleanup:")
after_stats = analytics.get_storage_stats(directory)
print(f"  Total size: {after_stats.formatted_total_size}")
print(f"  Files: {after_stats.file_count}")

# Calculate savings
space_saved = before_stats.total_size - after_stats.total_size
print(f"\nSpace saved: {format_size(space_saved)}")
```

### Workflow 3: Smart Organization with Suggestions

Use smart suggestions for intelligent file organization:

```python
from pathlib import Path
from file_organizer.services.smart_suggestions import SmartSuggestionEngine
from file_organizer.services.auto_tagging import AutoTaggingService
from file_organizer.services.intelligence import PreferenceTracker

# Initialize services
preference_tracker = PreferenceTracker()
engine = SmartSuggestionEngine(preference_tracker=preference_tracker)
tagger = AutoTaggingService()

# Process files in Downloads
downloads = Path("~/Downloads")

for file_path in downloads.glob("*"):
    if not file_path.is_file():
        continue

    print(f"\nProcessing: {file_path.name}")

    # Get smart suggestions
    suggestions = engine.get_suggestions(
        file_path,
        min_confidence=0.7
    )

    # Show top destination suggestion
    if suggestions.destinations:
        dest = suggestions.destinations[0]
        print(f"  Suggested location: {dest.path}")
        print(f"  Confidence: {dest.confidence:.0%}")
        print(f"  Reason: {dest.reason}")

        # Ask user
        response = input("  Accept suggestion? (y/n): ")

        if response.lower() == 'y':
            # Move file
            file_path.rename(dest.path / file_path.name)

            # Track acceptance
            engine.track_acceptance(file_path, dest, accepted=True)
            print("  ✓ Moved")
        else:
            # Track rejection
            engine.track_acceptance(file_path, dest, accepted=False)
            print("  ✗ Skipped")

    # Auto-tag the file
    tag_suggestions = tagger.suggest_tags(file_path, top_n=5)
    if tag_suggestions:
        tags = [tag for tag, _ in tag_suggestions]
        tagger.apply_tags(file_path, tags)
        print(f"  Tags: {', '.join(tags)}")
```

## Deduplication Examples

### Example 1: Find and Review Duplicate Photos

```python
from pathlib import Path
from file_organizer.services.deduplication import ImageDeduplicator, ImageQualityAnalyzer

# Initialize
deduper = ImageDeduplicator()
quality_analyzer = ImageQualityAnalyzer()

# Find similar photos
duplicates = deduper.find_duplicates(
    directory=Path("~/Pictures"),
    similarity_threshold=0.90,
    algorithm="phash",
    recursive=True
)

print(f"Found {len(duplicates)} groups of similar images\n")

# Process each group
for i, group in enumerate(duplicates, 1):
    print(f"Group {i}: {len(group)} similar images")

    # Analyze quality
    analyzed = []
    for img_path in group:
        quality = quality_analyzer.analyze(img_path)
        analyzed.append((img_path, quality))

        print(f"  {img_path.name}")
        print(f"    Resolution: {quality.width}x{quality.height}")
        print(f"    Quality score: {quality.overall_score:.2f}")
        print(f"    Size: {format_size(img_path.stat().st_size)}")

    # Keep highest quality
    best = max(analyzed, key=lambda x: x[1].overall_score)
    print(f"\n  Recommended: Keep {best[0].name}")
    print(f"  (Highest quality: {best[1].overall_score:.2f})")

    # User confirmation
    response = input("\n  Delete other copies? (y/n): ")
    if response.lower() == 'y':
        for img_path, _ in analyzed:
            if img_path != best[0]:
                img_path.unlink()
                print(f"  Deleted: {img_path.name}")
    print()
```

### Example 2: Find Similar Documents

```python
from pathlib import Path
from file_organizer.services.deduplication import DocumentDeduplicator

# Initialize
deduper = DocumentDeduplicator(model_name="qwen2.5:3b")

# Find similar documents
similar_docs = deduper.find_similar_documents(
    directory=Path("~/Documents"),
    similarity_threshold=0.85,
    recursive=True,
    file_extensions=[".txt", ".md", ".pdf", ".docx"]
)

print(f"Found {len(similar_docs)} groups of similar documents\n")

# Review each group
for i, group in enumerate(similar_docs, 1):
    print(f"Group {i}:")

    # Show primary document (most words)
    primary = max(group, key=lambda d: d.word_count)
    print(f"  Primary: {primary.path.name}")
    print(f"  Summary: {primary.summary}")
    print(f"  Word count: {primary.word_count}")

    # Show similar documents
    print(f"\n  Similar documents:")
    for doc in group:
        if doc != primary:
            print(f"    {doc.path.name}")
            print(f"      Similarity: {doc.similarity_score:.2%}")
            print(f"      Preview: {doc.preview[:100]}...")

    print()
```

### Example 3: Batch Hash-Based Deduplication

```bash
#!/bin/bash
# dedupe_all.sh - Clean up multiple directories

# Downloads
echo "Cleaning Downloads..."
python -m file_organizer.cli.dedupe ~/Downloads \
    --strategy newest \
    --algorithm md5 \
    --batch

# Documents
echo "Cleaning Documents..."
python -m file_organizer.cli.dedupe ~/Documents \
    --strategy oldest \
    --include "*.pdf" \
    --include "*.docx" \
    --batch

# Pictures
echo "Cleaning Pictures..."
python -m file_organizer.cli.dedupe ~/Pictures \
    --strategy largest \
    --include "*.jpg" \
    --include "*.png" \
    --min-size 1048576 \
    --batch

echo "Done!"
```

## Intelligence Examples

### Example 1: Learn Organization Patterns

```python
from pathlib import Path
from file_organizer.services.intelligence import (
    PreferenceTracker,
    track_file_move,
    track_category_change
)

tracker = PreferenceTracker()

# Simulate user organizing files
moves = [
    (Path("~/Downloads/report.pdf"), Path("~/Documents/Work/Reports/report.pdf")),
    (Path("~/Downloads/invoice.pdf"), Path("~/Documents/Work/Invoices/invoice.pdf")),
    (Path("~/Downloads/photo.jpg"), Path("~/Pictures/2024/photo.jpg")),
    (Path("~/Downloads/vacation.jpg"), Path("~/Pictures/2024/Vacation/vacation.jpg")),
]

for source, dest in moves:
    track_file_move(tracker, source, dest)
    print(f"Tracked: {source.name} → {dest.parent}")

# Check learned patterns
print("\nLearned preferences:")
prefs = tracker.get_all_preferences()

for pref in prefs[:5]:
    print(f"  {pref.key} → {pref.value}")
    print(f"  Confidence: {pref.metadata.confidence:.0%}")
    print()
```

### Example 2: Profile Management for Teams

```python
from pathlib import Path
from file_organizer.services.intelligence import (
    ProfileManager,
    ProfileExporter,
    ProfileImporter
)

# Team lead creates and exports profile
manager = ProfileManager()

# Create work profile
profile = manager.create_profile(
    name="team-work-profile",
    description="Standard work organization for the team"
)

# Add team preferences
profile.add_preference(
    preference_type="folder_mapping",
    key="*.pdf",
    value="Documents/Work/PDFs"
)
profile.add_preference(
    preference_type="naming_pattern",
    key="report_*",
    value="Report_{date}_{description}"
)

# Export for team
exporter = ProfileExporter()
exporter.export(
    profile,
    output_path="team_profile.json",
    anonymize=True  # Remove personal paths
)

print("Team profile exported to team_profile.json")

# Team member imports profile
importer = ProfileImporter()
imported = importer.import_profile(
    "team_profile.json",
    conflict_resolution="merge"
)

print(f"Imported profile with {len(imported.preferences)} preferences")
```

### Example 3: Adaptive Learning System

```python
from pathlib import Path
from file_organizer.services.intelligence import PreferenceTracker, FeedbackProcessor

from file_organizer.core.preferences import PreferenceType

tracker = PreferenceTracker()
feedback = FeedbackProcessor()

# System makes suggestions and learns from feedback
files_to_organize = [
    Path("~/Downloads/quarterly_report_Q1.pdf"),
    Path("~/Downloads/meeting_notes_jan.txt"),
    Path("~/Downloads/budget_2024.xlsx"),
]

for file_path in files_to_organize:
    # Get suggestion based on learned preferences
    preference = tracker.get_preference(
        file_path.suffix,
        PreferenceType.FOLDER_MAPPING
    )

    if preference:
        suggested_dest = Path(preference.value) / file_path.name
        print(f"\nFile: {file_path.name}")
        print(f"Suggested: {suggested_dest}")
        print(f"Confidence: {preference.metadata.confidence:.0%}")

        # User decides
        response = input("Accept? (y/n): ")

        if response.lower() == 'y':
            # Move file
            file_path.rename(suggested_dest)

            # Track acceptance
            feedback.track_feedback(
                action="file_move",
                suggested=str(suggested_dest),
                actual=str(suggested_dest),
                accepted=True
            )

            # Increase confidence
            tracker.update_confidence(success=True)
        else:
            # User provides better location
            actual_dest = input("Better location: ")

            # Track correction
            feedback.track_feedback(
                action="file_move",
                suggested=str(suggested_dest),
                actual=actual_dest,
                accepted=False
            )

            # Learn from correction
            track_file_move(tracker, file_path, Path(actual_dest))

# View learning progress
stats = feedback.get_statistics()
print(f"\nAcceptance rate: {stats['acceptance_rate']:.1%}")
```

## History & Undo Examples

### Example 1: Undo Accidental Organization

```python
from pathlib import Path
from file_organizer.core import FileOrganizer
from file_organizer.history import HistoryTracker, TransactionManager
from file_organizer.undo import UndoManager

# Organize files with history tracking
tracker = HistoryTracker()
tx_manager = TransactionManager()
organizer = FileOrganizer(history_tracker=tracker)

# Organize
with tx_manager.transaction("Organize Downloads") as tx_id:
    results = organizer.organize_directory(
        source=Path("~/Downloads"),
        destination=Path("~/Documents"),
        transaction_id=tx_id
    )

    print(f"Moved {results.files_moved} files")

# Oops! Wrong organization
print("\nUndoing organization...")

# Undo entire transaction
undo_manager = UndoManager()
success = undo_manager.undo_transaction(tx_id)

if success:
    print("✓ Organization undone - all files restored")
else:
    print("✗ Undo failed")
```

### Example 2: Selective Undo

```python
from file_organizer.history import HistoryTracker
from file_organizer.undo import UndoManager

tracker = HistoryTracker()
undo_manager = UndoManager()

# Get recent operations
operations = tracker.get_recent_operations(limit=10)

print("Recent operations:")
for i, op in enumerate(operations, 1):
    print(f"{i}. {op.operation_type.value}: {op.source_path.name}")
    if op.destination_path:
        print(f"   → {op.destination_path}")

# User selects which to undo
choice = int(input("\nUndo which operation? (number): "))
selected_op = operations[choice - 1]

# Check if can undo
can_undo, reason = undo_manager.can_undo(selected_op.id)

if can_undo:
    success = undo_manager.undo_operation(selected_op.id)
    if success:
        print("✓ Operation undone")
else:
    print(f"✗ Cannot undo: {reason}")
```

### Example 3: Redo After Review

```python
from file_organizer.undo import UndoManager

manager = UndoManager()

# Undo last operation
print("Undoing last operation...")
manager.undo_last_operation()

# Review redo stack
redo_stack = manager.get_redo_stack()

if redo_stack:
    op = redo_stack[0]
    print(f"\nCan redo: {op.operation_type.value}")
    print(f"File: {op.source_path.name}")

    response = input("Redo operation? (y/n): ")

    if response.lower() == 'y':
        success = manager.redo_last_operation()
        if success:
            print("✓ Operation redone")
```

## Smart Features Examples

### Example 1: Auto-Tag Document Library

```python
from pathlib import Path
from file_organizer.services.auto_tagging import AutoTaggingService

tagger = AutoTaggingService()

# Batch tag all documents
directory = Path("~/Documents")

for file_path in directory.rglob("*.pdf"):
    print(f"\nTagging: {file_path.name}")

    # Get tag suggestions
    suggestions = tagger.suggest_tags(
        file_path,
        top_n=5,
        min_confidence=60.0
    )

    if suggestions:
        tags = [tag for tag, confidence in suggestions]
        print(f"  Suggested tags: {', '.join(tags)}")

        # Apply tags
        tagger.apply_tags(file_path, tags, source="automatic")
        print("  ✓ Tags applied")

print("\n\nTag Statistics:")
stats = tagger.get_statistics()
print(f"Total files tagged: {stats['files_tagged']}")
print(f"Total tags: {stats['total_tags']}")
print(f"Avg tags per file: {stats['avg_tags_per_file']:.1f}")
```

### Example 2: Smart Suggestion Workflow

```python
from pathlib import Path
from file_organizer.services.smart_suggestions import SmartSuggestionEngine
from file_organizer.services.intelligence import PreferenceTracker

tracker = PreferenceTracker()
engine = SmartSuggestionEngine(preference_tracker=tracker)

# Load previous preferences
tracker.load_from_file("preferences.json")

# Process new files
new_files = list(Path("~/Downloads").glob("*"))

for file_path in new_files:
    if not file_path.is_file():
        continue

    # Get suggestions
    suggestions = engine.get_suggestions(file_path)

    print(f"\n{file_path.name}")
    print("─" * 50)

    # Show destination suggestions
    print("Destination suggestions:")
    for i, dest in enumerate(suggestions.destinations[:3], 1):
        print(f"  {i}. {dest.path} ({dest.confidence:.0%})")
        print(f"     {dest.reason}")

    # Show naming suggestions
    if suggestions.names:
        print("\nNaming suggestions:")
        for name in suggestions.names[:2]:
            print(f"  • {name.suggested_name} ({name.confidence:.0%})")

    # Show tag suggestions
    if suggestions.tags:
        tags = [tag.name for tag in suggestions.tags[:5]]
        print(f"\nSuggested tags: {', '.join(tags)}")
```

### Example 3: Content-Based Auto-Tagging

```python
from pathlib import Path
from file_organizer.services.auto_tagging import AutoTaggingService

tagger = AutoTaggingService()

file_path = Path("~/Documents/project_proposal.pdf")

print(f"Analyzing: {file_path.name}\n")

# Extract keywords
keywords = tagger.extract_keywords(file_path, max_keywords=15)
print("Keywords:")
for keyword, score in keywords[:10]:
    print(f"  {keyword}: {score:.2f}")

# Extract entities
entities = tagger.extract_entities(file_path)
print("\nNamed Entities:")
if entities['organizations']:
    print(f"  Organizations: {', '.join(entities['organizations'][:5])}")
if entities['people']:
    print(f"  People: {', '.join(entities['people'][:5])}")
if entities['locations']:
    print(f"  Locations: {', '.join(entities['locations'][:5])}")

# Identify topics
topics = tagger.identify_topics(file_path)
print("\nTopics:")
for topic, relevance in topics[:5]:
    print(f"  {topic}: {relevance:.0%}")

# Generate comprehensive tags
tags = tagger.suggest_tags(file_path, top_n=10)
print("\nRecommended tags:")
for tag, confidence in tags:
    print(f"  {tag} ({confidence:.0f}%)")
```

## Analytics Examples

### Example 1: Storage Audit

```python
from pathlib import Path
from file_organizer.services.analytics import AnalyticsService

analytics = AnalyticsService()

# Analyze multiple directories
directories = [
    Path("~/Documents"),
    Path("~/Downloads"),
    Path("~/Pictures"),
]

total_size = 0
total_files = 0

for directory in directories:
    stats = analytics.get_storage_stats(directory)

    print(f"\n{directory.name}:")
    print(f"  Size: {stats.formatted_total_size}")
    print(f"  Files: {stats.file_count}")
    print(f"  Directories: {stats.directory_count}")

    # Show top file types
    print("  Top file types:")
    sorted_types = sorted(
        stats.size_by_type.items(),
        key=lambda x: x[1],
        reverse=True
    )
    for file_type, size in sorted_types[:3]:
        pct = (size / stats.total_size) * 100
        print(f"    {file_type}: {format_size(size)} ({pct:.1f}%)")

    total_size += stats.total_size
    total_files += stats.file_count

print(f"\nTotal:")
print(f"  Size: {format_size(total_size)}")
print(f"  Files: {total_files}")
```

### Example 2: Quality Improvement Tracking

```python
from pathlib import Path
from file_organizer.services.analytics import AnalyticsService
from datetime import datetime
import json

analytics = AnalyticsService()
directory = Path("~/Documents")

# Get current quality
quality = analytics.get_quality_metrics(directory)

# Save snapshot
snapshot = {
    "date": datetime.now().isoformat(),
    "quality_score": quality.quality_score,
    "organization_score": quality.organization_score,
    "naming_score": quality.naming_score,
    "issues_count": len(quality.issues)
}

# Load previous snapshots
try:
    with open("quality_history.json") as f:
        history = json.load(f)
except FileNotFoundError:
    history = []

history.append(snapshot)

# Save history
with open("quality_history.json", "w") as f:
    json.dump(history, f, indent=2)

# Show improvement
if len(history) > 1:
    prev = history[-2]
    improvement = quality.quality_score - prev["quality_score"]
    print(f"Quality change: {improvement:+.1f} points")

# Show current issues
print(f"\nCurrent quality: {quality.quality_score:.1f}/100")
print(f"\nTop issues:")
for issue in quality.issues[:5]:
    print(f"  • {issue.title}")
    print(f"    {issue.description}")

# Show recommendations
print(f"\nRecommendations:")
for rec in quality.recommendations[:3]:
    print(f"  {rec.priority}: {rec.title}")
    print(f"    Impact: {rec.impact}")
    print(f"    Action: {rec.action}")
```

### Example 3: Generate Monthly Report

```bash
#!/bin/bash
# monthly_report.sh

YEAR=$(date +%Y)
MONTH=$(date +%m)
REPORT_DIR="~/Reports"
mkdir -p "$REPORT_DIR"

# Generate analytics report
python -m file_organizer.cli.analytics ~/Documents \
    --export "$REPORT_DIR/documents_${YEAR}_${MONTH}.html" \
    --trends --days 30

# Generate for other directories
for DIR in Downloads Pictures Music; do
    python -m file_organizer.cli.analytics ~/$DIR \
        --export "$REPORT_DIR/${DIR}_${YEAR}_${MONTH}.json"
done

echo "Reports saved to $REPORT_DIR"
```

## Integration Examples

### Example 1: Complete File Organization System

```python
from pathlib import Path
from file_organizer.core import FileOrganizer
from file_organizer.services.intelligence import PreferenceTracker
from file_organizer.services.deduplication import HashDeduplicator
from file_organizer.services.auto_tagging import AutoTaggingService
from file_organizer.services.analytics import AnalyticsService
from file_organizer.history import HistoryTracker, TransactionManager
from file_organizer.undo import UndoManager

class SmartFileOrganizer:
    def __init__(self):
        self.preference_tracker = PreferenceTracker()
        self.history_tracker = HistoryTracker()
        self.tx_manager = TransactionManager()
        self.organizer = FileOrganizer(
            preference_tracker=self.preference_tracker,
            history_tracker=self.history_tracker
        )
        self.deduper = HashDeduplicator()
        self.tagger = AutoTaggingService()
        self.analytics = AnalyticsService()
        self.undo_manager = UndoManager()

    def organize_smart(self, source: Path, destination: Path):
        """Organize with all smart features."""
        with self.tx_manager.transaction(f"Organize {source.name}") as tx_id:
            # 1. Analyze before
            print("Analyzing...")
            before_stats = self.analytics.get_storage_stats(source)

            # 2. Remove duplicates
            print("Finding duplicates...")
            duplicates = self.deduper.find_duplicates(source)
            dup_count = sum(len(files) - 1 for files in duplicates.values())
            print(f"Found {dup_count} duplicates")

            # 3. Organize files
            print("Organizing...")
            results = self.organizer.organize_directory(
                source=source,
                destination=destination,
                transaction_id=tx_id,
                learn_preferences=True
            )

            # 4. Auto-tag
            print("Tagging files...")
            for file_path in destination.rglob("*"):
                if file_path.is_file():
                    tags = self.tagger.suggest_tags(file_path, top_n=5)
                    if tags:
                        self.tagger.apply_tags(
                            file_path,
                            [tag for tag, _ in tags]
                        )

            # 5. Generate report
            print("\nResults:")
            print(f"  Files moved: {results.files_moved}")
            print(f"  Duplicates removed: {dup_count}")
            print(f"  Preferences learned: {len(self.preference_tracker.get_all_preferences())}")

            after_stats = self.analytics.get_storage_stats(destination)
            print(f"  Final size: {after_stats.formatted_total_size}")

            return tx_id

    def undo_last(self):
        """Undo last organization."""
        success = self.undo_manager.undo_last_operation()
        if success:
            print("✓ Undone")
        else:
            print("✗ Cannot undo")

# Usage
organizer = SmartFileOrganizer()
tx_id = organizer.organize_smart(
    Path("~/Downloads"),
    Path("~/Documents")
)

# If needed, undo
# organizer.undo_last()
```

See [API Reference](./api-reference.md) for complete API documentation.
