# Phase 4 Documentation

> Intelligence features for smart, adaptive file organization.

## Overview

Phase 4 introduces intelligent features that make File Organizer learn and adapt to your preferences:

- **Deduplication**: Remove duplicate files using hash, perceptual, and semantic detection
- **Intelligence**: Learn from your organization patterns and preferences
- **History & Undo**: Complete operation tracking with undo/redo support
- **Smart Features**: AI-powered suggestions and auto-tagging
- **Analytics**: Comprehensive insights into your file organization

## Quick Links

### User Guides

- **[Deduplication Guide](./deduplication.md)** - Hash-based, perceptual, and semantic duplicate detection
- **[Intelligence Guide](./intelligence.md)** - Preference tracking, pattern learning, and profile management
- **[History & Undo Guide](./undo-redo.md)** - Operation history tracking with undo/redo
- **[Smart Features Guide](./smart-features.md)** - Smart suggestions and auto-tagging
- **[Analytics Guide](./analytics.md)** - Storage analytics and quality metrics

### Reference Documentation

- **[API Reference](./api-reference.md)** - Complete API documentation for all Phase 4 features
- **[Usage Examples](./examples.md)** - Practical examples and real-world scenarios

## Features Overview

### Deduplication (#46, #47, #48)

Remove duplicate files with three powerful methods:

**Hash-Based** - Fast exact duplicate detection

```bash

python -m file_organizer.cli.dedupe ~/Downloads --strategy oldest

```

**Perceptual** - Find visually similar images

```python

from file_organizer.services.deduplication import ImageDeduplicator
deduper = ImageDeduplicator()
duplicates = deduper.find_duplicates(Path("~/Pictures"), similarity_threshold=0.90)

```

**Semantic** - Detect similar documents by meaning

```python

from file_organizer.services.deduplication import DocumentDeduplicator
deduper = DocumentDeduplicator()
similar = deduper.find_similar_documents(Path("~/Documents"), similarity_threshold=0.85)

```

### Intelligence (#49, #50, #51)

Learn from your organization patterns:

#### Preference Tracking

Learns from your corrections

```python

from file_organizer.services.intelligence import PreferenceTracker
tracker = PreferenceTracker()
tracker.add_correction(...)  # Tracks your organization decisions

```

#### Pattern Learning

Identifies your organization patterns

```python

from file_organizer.services.intelligence import PatternLearner
learner = PatternLearner()
patterns = learner.analyze_patterns(Path("~/Documents"))

```

#### Profile Management

Save and share preferences

```bash

python -m file_organizer.cli.profile export --output my-profile.json
python -m file_organizer.cli.profile import --input team-profile.json

```

### History & Undo (#53, #55)

Full operation history with undo/redo:

**Track Operations** - Every change is recorded

```python

from file_organizer.history import HistoryTracker
tracker = HistoryTracker()
operation = tracker.track_operation(...)

```

**Undo/Redo** - Reverse any operation

```bash

python -m file_organizer.cli.undo_redo --undo
python -m file_organizer.cli.undo_redo --redo

```

**Transactions** - Group operations together

```python

from file_organizer.history import TransactionManager
with tx_manager.transaction("Batch operation") as tx_id:
    # All operations tracked together
    pass

```

### Smart Features (#52, #54)

AI-powered intelligent assistance:

**Smart Suggestions** - Get intelligent organization recommendations

```python

from file_organizer.services.smart_suggestions import SmartSuggestionEngine
engine = SmartSuggestionEngine()
suggestions = engine.get_suggestions(file_path)

```

**Auto-Tagging** - Automatic content-based tagging

```bash

python -m file_organizer.cli.autotag suggest document.pdf
python -m file_organizer.cli.autotag apply document.pdf financial report

```

### Analytics (#56)

Comprehensive insights and metrics:

**Storage Analytics** - Understand your storage usage

```python

from file_organizer.services.analytics import AnalyticsService
analytics = AnalyticsService()
stats = analytics.get_storage_stats(Path("~/Documents"))

```

**Quality Metrics** - Measure organization quality

```python

quality = analytics.get_quality_metrics(Path("~/Documents"))
print(f"Quality score: {quality.quality_score}/100")

```

**Dashboard** - Visual analytics interface

```bash

python -m file_organizer.cli.analytics ~/Documents --export report.html

```

## Getting Started

### Installation

Phase 4 features are included with File Organizer v2:

```bash

cd file_organizer_v2
pip install -e .

```

### Quick Start

1. **Try Hash-Based Deduplication**

```bash

python -m file_organizer.cli.dedupe ~/Downloads --dry-run

```

2. **Enable Preference Learning**

```python

from file_organizer.services.intelligence import PreferenceTracker
tracker = PreferenceTracker()
# Use with FileOrganizer to learn from corrections

```

3. **View Analytics**

```bash

python -m file_organizer.cli.analytics ~/Documents

```

4. **Auto-Tag Files**

```bash

python -m file_organizer.cli.autotag suggest document.pdf

```

## CLI Commands Reference

### Deduplication

```bash

# Hash-based deduplication
python -m file_organizer.cli.dedupe <directory> [options]
  --strategy {manual,oldest,newest,largest,smallest}
  --algorithm {md5,sha256}
  --dry-run
  --batch

```

### Profile Management

```bash

# Profile commands
python -m file_organizer.cli.profile export <file>
python -m file_organizer.cli.profile import <file>
python -m file_organizer.cli.profile list
python -m file_organizer.cli.profile show <name>

```

### Undo/Redo

```bash

# History commands
python -m file_organizer.cli.undo_redo --list
python -m file_organizer.cli.undo_redo --undo [--operation-id ID]
python -m file_organizer.cli.undo_redo --redo [--operation-id ID]

```

### Auto-Tagging

```bash

# Tagging commands
python -m file_organizer.cli.autotag suggest <file>
python -m file_organizer.cli.autotag apply <file> <tags...>
python -m file_organizer.cli.autotag batch <directory>

```

### Analytics

```bash

# Analytics commands
python -m file_organizer.cli.analytics <directory>
python -m file_organizer.cli.analytics <directory> --export <file>
python -m file_organizer.cli.analytics <directory> --trends --days 90

```

## Architecture

Phase 4 follows a modular architecture:

```

phase4/
├── services/
│   ├── deduplication/      # Hash, perceptual, semantic dedup
│   ├── intelligence/       # Preference learning and profiles
│   ├── auto_tagging/       # Content-based tagging
│   └── analytics/          # Storage and quality analytics
├── history/                # Operation tracking
├── undo/                   # Undo/redo management
└── cli/                    # Command-line interfaces

```

## Performance Considerations

### Deduplication
- Hash-based: Fast, handles large datasets
- Perceptual: Slower, best for photo libraries
- Semantic: Requires AI model, best for document collections

### Intelligence
- Preference tracking: Real-time, minimal overhead
- Pattern learning: Periodic analysis recommended
- Profile operations: Fast, in-memory with disk persistence

### History
- SQLite database for storage
- Indexed for fast queries
- Regular cleanup recommended for large histories

### Analytics
- Caching enabled by default
- Incremental analysis available
- Parallel processing for large directories

## Troubleshooting

### Common Issues

**Deduplication is slow**
- Use MD5 instead of SHA256
- Add size filters
- Process directories separately

**Low confidence suggestions**
- Provide more training data
- Review learned preferences
- Check AI model availability

**Cannot undo operation**
- Verify file still exists
- Check permissions
- Review validation errors

**Analytics taking too long**
- Enable caching
- Exclude large directories
- Use sampling for very large datasets

See individual guides for detailed troubleshooting.

## Integration Examples

### Complete Workflow

```python

from pathlib import Path
from file_organizer.core import FileOrganizer
from file_organizer.services.intelligence import PreferenceTracker
from file_organizer.services.deduplication import HashDeduplicator
from file_organizer.services.auto_tagging import AutoTaggingService
from file_organizer.history import HistoryTracker, TransactionManager

# Initialize all services
preference_tracker = PreferenceTracker()
history_tracker = HistoryTracker()
tx_manager = TransactionManager()
deduper = HashDeduplicator()
tagger = AutoTaggingService()

organizer = FileOrganizer(
    preference_tracker=preference_tracker,
    history_tracker=history_tracker
)

# Organize with all features
with tx_manager.transaction("Smart organize") as tx_id:
    # 1. Remove duplicates
    duplicates = deduper.find_duplicates(Path("~/Downloads"))

    # 2. Organize files (learning preferences)
    results = organizer.organize_directory(
        source=Path("~/Downloads"),
        destination=Path("~/Documents"),
        transaction_id=tx_id
    )

    # 3. Auto-tag organized files
    for file_path in results.moved_files:
        tags = tagger.suggest_tags(file_path)
        if tags:
            tagger.apply_tags(file_path, [tag for tag, _ in tags[:5]])

```

## Best Practices

1. **Start with dry-run**: Always preview changes first
2. **Use transactions**: Group related operations
3. **Regular backups**: Export preferences and history
4. **Monitor quality**: Track organization quality over time
5. **Provide feedback**: Correct suggestions to improve learning
6. **Clean up history**: Periodically remove old history records
7. **Review analytics**: Use insights to improve organization

## Contributing

Phase 4 features are actively developed. See main [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.

## Support

- **Issues**: [GitHub Issues](https://github.com/QiuYannnn/Local-File-Organizer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/QiuYannnn/Local-File-Organizer/discussions)
- **Documentation**: This directory and [main README](../../README.md)

## License

Dual-licensed under MIT OR Apache-2.0.

## Related Documentation

- [Main README](../../README.md) - Project overview
- [Phase 1 Documentation](../../DEMO_COMPLETE.md) - Basic features
- [Phase 2 Documentation](../) - Enhanced UX
- [Phase 3 Documentation](../) - Feature expansion
