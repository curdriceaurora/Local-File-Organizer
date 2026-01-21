# Smart Features Guide

> **Phase 4 Feature** - AI-powered smart suggestions (#52) and automatic tagging (#54) for intelligent file organization.

## Overview

Smart Features enhance your file organization workflow with:

1. **Smart Suggestions** (#52) - AI-powered organization recommendations
2. **Auto-Tagging** (#54) - Intelligent file tagging based on content

## Smart Suggestions

### How It Works

Smart Suggestions analyzes files and provides intelligent recommendations for:
- **Destination folders**: Where files should be moved
- **File names**: Better naming conventions
- **Categories**: Appropriate categorization
- **Tags**: Relevant tags based on content

The system combines:
- AI content analysis
- Learned user preferences
- Historical patterns
- Similarity with existing files

### Using Smart Suggestions

```python
from file_organizer.services.smart_suggestions import SmartSuggestionEngine
from pathlib import Path

# Initialize suggestion engine
engine = SmartSuggestionEngine()

# Get suggestions for a file
file_path = Path("~/Downloads/report.pdf")
suggestions = engine.get_suggestions(file_path)

# Review suggestions
print("Destination suggestions:")
for dest in suggestions.destinations:
    print(f"  {dest.path} (confidence: {dest.confidence:.0%})")
    print(f"  Reason: {dest.reason}")

print("\nNaming suggestions:")
for name in suggestions.names:
    print(f"  {name.suggested_name} (confidence: {name.confidence:.0%})")

print("\nCategory suggestions:")
for cat in suggestions.categories:
    print(f"  {cat.category} (confidence: {cat.confidence:.0%})")

print("\nTag suggestions:")
for tag in suggestions.tags:
    print(f"  {tag.name} (relevance: {tag.relevance:.0%})")
```

### Confidence Thresholds

```python
# Only show high-confidence suggestions
suggestions = engine.get_suggestions(
    file_path,
    min_confidence=0.7  # 70% confidence threshold
)

# Get more suggestions (lower threshold)
suggestions = engine.get_suggestions(
    file_path,
    min_confidence=0.5,
    max_suggestions=10
)
```

### Accepting Suggestions

```python
# User accepts a suggestion
accepted_suggestion = suggestions.destinations[0]

# Track acceptance for learning
engine.track_acceptance(
    file_path=file_path,
    suggestion=accepted_suggestion,
    accepted=True
)

# This improves future suggestions
```

### Suggestion Types

**Destination Suggestions**
Based on:
- File type and extension
- Content analysis
- Similar files in your library
- Learned folder mappings

```python
destinations = suggestions.destinations
# Returns list of (path, confidence, reason) tuples

# Example output:
# Path: ~/Documents/Work/Reports
# Confidence: 0.85
# Reason: "Similar PDF files are stored here (15 files)"
```

**Naming Suggestions**
Based on:
- Content analysis
- Existing naming patterns
- Date/time information
- File type conventions

```python
names = suggestions.names

# Example suggestions:
# - "Report_2024_Q1_Financial.pdf" (0.90)
# - "Financial_Report_Jan_2024.pdf" (0.82)
# - "Q1_2024_Report.pdf" (0.75)
```

**Category Suggestions**
Based on:
- AI content understanding
- Historical categorization
- File type
- Keywords and entities

```python
categories = suggestions.categories

# Example categories:
# - "Work" (0.88)
# - "Financial" (0.75)
# - "Reports" (0.70)
```

**Tag Suggestions**
Based on:
- Content keywords
- Named entities
- Topics detected
- Related file tags

```python
tags = suggestions.tags

# Example tags:
# - "financial" (0.95)
# - "quarterly" (0.88)
# - "2024" (0.85)
# - "pdf" (0.80)
```

## Auto-Tagging

### Overview

Auto-Tagging automatically generates and applies tags to files based on their content, making them easier to find and organize.

### Basic Usage

```bash
# Get tag suggestions for a file
python -m file_organizer.cli.autotag suggest document.pdf

# Apply suggested tags
python -m file_organizer.cli.autotag apply document.pdf financial quarterly report

# Batch tag entire directory
python -m file_organizer.cli.autotag batch ~/Documents --recursive
```

### Python API

```python
from file_organizer.services.auto_tagging import AutoTaggingService
from pathlib import Path

# Initialize service
tagger = AutoTaggingService()

# Suggest tags for a file
file_path = Path("~/Documents/report.pdf")
suggestions = tagger.suggest_tags(
    file_path,
    top_n=10,
    min_confidence=50.0
)

print("Suggested tags:")
for tag, confidence in suggestions:
    print(f"  {tag}: {confidence:.1f}%")

# Apply tags
tagger.apply_tags(
    file_path,
    tags=["financial", "quarterly", "report"],
    source="user"
)

# Get file tags
tags = tagger.get_tags(file_path)
print(f"File tags: {', '.join(tags)}")
```

### Tag Sources

Tags can come from multiple sources:

**Content Analysis**
```python
# Extract tags from file content
content_tags = tagger.analyze_content(file_path)

# Uses:
# - Keyword extraction
# - Named entity recognition
# - Topic modeling
# - Frequency analysis
```

**Similar Files**
```python
# Tags from similar files in library
similar_tags = tagger.get_similar_file_tags(file_path)

# Finds files with similar:
# - Content
# - Name patterns
# - Location
# - Type
```

**User History**
```python
# Tags based on user's tagging patterns
historical_tags = tagger.get_historical_tags(
    file_type=".pdf",
    category="Work"
)

# Learns from:
# - Previously applied tags
# - Tag frequencies
# - Tag co-occurrences
```

**AI Analysis**
```python
# AI-powered tag generation
ai_tags = tagger.generate_ai_tags(
    file_path,
    model="qwen2.5:3b"
)

# Generates tags based on:
# - Semantic understanding
# - Context awareness
# - Domain knowledge
```

### Tag Management

**View Popular Tags**
```bash
# Show most popular tags
python -m file_organizer.cli.autotag popular --limit 20
```

```python
# Get popular tags programmatically
popular = tagger.get_popular_tags(limit=20)

for tag, count in popular:
    print(f"{tag}: used {count} times")
```

**View Recent Tags**
```bash
# Show recently used tags
python -m file_organizer.cli.autotag recent --days 30
```

```python
# Get recent tags
from datetime import datetime, timedelta

recent = tagger.get_recent_tags(
    since=datetime.now() - timedelta(days=30),
    limit=20
)
```

**Tag Statistics**
```python
# Get tag statistics
stats = tagger.get_statistics()

print(f"Total tags: {stats['total_tags']}")
print(f"Total files tagged: {stats['files_tagged']}")
print(f"Average tags per file: {stats['avg_tags_per_file']:.1f}")
print(f"Most used tag: {stats['most_used_tag']}")
```

### Advanced Features

**Keyword Extraction**
```python
# Extract keywords from file
keywords = tagger.extract_keywords(
    file_path,
    max_keywords=20,
    min_score=0.3
)

for keyword, score in keywords:
    print(f"{keyword}: {score:.2f}")
```

**Entity Extraction**
```python
# Extract named entities
entities = tagger.extract_entities(file_path)

print("Organizations:", entities['organizations'])
print("People:", entities['people'])
print("Locations:", entities['locations'])
print("Dates:", entities['dates'])
```

**Topic Modeling**
```python
# Identify document topics
topics = tagger.identify_topics(file_path)

for topic, relevance in topics:
    print(f"{topic}: {relevance:.0%} relevant")
```

**Tag Relationships**
```python
# Find related tags
related = tagger.get_related_tags("financial")

# Returns tags frequently used together:
# - "quarterly" (0.85 correlation)
# - "report" (0.80 correlation)
# - "budget" (0.75 correlation)
```

### Batch Operations

**Batch Tagging**
```bash
# Tag entire directory
python -m file_organizer.cli.autotag batch ~/Documents \
    --recursive \
    --min-confidence 60 \
    --pattern "*.pdf"
```

```python
# Batch tag programmatically
results = tagger.batch_tag_directory(
    directory=Path("~/Documents"),
    recursive=True,
    file_pattern="*.pdf",
    min_confidence=60.0,
    auto_apply=False  # Suggest only, don't auto-apply
)

print(f"Processed {results.files_processed} files")
print(f"Suggested {results.total_suggestions} tags")
```

**Tag Cleanup**
```python
# Remove unused tags
removed = tagger.cleanup_unused_tags(days=90)
print(f"Removed {removed} unused tags")

# Merge similar tags
merged = tagger.merge_similar_tags(
    similarity_threshold=0.9
)
print(f"Merged {merged} tag pairs")

# Normalize tag names
normalized = tagger.normalize_tags()
# Fixes: capitalization, plurals, synonyms
```

### Learning from Feedback

**Track Tag Usage**
```python
# System learns which tags are useful
tagger.track_tag_usage(
    file_path=file_path,
    tag="financial",
    action="applied"  # or "removed", "modified"
)

# This improves future suggestions
```

**Import/Export Tags**
```bash
# Export tags
python -m file_organizer.cli.autotag export tags.json

# Import tags
python -m file_organizer.cli.autotag import tags.json --merge
```

```python
# Export programmatically
tag_data = tagger.export_tags()

with open("tags.json", "w") as f:
    json.dump(tag_data, f, indent=2)

# Import
with open("tags.json") as f:
    tag_data = json.load(f)
tagger.import_tags(tag_data, merge=True)
```

## Integration Examples

### With File Organization

```python
from file_organizer.core import FileOrganizer
from file_organizer.services.smart_suggestions import SmartSuggestionEngine
from file_organizer.services.auto_tagging import AutoTaggingService

# Initialize services
organizer = FileOrganizer()
suggestions = SmartSuggestionEngine()
tagger = AutoTaggingService()

# Organize with smart suggestions
file_path = Path("~/Downloads/document.pdf")

# Get suggestions
dest_suggestions = suggestions.get_suggestions(file_path)

# Apply best suggestion
best_dest = dest_suggestions.destinations[0]
organizer.move_file(file_path, best_dest.path)

# Auto-tag the file
tag_suggestions = tagger.suggest_tags(file_path)
tagger.apply_tags(file_path, [tag for tag, _ in tag_suggestions[:5]])
```

### With Intelligence System

```python
from file_organizer.services.intelligence import PreferenceTracker

# Smart suggestions use learned preferences
tracker = PreferenceTracker()
engine = SmartSuggestionEngine(preference_tracker=tracker)

# Suggestions improve over time
suggestions = engine.get_suggestions(file_path)

# User accepts suggestion
engine.track_acceptance(file_path, suggestions.destinations[0], True)

# Next time, similar files get better suggestions
```

### With Search

```python
# Find files by tags
tagged_files = tagger.search_by_tags(
    tags=["financial", "quarterly"],
    operator="AND"  # or "OR"
)

print(f"Found {len(tagged_files)} files")

# Find files by tag pattern
reports = tagger.search_by_tag_pattern("*report*")
```

## CLI Reference

### Smart Suggestions (Future)
```bash
# Get suggestions for a file
file-organizer suggest ~/Downloads/file.pdf

# Apply suggestion
file-organizer apply-suggestion --id 42

# Batch suggestions
file-organizer suggest-batch ~/Downloads
```

### Auto-Tagging

```bash
# Suggest tags
python -m file_organizer.cli.autotag suggest document.pdf \
    --top-n 10 \
    --min-confidence 50

# Apply tags
python -m file_organizer.cli.autotag apply document.pdf financial report

# Popular tags
python -m file_organizer.cli.autotag popular --limit 20

# Recent tags
python -m file_organizer.cli.autotag recent --days 30

# Analyze content
python -m file_organizer.cli.autotag analyze document.pdf \
    --keywords \
    --entities

# Batch tagging
python -m file_organizer.cli.autotag batch ~/Documents \
    --recursive \
    --pattern "*.pdf" \
    --min-confidence 60
```

## Best Practices

### 1. Set Appropriate Confidence Thresholds

```python
# High stakes: use high threshold
suggestions = engine.get_suggestions(
    file_path,
    min_confidence=0.8  # 80% confidence
)

# Exploration: use lower threshold
suggestions = engine.get_suggestions(
    file_path,
    min_confidence=0.5  # Show more options
)
```

### 2. Provide Feedback

```python
# Always track accepted/rejected suggestions
engine.track_acceptance(file_path, suggestion, accepted=True)

# This improves the system
```

### 3. Regular Tag Cleanup

```bash
# Monthly cleanup
python -m file_organizer.cli.autotag cleanup --days 90
```

### 4. Use Batch Operations for Large Libraries

```bash
# Initial tagging of existing library
python -m file_organizer.cli.autotag batch ~/Documents \
    --recursive \
    --min-confidence 70 \
    --auto-apply
```

### 5. Combine with Intelligence System

```python
# Let suggestions learn from preferences
engine = SmartSuggestionEngine(
    preference_tracker=tracker,
    learn_from_feedback=True
)
```

## Troubleshooting

### Low-Quality Suggestions

**Problem**: Suggestions are not relevant

**Solutions**:
- Increase confidence threshold
- Provide more feedback
- Check file content quality
- Verify AI model is running

```python
# Debug suggestions
debug_info = engine.get_suggestion_debug_info(file_path)
print(f"Factors considered: {debug_info.factors}")
print(f"Confidence sources: {debug_info.sources}")
```

### Tags Not Appearing

**Problem**: Auto-tagging doesn't generate tags

**Solutions**:
- Check file is readable
- Verify content isn't empty
- Lower confidence threshold
- Check AI model availability

```bash
# Test with verbose output
python -m file_organizer.cli.autotag suggest file.pdf --verbose
```

### Poor Tag Quality

**Problem**: Generated tags are generic or irrelevant

**Solutions**:
- Use content-based tagging (not just filename)
- Increase minimum confidence
- Provide manual feedback
- Review and merge similar tags

```python
# Focus on content analysis
tags = tagger.suggest_tags(
    file_path,
    use_content=True,
    use_filename=False,
    min_confidence=60.0
)
```

## Performance Tips

### 1. Cache Suggestions

```python
# Cache expensive suggestions
engine = SmartSuggestionEngine(
    cache_suggestions=True,
    cache_ttl=3600  # 1 hour
)
```

### 2. Batch Processing

```python
# Process multiple files efficiently
files = [Path(f) for f in file_list]
results = tagger.batch_suggest_tags(files)
```

### 3. Async Operations

```python
# Use async for better performance
async def process_files(files):
    tasks = [tagger.suggest_tags_async(f) for f in files]
    results = await asyncio.gather(*tasks)
    return results
```

## API Reference

### SmartSuggestionEngine

```python
class SmartSuggestionEngine:
    def get_suggestions(
        self,
        file_path: Path,
        min_confidence: float = 0.6,
        max_suggestions: int = 5,
    ) -> Suggestions:
        """Get smart suggestions for a file."""

    def track_acceptance(
        self,
        file_path: Path,
        suggestion: Suggestion,
        accepted: bool,
    ):
        """Track whether suggestion was accepted."""
```

### AutoTaggingService

```python
class AutoTaggingService:
    def suggest_tags(
        self,
        file_path: Path,
        top_n: int = 10,
        min_confidence: float = 50.0,
    ) -> List[Tuple[str, float]]:
        """Suggest tags for a file."""

    def apply_tags(
        self,
        file_path: Path,
        tags: List[str],
        source: str = "user",
    ):
        """Apply tags to a file."""

    def get_tags(self, file_path: Path) -> List[str]:
        """Get tags for a file."""
```

## Related Documentation

- [Intelligence Guide](./intelligence.md) - Preference learning
- [Analytics Guide](./analytics.md) - Tag statistics
- [API Reference](./api-reference.md) - Complete API docs
