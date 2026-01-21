# Intelligence Services

This module provides intelligent learning capabilities that adapt to user behavior and preferences over time.

## Components

### PreferenceTracker

Core preference tracking engine that learns from user corrections and changes.

**Features:**
- Track file moves, renames, and category overrides
- In-memory preference management with metadata
- Thread-safe operations using locks
- Preference confidence and frequency tracking
- Real-time preference updates
- Export/import for persistence

**Usage Example:**

```python
from pathlib import Path
from file_organizer.services.intelligence import (
    PreferenceTracker,
    PreferenceType,
    track_file_move,
    track_category_change,
)

# Create tracker instance
tracker = PreferenceTracker()

# Track user correction - file move
source = Path("/home/user/Downloads/document.pdf")
destination = Path("/home/user/Documents/Work/document.pdf")
track_file_move(tracker, source, destination)

# Track multiple corrections to build confidence
source2 = Path("/home/user/Downloads/report.pdf")
destination2 = Path("/home/user/Documents/Work/report.pdf")
track_file_move(tracker, source2, destination2)

# Get preference for similar file
new_file = Path("/home/user/Downloads/proposal.pdf")
preference = tracker.get_preference(new_file, PreferenceType.FOLDER_MAPPING)

if preference:
    print(f"Suggested destination: {preference.value}")
    print(f"Confidence: {preference.metadata.confidence}")
    print(f"Based on {preference.metadata.frequency} corrections")

# Track category changes
file_path = Path("/home/user/Documents/report.docx")
track_category_change(tracker, file_path, "General", "Work")

# Get statistics
stats = tracker.get_statistics()
print(f"Total corrections tracked: {stats['total_corrections']}")
print(f"Average confidence: {stats['average_confidence']}")

# Export preferences for persistence
data = tracker.export_data()
# Save to JSON file...

# Later, import preferences
tracker.import_data(data)
```

## Preference Types

- **FOLDER_MAPPING**: Where files should be moved based on type/extension
- **NAMING_PATTERN**: How files should be renamed
- **CATEGORY_OVERRIDE**: Custom category assignments
- **FILE_EXTENSION**: Extension-based preferences
- **CUSTOM**: Custom preference types

## Correction Types

- **FILE_MOVE**: User moved a file to different location
- **FILE_RENAME**: User renamed a file
- **CATEGORY_CHANGE**: User changed file category
- **FOLDER_CREATION**: User created new folder structure
- **MANUAL_OVERRIDE**: User manually overrode system decision

## Thread Safety

All operations are thread-safe using a reentrant lock (RLock). Multiple threads can safely:
- Track corrections simultaneously
- Query preferences
- Update confidence scores
- Export/import data

## Confidence Scoring

Preferences start with 0.5 confidence and adjust based on:
- **Frequency**: More corrections increase confidence (up to 0.95)
- **Success**: Successful applications increase confidence (+0.05)
- **Failure**: Failed applications decrease confidence (-0.1)
- **Floor/Ceiling**: Confidence ranges from 0.1 to 0.98

## Performance

- Preference lookup: <10ms for typical cases
- Thread-safe operations with minimal lock contention
- In-memory storage for fast access
- Export/import for persistence

## Integration

The PreferenceTracker is designed to integrate with:
- FileOrganizer service (capture corrections)
- Pattern learning system (Task #49)
- Future ML models
- CLI commands for preference management
