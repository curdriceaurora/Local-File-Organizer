# Phase 4 API Reference

> Complete API documentation for all Phase 4 features.

## Table of Contents

- [Deduplication](#deduplication)
- [Intelligence](#intelligence)
- [History & Undo/Redo](#history--undoredo)
- [Smart Features](#smart-features)
- [Analytics](#analytics)

## Deduplication

### HashDeduplicator

Hash-based duplicate detection.

```python
from file_organizer.services.deduplication import HashDeduplicator
```

#### `__init__(algorithm: str = "sha256")`

Initialize hash deduplicator.

**Parameters:**
- `algorithm` (str): Hash algorithm to use ("md5" or "sha256")

**Example:**
```python
deduper = HashDeduplicator(algorithm="sha256")
```

#### `find_duplicates(directory: Path, **kwargs) -> Dict[str, List[Path]]`

Find duplicate files by hash.

**Parameters:**
- `directory` (Path): Directory to scan
- `recursive` (bool): Scan subdirectories (default: True)
- `min_size` (int): Minimum file size in bytes (default: 0)
- `max_size` (Optional[int]): Maximum file size in bytes (default: None)
- `include_patterns` (List[str]): File patterns to include
- `exclude_patterns` (List[str]): File patterns to exclude

**Returns:**
- Dict mapping file hashes to list of duplicate file paths

**Example:**
```python
duplicates = deduper.find_duplicates(
    Path("~/Documents"),
    recursive=True,
    min_size=1024,
    include_patterns=["*.pdf", "*.docx"]
)
```

### ImageDeduplicator

Perceptual image duplicate detection.

```python
from file_organizer.services.deduplication import ImageDeduplicator
```

#### `__init__()`

Initialize image deduplicator.

#### `find_duplicates(directory: Path, **kwargs) -> List[List[ImageInfo]]`

Find visually similar images.

**Parameters:**
- `directory` (Path): Directory to scan
- `similarity_threshold` (float): Similarity threshold 0.0-1.0 (default: 0.90)
- `algorithm` (str): Hash algorithm ("dhash", "phash", "whash")
- `recursive` (bool): Scan subdirectories (default: True)

**Returns:**
- List of duplicate groups, each containing ImageInfo objects

**Example:**
```python
deduper = ImageDeduplicator()
duplicates = deduper.find_duplicates(
    Path("~/Pictures"),
    similarity_threshold=0.95,
    algorithm="phash"
)
```

### DocumentDeduplicator

Semantic document duplicate detection.

```python
from file_organizer.services.deduplication import DocumentDeduplicator
```

#### `__init__(model_name: str = "qwen2.5:3b", embedding_dim: int = 768)`

Initialize document deduplicator.

**Parameters:**
- `model_name` (str): AI model name for embeddings
- `embedding_dim` (int): Embedding dimension size

#### `find_similar_documents(directory: Path, **kwargs) -> List[List[DocumentInfo]]`

Find semantically similar documents.

**Parameters:**
- `directory` (Path): Directory to scan
- `similarity_threshold` (float): Similarity threshold 0.0-1.0 (default: 0.85)
- `recursive` (bool): Scan subdirectories (default: True)
- `file_extensions` (List[str]): File extensions to process

**Returns:**
- List of similar document groups

**Example:**
```python
deduper = DocumentDeduplicator()
similar = deduper.find_similar_documents(
    Path("~/Documents"),
    similarity_threshold=0.90,
    file_extensions=[".txt", ".md", ".pdf"]
)
```

## Intelligence

### PreferenceTracker

Track and learn from user corrections.

```python
from file_organizer.services.intelligence import PreferenceTracker
```

#### `__init__()`

Initialize preference tracker.

#### `add_correction(correction_type: CorrectionType, preference_type: PreferenceType, key: str, value: str, **kwargs)`

Add a correction to track.

**Parameters:**
- `correction_type` (CorrectionType): Type of correction
- `preference_type` (PreferenceType): Type of preference
- `key` (str): Preference key
- `value` (str): Preference value
- `context` (Dict): Additional context
- `metadata` (Dict): Additional metadata

**Example:**
```python
tracker = PreferenceTracker()
tracker.add_correction(
    correction_type=CorrectionType.FILE_MOVE,
    preference_type=PreferenceType.FOLDER_MAPPING,
    key="*.pdf",
    value="Documents/Work",
    context={"file_type": "document"}
)
```

#### `get_preference(key: str, preference_type: PreferenceType) -> Optional[Preference]`

Get a learned preference.

**Parameters:**
- `key` (str): Preference key to look up
- `preference_type` (PreferenceType): Type of preference

**Returns:**
- Preference object if found, None otherwise

**Example:**
```python
pref = tracker.get_preference("*.pdf", PreferenceType.FOLDER_MAPPING)
if pref:
    print(f"Suggestion: {pref.value} (confidence: {pref.metadata.confidence})")
```

#### `export_data() -> Dict[str, Any]`

Export all preferences.

**Returns:**
- Dictionary containing all preference data

#### `import_data(data: Dict[str, Any])`

Import preferences from data.

**Parameters:**
- `data` (Dict): Preference data to import

### PreferenceStore

Persistent preference storage.

```python
from file_organizer.services.intelligence import PreferenceStore
```

#### `__init__(storage_path: Optional[Path] = None)`

Initialize preference store.

**Parameters:**
- `storage_path` (Path): Custom storage location (default: ~/.file_organizer/preferences/)

#### `add_preference(path: Path, preference_data: Dict)`

Add preference for a directory.

**Parameters:**
- `path` (Path): Directory path
- `preference_data` (Dict): Preference data

**Example:**
```python
store = PreferenceStore()
store.add_preference(
    path=Path("~/Documents/Work"),
    preference_data={
        "folder_mappings": {"*.pdf": "PDFs"},
        "confidence": 0.85
    }
)
```

#### `get_preference(path: Path, fallback_to_parent: bool = True) -> Optional[Dict]`

Get preference for a path.

**Parameters:**
- `path` (Path): Directory path
- `fallback_to_parent` (bool): Use parent directory if not found

**Returns:**
- Preference dictionary or None

#### `save_preferences()`

Save preferences to disk.

#### `load_preferences()`

Load preferences from disk.

### ProfileManager

Manage preference profiles.

```python
from file_organizer.services.intelligence import ProfileManager
```

#### `create_profile(name: str, description: str = "") -> Profile`

Create a new profile.

**Parameters:**
- `name` (str): Profile name
- `description` (str): Profile description

**Returns:**
- Profile object

#### `save_profile(profile: Profile)`

Save profile to disk.

#### `load_profile(name: str) -> Profile`

Load profile from disk.

#### `list_profiles() -> List[str]`

List all available profiles.

## History & Undo/Redo

### HistoryTracker

Track file operations.

```python
from file_organizer.history import HistoryTracker
```

#### `__init__(db_path: Optional[Path] = None)`

Initialize history tracker.

**Parameters:**
- `db_path` (Path): Custom database path (default: ~/.file_organizer/history/operations.db)

#### `track_operation(operation_type: OperationType, source_path: Path, **kwargs) -> Operation`

Track a file operation.

**Parameters:**
- `operation_type` (OperationType): Type of operation
- `source_path` (Path): Source file path
- `destination_path` (Optional[Path]): Destination path
- `file_hash` (Optional[str]): File hash
- `metadata` (Dict): Additional metadata
- `transaction_id` (Optional[str]): Transaction ID

**Returns:**
- Operation object

**Example:**
```python
tracker = HistoryTracker()
operation = tracker.track_operation(
    operation_type=OperationType.MOVE,
    source_path=Path("~/Downloads/file.pdf"),
    destination_path=Path("~/Documents/file.pdf"),
    transaction_id="tx_123"
)
```

#### `get_recent_operations(limit: int = 10) -> List[Operation]`

Get recent operations.

**Parameters:**
- `limit` (int): Maximum number of operations

**Returns:**
- List of Operation objects

#### `get_operations_by_date_range(start: datetime, end: datetime) -> List[Operation]`

Get operations in date range.

**Parameters:**
- `start` (datetime): Start date
- `end` (datetime): End date

**Returns:**
- List of Operation objects

### OperationHistory

Manage operation transactions.

```python
from file_organizer.history import OperationHistory

history = OperationHistory()
```

#### `start_transaction(description: str = "") -> str`

Start a new transaction.

**Parameters:**
- `description` (str): Transaction description

**Returns:**
- Transaction ID

#### `commit_transaction(transaction_id: str) -> bool`

Commit a transaction.

**Parameters:**
- `transaction_id` (str): Transaction ID

**Returns:**
- True if successful

#### `rollback_transaction(transaction_id: str) -> bool`

Rollback a transaction.

**Parameters:**
- `transaction_id` (str): Transaction ID

**Returns:**
- True if successful

#### `transaction(description: str = "") -> ContextManager[str]`

Context manager for transactions.

**Parameters:**
- `description` (str): Transaction description

**Returns:**
- Context manager yielding transaction ID

**Example:**
```python
manager = TransactionManager()
with manager.transaction("Batch operation") as tx_id:
    # Perform operations
    tracker.track_operation(..., transaction_id=tx_id)
    # Automatically commits on success, rolls back on exception
```

### UndoManager

Undo and redo operations.

```python
from file_organizer.undo import UndoManager
```

#### `undo_last_operation() -> bool`

Undo the last operation.

**Returns:**
- True if successful

#### `undo_operation(operation_id: int) -> bool`

Undo specific operation.

**Parameters:**
- `operation_id` (int): Operation ID

**Returns:**
- True if successful

#### `undo_transaction(transaction_id: str) -> bool`

Undo all operations in a transaction.

**Parameters:**
- `transaction_id` (str): Transaction ID

**Returns:**
- True if successful

#### `redo_last_operation() -> bool`

Redo the last undone operation.

**Returns:**
- True if successful

#### `can_undo(operation_id: int) -> Tuple[bool, str]`

Check if operation can be undone.

**Parameters:**
- `operation_id` (int): Operation ID

**Returns:**
- Tuple of (can_undo, reason)

**Example:**
```python
manager = UndoManager()
can_undo, reason = manager.can_undo(42)
if can_undo:
    manager.undo_operation(42)
else:
    print(f"Cannot undo: {reason}")
```

## Smart Features

### SmartSuggestionEngine

AI-powered smart suggestions.

```python
from file_organizer.services.smart_suggestions import SmartSuggestionEngine
```

#### `__init__(**kwargs)`

Initialize suggestion engine.

**Parameters:**
- `preference_tracker` (Optional[PreferenceTracker]): Preference tracker to use
- `min_confidence` (float): Minimum confidence threshold (default: 0.6)

#### `get_suggestions(file_path: Path, **kwargs) -> Suggestions`

Get smart suggestions for a file.

**Parameters:**
- `file_path` (Path): File to analyze
- `min_confidence` (float): Minimum confidence threshold
- `max_suggestions` (int): Maximum number of suggestions

**Returns:**
- Suggestions object containing destinations, names, categories, and tags

**Example:**
```python
engine = SmartSuggestionEngine()
suggestions = engine.get_suggestions(
    Path("~/Downloads/report.pdf"),
    min_confidence=0.7,
    max_suggestions=5
)
```

#### `track_acceptance(file_path: Path, suggestion: Suggestion, accepted: bool)`

Track whether suggestion was accepted.

**Parameters:**
- `file_path` (Path): File path
- `suggestion` (Suggestion): Suggestion object
- `accepted` (bool): Whether suggestion was accepted

### AutoTaggingService

Automatic file tagging.

```python
from file_organizer.services.auto_tagging import AutoTaggingService
```

#### `__init__()`

Initialize auto-tagging service.

#### `suggest_tags(file_path: Path, **kwargs) -> List[Tuple[str, float]]`

Suggest tags for a file.

**Parameters:**
- `file_path` (Path): File to analyze
- `top_n` (int): Maximum number of tags (default: 10)
- `min_confidence` (float): Minimum confidence threshold (default: 50.0)

**Returns:**
- List of (tag, confidence) tuples

**Example:**
```python
tagger = AutoTaggingService()
tags = tagger.suggest_tags(
    Path("~/Documents/report.pdf"),
    top_n=10,
    min_confidence=60.0
)
```

#### `apply_tags(file_path: Path, tags: List[str], source: str = "user")`

Apply tags to a file.

**Parameters:**
- `file_path` (Path): File to tag
- `tags` (List[str]): Tags to apply
- `source` (str): Tag source ("user", "ai", "automatic")

#### `get_tags(file_path: Path) -> List[str]`

Get tags for a file.

**Parameters:**
- `file_path` (Path): File path

**Returns:**
- List of tags

#### `get_popular_tags(limit: int = 20) -> List[Tuple[str, int]]`

Get most popular tags.

**Parameters:**
- `limit` (int): Maximum number of tags

**Returns:**
- List of (tag, usage_count) tuples

## Analytics

### AnalyticsService

Comprehensive analytics and insights.

```python
from file_organizer.services.analytics import AnalyticsService
```

#### `__init__(**kwargs)`

Initialize analytics service.

**Parameters:**
- `cache_enabled` (bool): Enable caching (default: True)
- `workers` (int): Number of worker threads (default: 4)

#### `analyze_directory(directory: Path, **kwargs) -> AnalysisResults`

Analyze a directory.

**Parameters:**
- `directory` (Path): Directory to analyze
- `include_subdirs` (bool): Include subdirectories (default: True)
- `exclude_patterns` (List[str]): Patterns to exclude

**Returns:**
- AnalysisResults object

**Example:**
```python
analytics = AnalyticsService()
results = analytics.analyze_directory(
    Path("~/Documents"),
    include_subdirs=True
)
```

#### `get_storage_stats(directory: Path) -> StorageStats`

Get storage statistics.

**Parameters:**
- `directory` (Path): Directory to analyze

**Returns:**
- StorageStats object with size, file counts, etc.

#### `get_quality_metrics(directory: Path) -> QualityMetrics`

Get quality metrics.

**Parameters:**
- `directory` (Path): Directory to analyze

**Returns:**
- QualityMetrics object with quality scores

**Example:**
```python
quality = analytics.get_quality_metrics(Path("~/Documents"))
print(f"Quality score: {quality.quality_score}/100")
```

#### `analyze_patterns(directory: Path) -> PatternAnalysis`

Analyze organization patterns.

**Parameters:**
- `directory` (Path): Directory to analyze

**Returns:**
- PatternAnalysis object

#### `get_trends(directory: Path, start_date: datetime, end_date: datetime, **kwargs) -> TrendAnalysis`

Get trend analysis.

**Parameters:**
- `directory` (Path): Directory to analyze
- `start_date` (datetime): Start date
- `end_date` (datetime): End date
- `granularity` (str): Time granularity ("day", "week", "month")

**Returns:**
- TrendAnalysis object

## Data Models

### Operation

```python
@dataclass
class Operation:
    operation_type: OperationType
    timestamp: datetime
    source_path: Path
    destination_path: Optional[Path] = None
    file_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    transaction_id: Optional[str] = None
    status: OperationStatus = OperationStatus.COMPLETED
```

### Preference

```python
@dataclass
class Preference:
    key: str
    value: str
    preference_type: PreferenceType
    metadata: PreferenceMetadata
```

### Suggestions

```python
@dataclass
class Suggestions:
    destinations: List[DestinationSuggestion]
    names: List[NameSuggestion]
    categories: List[CategorySuggestion]
    tags: List[TagSuggestion]
```

### StorageStats

```python
@dataclass
class StorageStats:
    total_size: int
    file_count: int
    directory_count: int
    size_by_type: Dict[str, int]
    largest_files: List[FileInfo]
    formatted_total_size: str
```

### QualityMetrics

```python
@dataclass
class QualityMetrics:
    quality_score: float  # 0-100
    organization_score: float  # 0-1
    naming_score: float  # 0-1
    consistency_score: float  # 0-1
    completeness_score: float  # 0-1
    issues: List[QualityIssue]
    recommendations: List[Recommendation]
```

## Enums

### OperationType

```python
class OperationType(str, Enum):
    MOVE = "move"
    RENAME = "rename"
    DELETE = "delete"
    COPY = "copy"
    CREATE = "create"
```

### PreferenceType

```python
class PreferenceType(str, Enum):
    FOLDER_MAPPING = "folder_mapping"
    NAMING_PATTERN = "naming_pattern"
    CATEGORY_OVERRIDE = "category_override"
    FILE_EXTENSION = "file_extension"
    CUSTOM = "custom"
```

### CorrectionType

```python
class CorrectionType(str, Enum):
    FILE_MOVE = "file_move"
    FILE_RENAME = "file_rename"
    CATEGORY_CHANGE = "category_change"
    FOLDER_CREATION = "folder_creation"
    MANUAL_OVERRIDE = "manual_override"
```

## Utility Functions

### Helper Functions

```python
from file_organizer.services.intelligence import (
    track_file_move,
    track_category_change,
    track_rename
)

# Quick tracking helpers
track_file_move(tracker, source, destination)
track_category_change(tracker, file_path, old_cat, new_cat)
track_rename(tracker, old_path, new_path)
```

### Formatting Utilities

```python
from file_organizer.utils import format_size, format_datetime

# Format file size
size_str = format_size(1024000)  # "1.0 MB"

# Format datetime
date_str = format_datetime(timestamp)  # "2024-01-21 10:30:45"
```

## Error Handling

All APIs may raise the following exceptions:

- `FileNotFoundError`: File or directory not found
- `PermissionError`: Insufficient permissions
- `ValueError`: Invalid parameter value
- `OSError`: Operating system error
- `DatabaseError`: Database operation failed

**Example Error Handling:**
```python
try:
    duplicates = deduper.find_duplicates(directory)
except FileNotFoundError:
    print("Directory not found")
except PermissionError:
    print("Permission denied")
except Exception as e:
    print(f"Error: {e}")
```

## Related Documentation

- [Deduplication Guide](./deduplication.md)
- [Intelligence Guide](./intelligence.md)
- [History & Undo Guide](./undo-redo.md)
- [Smart Features Guide](./smart-features.md)
- [Analytics Guide](./analytics.md)
- [Usage Examples](./examples.md)
