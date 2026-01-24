# PARA Methodology API Reference

## Overview

The PARA API provides programmatic access to the PARA methodology implementation, including auto-categorization, custom rules, smart suggestions, and user preference learning.

## Table of Contents

- [Core Classes](#core-classes)
- [Configuration](#configuration)
- [Auto-Categorization](#auto-categorization)
- [Custom Rules](#custom-rules)
- [Smart Suggestions](#smart-suggestions)
- [User Preferences](#user-preferences)
- [Examples](#examples)

---

## Core Classes

### PARAConfig

Configuration object for PARA methodology.

```python
from file_organizer.methodologies.para import PARAConfig

config = PARAConfig(
    enabled: bool = True,
    auto_categorize: bool = True,
    confidence_threshold: float = 0.7,
    use_smart_suggestions: bool = True,
    auto_archive: bool = False,
    archive_after_days: int = 90,
    manual_review_threshold: float = 0.6,
    mixed_folder_strategy: str = "split"
)
```

**Parameters**:
- `enabled` - Enable PARA methodology
- `auto_categorize` - Automatically categorize files
- `confidence_threshold` - Minimum confidence for auto-categorization (0-1)
- `use_smart_suggestions` - Enable AI-powered suggestions
- `auto_archive` - Automatically archive inactive projects
- `archive_after_days` - Days before archiving inactive projects
- `manual_review_threshold` - Confidence below which manual review is flagged
- `mixed_folder_strategy` - How to handle mixed-content folders: "split", "dominant", "manual"

**Methods**:

```python
# Save configuration
config.save(path: str) -> None

# Load configuration
config = PARAConfig.load(path: str) -> PARAConfig

# Add custom rule
config.add_rule(rule: PARARule) -> None

# Remove rule
config.remove_rule(rule_name: str) -> None

# Validate configuration
config.validate() -> bool
```

### PARACategory

Enum representing PARA categories.

```python
from file_organizer.methodologies.para import PARACategory

class PARACategory(Enum):
    PROJECTS = "projects"
    AREAS = "areas"
    RESOURCES = "resources"
    ARCHIVE = "archive"
```

### PARAResult

Result from PARA categorization.

```python
@dataclass
class PARAResult:
    category: PARACategory
    confidence: float
    reasoning: str
    suggested_subfolder: Optional[str]
    alternative_categories: List[Tuple[PARACategory, float]]
```

**Attributes**:
- `category` - Assigned PARA category
- `confidence` - Confidence score (0-1)
- `reasoning` - Explanation of categorization
- `suggested_subfolder` - Recommended subfolder path
- `alternative_categories` - Other possible categories with scores

---

## Configuration

### Creating Configuration

**Basic Setup**:
```python
from file_organizer.methodologies.para import PARAConfig

# Minimal configuration
config = PARAConfig(
    enabled=True,
    auto_categorize=True
)

# Full configuration
config = PARAConfig(
    enabled=True,
    auto_categorize=True,
    confidence_threshold=0.7,
    use_smart_suggestions=True,
    auto_archive=True,
    archive_after_days=90,
    manual_review_threshold=0.6,
    mixed_folder_strategy="split"
)
```

**Loading from File**:
```python
# Load from YAML
config = PARAConfig.load("~/.config/file-organizer/para.json")

# Load from dict
config_dict = {
    "enabled": True,
    "auto_categorize": True,
    "confidence_threshold": 0.7
}
config = PARAConfig(**config_dict)
```

**Saving Configuration**:
```python
# Save to file
config.save("~/.config/file-organizer/para.json")

# Export to dict
config_dict = config.to_dict()
```

---

## Auto-Categorization

### PARACategorizer

Main class for automatic categorization.

```python
from file_organizer.methodologies.para import PARACategorizer

categorizer = PARACategorizer(config: PARAConfig)
```

**Methods**:

#### categorize()

```python
result = categorizer.categorize(
    file_path: Path,
    content: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> PARAResult
```

Categorize a file into PARA structure.

**Parameters**:
- `file_path` - Path to file
- `content` - Optional file content (extracted if not provided)
- `metadata` - Optional metadata dict

**Returns**: `PARAResult` with category and confidence

**Example**:
```python
from pathlib import Path

result = categorizer.categorize(Path("project-plan.pdf"))

print(f"Category: {result.category.value}")
print(f"Confidence: {result.confidence:.2%}")
print(f"Reasoning: {result.reasoning}")

# Output:
# Category: projects
# Confidence: 92.00%
# Reasoning: Contains deadline, goal-oriented language, temporary nature
```

#### batch_categorize()

```python
results = categorizer.batch_categorize(
    file_paths: List[Path],
    progress_callback: Optional[Callable] = None
) -> List[PARAResult]
```

Categorize multiple files in batch.

**Parameters**:
- `file_paths` - List of file paths
- `progress_callback` - Optional callback for progress updates

**Returns**: List of `PARAResult` objects

**Example**:
```python
from pathlib import Path

files = list(Path("~/Downloads").glob("*"))

def progress(current, total):
    print(f"Processing {current}/{total}")

results = categorizer.batch_categorize(files, progress_callback=progress)

for file, result in zip(files, results):
    print(f"{file.name} → {result.category.value}")
```

### Heuristics

Built-in heuristics for categorization.

#### TemporalHeuristic

Analyzes time-related indicators.

```python
from file_organizer.methodologies.para.detection import TemporalHeuristic

heuristic = TemporalHeuristic()
score = heuristic.evaluate(content, metadata)
```

**Detects**:
- Deadlines and dates
- Frequency indicators (daily, weekly, ongoing)
- Completion markers
- Time-bound language

#### ContentHeuristic

Examines file content for category indicators.

```python
from file_organizer.methodologies.para.detection import ContentHeuristic

heuristic = ContentHeuristic()
score = heuristic.evaluate(content, metadata)
```

**Detects**:
- Goal-oriented language (deliver, complete, finish)
- Maintenance language (maintain, monitor, track)
- Reference indicators (guide, tutorial, reference)
- Archive markers (old, completed, final)

#### StructuralHeuristic

Analyzes file organization and metadata.

```python
from file_organizer.methodologies.para.detection import StructuralHeuristic

heuristic = StructuralHeuristic()
score = heuristic.evaluate(content, metadata)
```

**Detects**:
- Folder structure hints
- Naming patterns
- Metadata tags
- File relationships

---

## Custom Rules

### PARARule

Define custom categorization rules.

```python
from file_organizer.methodologies.para import PARARule, PARACategory

rule = PARARule(
    name: str,
    category: PARACategory,
    conditions: Dict,
    priority: int = 5,
    enabled: bool = True
)
```

**Parameters**:
- `name` - Rule identifier
- `category` - Target PARA category
- `conditions` - Dictionary of conditions to match
- `priority` - Rule priority (1-10, higher = first)
- `enabled` - Whether rule is active

**Condition Keys**:
- `keywords` - List of keywords to match
- `file_extension` - List of extensions
- `path_contains` - Path substring match
- `metadata_contains` - Metadata field matches
- `min_size_mb` - Minimum file size
- `max_size_mb` - Maximum file size
- `created_after` - Date filter
- `created_before` - Date filter
- `recurring` - Boolean for recurring items

**Example**:
```python
# Work projects rule
work_rule = PARARule(
    name="Work Projects",
    category=PARACategory.PROJECTS,
    conditions={
        "keywords": ["client", "deliverable", "deadline"],
        "file_extension": [".docx", ".xlsx", ".pptx"],
        "path_contains": "/work/"
    },
    priority=10
)

config.add_rule(work_rule)

# Finance area rule
finance_rule = PARARule(
    name="Personal Finance",
    category=PARACategory.AREAS,
    conditions={
        "keywords": ["budget", "invoice", "receipt", "tax"],
        "recurring": True
    },
    priority=8
)

config.add_rule(finance_rule)
```

### RuleEngine

Manages and evaluates rules.

```python
from file_organizer.methodologies.para import RuleEngine

engine = RuleEngine(config: PARAConfig)
```

**Methods**:

```python
# Evaluate rules for a file
result = engine.evaluate_rules(
    file_path: Path,
    content: str,
    metadata: Dict
) -> Optional[PARAResult]

# Add rule
engine.add_rule(rule: PARARule)

# Remove rule
engine.remove_rule(rule_name: str)

# List all rules
rules = engine.list_rules() -> List[PARARule]

# Enable/disable rule
engine.set_rule_enabled(rule_name: str, enabled: bool)
```

**Example**:
```python
# Add custom rules
engine.add_rule(work_rule)
engine.add_rule(finance_rule)

# Evaluate
result = engine.evaluate_rules(
    Path("invoice.pdf"),
    content="Monthly invoice...",
    metadata={"tags": ["finance", "recurring"]}
)

if result:
    print(f"Rule matched: {result.category.value}")
```

---

## Smart Suggestions

### PARASuggestionEngine

AI-powered suggestion system.

```python
from file_organizer.methodologies.para import PARASuggestionEngine

engine = PARASuggestionEngine()
```

**Methods**:

#### suggest()

```python
suggestions = engine.suggest(
    file_path: Path,
    context: Optional[Dict] = None
) -> List[PARASuggestion]
```

Get categorization suggestions.

**Parameters**:
- `file_path` - File to analyze
- `context` - Optional context (recent activity, current focus)

**Returns**: List of `PARASuggestion` objects (sorted by confidence)

**Example**:
```python
suggestions = engine.suggest(
    Path("document.pdf"),
    context={
        "recent_activity": "project planning",
        "current_focus": ["Q2 goals", "team collaboration"]
    }
)

for suggestion in suggestions:
    print(f"{suggestion.category.value}: {suggestion.reasoning}")
    print(f"Confidence: {suggestion.confidence:.2%}")
```

#### accept_suggestion()

```python
engine.accept_suggestion(
    file_path: Path,
    category: PARACategory
) -> None
```

Record acceptance for learning.

**Example**:
```python
# Accept suggestion
engine.accept_suggestion(
    Path("document.pdf"),
    PARACategory.PROJECTS
)
```

#### reject_suggestion()

```python
engine.reject_suggestion(
    file_path: Path,
    suggested_category: PARACategory,
    correct_category: PARACategory,
    feedback: Optional[str] = None
) -> None
```

Record rejection with correction.

**Example**:
```python
# Reject and correct
engine.reject_suggestion(
    Path("document.pdf"),
    suggested_category=PARACategory.PROJECTS,
    correct_category=PARACategory.AREAS,
    feedback="This is ongoing maintenance, not a project"
)
```

---

## User Preferences

### PreferenceTracker

Tracks user preferences and patterns.

```python
from file_organizer.methodologies.para import PreferenceTracker

tracker = PreferenceTracker()
```

**Methods**:

```python
# Record user action
tracker.record_action(
    file_path: Path,
    chosen_category: PARACategory,
    alternative_category: Optional[PARACategory] = None
)

# Get category preference
preference = tracker.get_category_preference(
    file_pattern: str
) -> PARACategory

# Get confidence in preference
confidence = tracker.get_preference_confidence(
    file_pattern: str
) -> float

# Export preferences
preferences = tracker.export_preferences() -> Dict

# Import preferences
tracker.import_preferences(preferences: Dict)
```

**Example**:
```python
# Record user choices
tracker.record_action(
    Path("client-report.pdf"),
    chosen_category=PARACategory.PROJECTS
)

# Get learned preference
preference = tracker.get_category_preference("*-report.pdf")
confidence = tracker.get_preference_confidence("*-report.pdf")

print(f"Preference: {preference.value} ({confidence:.0%} confidence)")
```

---

## Examples

### Basic Usage

```python
from pathlib import Path
from file_organizer.methodologies.para import (
    PARAConfig,
    PARACategorizer
)

# Setup
config = PARAConfig(
    enabled=True,
    auto_categorize=True,
    confidence_threshold=0.7
)

categorizer = PARACategorizer(config)

# Categorize a file
file_path = Path("project-proposal.pdf")
result = categorizer.categorize(file_path)

print(f"Category: {result.category.value}")
print(f"Confidence: {result.confidence:.2%}")
print(f"Suggested path: {result.suggested_subfolder}")
```

### Custom Rules

```python
from file_organizer.methodologies.para import (
    PARAConfig,
    PARARule,
    PARACategory,
    PARACategorizer
)

# Create config with custom rules
config = PARAConfig()

# Add work rule
work_rule = PARARule(
    name="Work Projects",
    category=PARACategory.PROJECTS,
    conditions={
        "keywords": ["client", "deliverable"],
        "path_contains": "/work/"
    },
    priority=10
)
config.add_rule(work_rule)

# Add personal rule
personal_rule = PARARule(
    name="Personal Finance",
    category=PARACategory.AREAS,
    conditions={
        "keywords": ["budget", "invoice", "tax"],
        "recurring": True
    },
    priority=8
)
config.add_rule(personal_rule)

# Use with categorizer
categorizer = PARACategorizer(config)
result = categorizer.categorize(Path("invoice.pdf"))
```

### Batch Processing

```python
from pathlib import Path
from file_organizer.methodologies.para import PARACategorizer, PARAConfig

config = PARAConfig()
categorizer = PARACategorizer(config)

# Get all files
files = list(Path("~/Downloads").expanduser().glob("*"))

# Batch categorize
results = categorizer.batch_categorize(
    files,
    progress_callback=lambda current, total: print(f"{current}/{total}")
)

# Organize by category
from collections import defaultdict
by_category = defaultdict(list)

for file, result in zip(files, results):
    by_category[result.category].append(file.name)

# Print summary
for category, files in by_category.items():
    print(f"\n{category.value.upper()} ({len(files)} files):")
    for filename in files[:5]:  # Show first 5
        print(f"  - {filename}")
```

### Smart Suggestions

```python
from pathlib import Path
from file_organizer.methodologies.para import PARASuggestionEngine

engine = PARASuggestionEngine()

# Get suggestions with context
suggestions = engine.suggest(
    Path("new-document.pdf"),
    context={
        "recent_activity": "project planning",
        "current_focus": ["Q2 goals"]
    }
)

# Show all suggestions
for i, suggestion in enumerate(suggestions, 1):
    print(f"{i}. {suggestion.category.value} ({suggestion.confidence:.0%})")
    print(f"   Reasoning: {suggestion.reasoning}\n")

# Accept first suggestion
if suggestions:
    engine.accept_suggestion(
        Path("new-document.pdf"),
        suggestions[0].category
    )
```

### Learning from Feedback

```python
from file_organizer.methodologies.para import (
    PARASuggestionEngine,
    PARACategory
)

engine = PARASuggestionEngine()

# System suggests PROJECTS
suggestions = engine.suggest(Path("document.pdf"))
suggested = suggestions[0].category

# User corrects to AREAS
engine.reject_suggestion(
    Path("document.pdf"),
    suggested_category=PARACategory.PROJECTS,
    correct_category=PARACategory.AREAS,
    feedback="This is ongoing maintenance, not a project"
)

# Next time, system learns
new_suggestions = engine.suggest(Path("similar-document.pdf"))
# Now likely suggests AREAS first
```

---

## Exception Handling

```python
from file_organizer.methodologies.para.exceptions import (
    PARAConfigurationError,
    PARACategorizationError,
    PARAInvalidRuleError
)

try:
    result = categorizer.categorize(file_path)
except PARACategorizationError as e:
    print(f"Failed to categorize: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

---

## Related APIs

- [Johnny Decimal API](johnny-decimal-api.md) - Numbering system API
- [File Organization API](organization-api.md) - Core organization API

---

**API Version**: 2.0
**Last Updated**: 2026-01-24
