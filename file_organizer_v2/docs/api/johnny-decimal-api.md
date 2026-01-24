# Johnny Decimal System API Reference

## Overview

The Johnny Decimal API provides programmatic access to the Johnny Decimal numbering system, including automatic number assignment, conflict resolution, custom schemes, and validation.

## Table of Contents

- [Core Classes](#core-classes)
- [Configuration](#configuration)
- [Number Generation](#number-generation)
- [Numbering Schemes](#numbering-schemes)
- [Conflict Resolution](#conflict-resolution)
- [Validation](#validation)
- [Examples](#examples)

---

## Core Classes

### JohnnyDecimalConfig

Configuration for Johnny Decimal system.

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalConfig

config = JohnnyDecimalConfig(
    enabled: bool = True,
    auto_assign: bool = True,
    auto_increment: bool = True,
    skip_full_categories: bool = True,
    enforce_strict_ranges: bool = True,
    allow_category_99: bool = False,
    default_conflict_strategy: str = "increment",
    max_retries: int = 10,
    start_from: str = "01",
    reserve_ranges: List[str] = [],
    include_number_in_name: bool = True,
    separator: str = " - ",
    scheme: str = "business"
)
```

**Parameters**:
- `enabled` - Enable Johnny Decimal system
- `auto_assign` - Automatically assign numbers
- `auto_increment` - Auto-increment on conflicts
- `skip_full_categories` - Skip categories with 99 items
- `enforce_strict_ranges` - Enforce area/category ranges
- `allow_category_99` - Allow use of category 99 (typically reserved)
- `default_conflict_strategy` - "increment", "skip", or "manual"
- `max_retries` - Maximum attempts to find available number
- `start_from` - Starting ID ("00" or "01")
- `reserve_ranges` - List of reserved number ranges
- `include_number_in_name` - Add number to filename
- `separator` - Separator between number and name
- `scheme` - Pre-defined scheme name

### JohnnyDecimalNumber

Represents a Johnny Decimal number (XX.YY format).

```python
@dataclass
class JohnnyDecimalNumber:
    category: int  # 00-99
    id: int  # 00-99
    area: Optional[int] = None  # Computed from category

    @property
    def full_number(self) -> str:
        """Returns formatted number (e.g., '11.04')"""

    @property
    def is_valid(self) -> bool:
        """Validates number format"""
```

**Example**:
```python
number = JohnnyDecimalNumber(category=11, id=4)
print(number.full_number)  # "11.04"
print(number.area)  # 1 (derived from category 11)
```

### AssignmentResult

Result from number assignment.

```python
@dataclass
class AssignmentResult:
    number: JohnnyDecimalNumber
    category: CategoryDefinition
    suggested_path: str
    confidence: float
    needs_manual_review: bool
    suggested_alternatives: List[JohnnyDecimalNumber]
```

**Attributes**:
- `number` - Assigned number
- `category` - Category definition
- `suggested_path` - Full file path with number
- `confidence` - Assignment confidence (0-1)
- `needs_manual_review` - Whether manual review needed
- `suggested_alternatives` - Other possible numbers

---

## Configuration

### Creating Configuration

**Basic Setup**:
```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalConfig

# Minimal config
config = JohnnyDecimalConfig(
    enabled=True,
    auto_assign=True
)

# Full config
config = JohnnyDecimalConfig(
    enabled=True,
    auto_assign=True,
    auto_increment=True,
    skip_full_categories=True,
    default_conflict_strategy="increment",
    include_number_in_name=True,
    separator=" - ",
    scheme="business"
)
```

**Using Pre-defined Schemes**:
```python
# Business scheme
config = JohnnyDecimalConfig(scheme="business")

# Personal scheme
config = JohnnyDecimalConfig(scheme="personal")

# Research scheme
config = JohnnyDecimalConfig(scheme="research")

# Creative scheme
config = JohnnyDecimalConfig(scheme="creative")
```

**Saving/Loading**:
```python
# Save configuration
config.save("~/.config/file-organizer/jd-config.json")

# Load configuration
config = JohnnyDecimalConfig.load("~/.config/file-organizer/jd-config.json")
```

---

## Number Generation

### JohnnyDecimalGenerator

Main class for generating numbers.

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalGenerator

generator = JohnnyDecimalGenerator(
    config: Optional[JohnnyDecimalConfig] = None,
    scheme: Optional[NumberingScheme] = None
)
```

**Methods**:

#### assign_number()

```python
result = generator.assign_number(
    file_path: Path,
    content_hint: Optional[str] = None,
    suggested_area: Optional[int] = None,
    preferred_category: Optional[int] = None,
    preferred_number: Optional[str] = None,
    conflict_resolution: Optional[str] = None,
    respect_existing: bool = True
) -> AssignmentResult
```

Assign a Johnny Decimal number to a file.

**Parameters**:
- `file_path` - File to number
- `content_hint` - Hint about file content
- `suggested_area` - Preferred area (10-19, 20-29, etc.)
- `preferred_category` - Preferred category (00-99)
- `preferred_number` - Exact number if known
- `conflict_resolution` - Override default strategy
- `respect_existing` - Don't reassign existing numbers

**Returns**: `AssignmentResult` with assigned number

**Example**:
```python
from pathlib import Path

# Auto-assign based on content
result = generator.assign_number(
    file_path=Path("invoice-2024.pdf"),
    content_hint="accounting invoice"
)

print(f"Assigned: {result.number.full_number}")
print(f"Category: {result.category.name}")
print(f"Path: {result.suggested_path}")

# Output:
# Assigned: 21.05
# Category: 21 Accounting
# Path: 20-29-Finance/21-Accounting/21.05-invoice-2024.pdf
```

#### next_available()

```python
number = generator.next_available(
    category: int
) -> JohnnyDecimalNumber
```

Get next available number in category.

**Example**:
```python
# Get next number in category 11
number = generator.next_available(category=11)
print(f"Next: {number.full_number}")  # e.g., "11.05"
```

#### is_number_available()

```python
available = generator.is_number_available(
    number: str
) -> bool
```

Check if number is available.

**Example**:
```python
if generator.is_number_available("11.04"):
    print("Number is free to use")
else:
    print("Number already assigned")
```

#### batch_assign()

```python
results = generator.batch_assign(
    file_paths: List[Path],
    progress_callback: Optional[Callable] = None
) -> List[AssignmentResult]
```

Assign numbers to multiple files.

**Example**:
```python
files = list(Path("~/Documents").glob("*.pdf"))

def progress(current, total):
    print(f"Processing {current}/{total}")

results = generator.batch_assign(files, progress_callback=progress)

for file, result in zip(files, results):
    print(f"{file.name} → {result.number.full_number}")
```

---

## Numbering Schemes

### NumberingScheme

Defines the structure of areas and categories.

```python
from file_organizer.methodologies.johnny_decimal import NumberingScheme

scheme = NumberingScheme(
    name: str,
    description: Optional[str] = None
)
```

**Methods**:

```python
# Add area
scheme.add_area(area: AreaDefinition)

# Add category
scheme.add_category(category: CategoryDefinition)

# Get area
area = scheme.get_area(area_number: int) -> AreaDefinition

# Get category
category = scheme.get_category(category_number: int) -> CategoryDefinition

# List all areas
areas = scheme.list_areas() -> List[AreaDefinition]

# List all categories
categories = scheme.list_categories() -> List[CategoryDefinition]

# Export scheme
scheme_dict = scheme.export() -> Dict

# Import scheme
scheme = NumberingScheme.import_from(scheme_dict: Dict)
```

### AreaDefinition

Defines an area (10-19, 20-29, etc.).

```python
from file_organizer.methodologies.johnny_decimal import AreaDefinition

area = AreaDefinition(
    area_range: Tuple[int, int],
    name: str,
    description: Optional[str] = None,
    keywords: List[str] = []
)
```

**Example**:
```python
# Define Administration area
admin_area = AreaDefinition(
    area_range=(10, 19),
    name="Administration",
    description="Company administration and operations",
    keywords=["admin", "company", "operations"]
)

scheme.add_area(admin_area)
```

### CategoryDefinition

Defines a category within an area.

```python
from file_organizer.methodologies.johnny_decimal import CategoryDefinition

category = CategoryDefinition(
    category_number: int,
    name: str,
    description: Optional[str] = None,
    keywords: List[str] = [],
    parent_area: AreaDefinition = None
)
```

**Example**:
```python
# Define Company Documents category
company_docs = CategoryDefinition(
    category_number=11,
    name="Company documents",
    description="Registration, licenses, insurance",
    keywords=["registration", "license", "insurance"],
    parent_area=admin_area
)

scheme.add_category(company_docs)
```

### Pre-defined Schemes

```python
from file_organizer.methodologies.johnny_decimal import get_default_scheme

# Business scheme
business = get_default_scheme("business")
# Areas: 10-19 Administration, 20-29 Finance, 30-39 Projects,
#        40-49 Marketing, 50-59 Operations, 60-69 HR,
#        70-79 IT, 80-89 Legal, 90-99 Archive

# Personal scheme
personal = get_default_scheme("personal")
# Areas: 10-19 Personal Admin, 20-29 Home, 30-39 Work,
#        40-49 Hobbies, 50-59 Health, 60-69 Travel,
#        70-79 Learning, 80-89 Social, 90-99 Archive

# Research scheme
research = get_default_scheme("research")
# Areas: 10-19 Literature, 20-29 Data, 30-39 Writing,
#        40-49 Presentations, 50-59 Experiments, 60-69 Collaborations,
#        70-79 Administration, 80-89 Teaching, 90-99 Archive

# Creative scheme
creative = get_default_scheme("creative")
# Areas: 10-19 Inspiration, 20-29 Projects, 30-39 Assets,
#        40-49 Portfolio, 50-59 Client Work, 60-69 Learning,
#        70-79 Business, 80-89 Marketing, 90-99 Archive
```

### Creating Custom Schemes

```python
from file_organizer.methodologies.johnny_decimal import (
    NumberingScheme,
    AreaDefinition,
    CategoryDefinition
)

# Create scheme
scheme = NumberingScheme(name="My Custom Scheme")

# Define areas
admin_area = AreaDefinition(
    area_range=(10, 19),
    name="Administration"
)

finance_area = AreaDefinition(
    area_range=(20, 29),
    name="Finance"
)

# Define categories
company_docs = CategoryDefinition(
    category_number=11,
    name="Company documents",
    keywords=["registration", "license"],
    parent_area=admin_area
)

contracts = CategoryDefinition(
    category_number=12,
    name="Contracts",
    keywords=["contract", "agreement"],
    parent_area=admin_area
)

accounting = CategoryDefinition(
    category_number=21,
    name="Accounting",
    keywords=["invoice", "receipt", "ledger"],
    parent_area=finance_area
)

# Add to scheme
scheme.add_area(admin_area)
scheme.add_area(finance_area)
scheme.add_category(company_docs)
scheme.add_category(contracts)
scheme.add_category(accounting)

# Use scheme
generator = JohnnyDecimalGenerator(scheme=scheme)
```

---

## Conflict Resolution

### Detecting Conflicts

```python
# Check single number
if not generator.is_number_available("11.04"):
    conflicts = generator.find_conflicts("11.04")
    for conflict in conflicts:
        print(f"Conflict: {conflict.file_path}")
```

### Resolution Strategies

#### Increment Strategy

Auto-increment to next available number.

```python
result = generator.assign_number(
    file_path,
    preferred_category=11,
    conflict_resolution="increment"
)
# If 11.04 is taken, tries 11.05, 11.06, etc.
```

#### Skip Strategy

Skip to next category if current is full.

```python
result = generator.assign_number(
    file_path,
    preferred_category=11,
    conflict_resolution="skip"
)
# If category 11 is full (99 items), moves to category 12
```

#### Manual Strategy

Flag for user review.

```python
result = generator.assign_number(
    file_path,
    preferred_category=11,
    conflict_resolution="manual"
)

if result.needs_manual_review:
    print("Manual review required")
    print(f"Alternatives: {result.suggested_alternatives}")
```

### ConflictResolver

Advanced conflict resolution.

```python
from file_organizer.methodologies.johnny_decimal import ConflictResolver

resolver = ConflictResolver(generator)
```

**Methods**:

```python
# Find all conflicts in directory
conflicts = resolver.find_all_conflicts(
    directory: Path
) -> List[ConflictInfo]

# Resolve conflicts automatically
resolved = resolver.resolve_conflicts(
    conflicts: List[ConflictInfo],
    strategy: str = "increment"
) -> List[AssignmentResult]

# Get conflict report
report = resolver.generate_conflict_report(
    directory: Path
) -> str
```

---

## Validation

### Validate Number Format

```python
from file_organizer.methodologies.johnny_decimal import validate_number

# Valid numbers
validate_number("11.04")  # True
validate_number("11.99")  # True
validate_number("00.01")  # True

# Invalid numbers
validate_number("11.100")  # False - ID must be 00-99
validate_number("100.01")  # False - Category must be 00-99
validate_number("11")      # False - Missing ID
validate_number("11.4")    # False - ID must be two digits
```

### Validate Ranges

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalSystem

system = JohnnyDecimalSystem(scheme)

# Check if number fits in category's range
category = scheme.get_category(11)
if category.is_in_range("11.04"):
    print("Number is valid for this category")

# Check area ranges
area = scheme.get_area_for_category(11)
if area.contains_category(11):
    print("Category is in correct area")
```

### ValidationResult

```python
@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    suggestions: List[str]
```

**Example**:
```python
from file_organizer.methodologies.johnny_decimal import Validator

validator = Validator(scheme)
result = validator.validate_number("11.04")

if not result.is_valid:
    for error in result.errors:
        print(f"Error: {error}")
    for suggestion in result.suggestions:
        print(f"Suggestion: {suggestion}")
```

---

## System Management

### JohnnyDecimalSystem

High-level system management.

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalSystem

system = JohnnyDecimalSystem(
    scheme: Optional[NumberingScheme] = None,
    config: Optional[JohnnyDecimalConfig] = None
)
```

**Methods**:

#### initialize()

```python
system.initialize(
    root_directory: Path
) -> None
```

Initialize Johnny Decimal structure in directory.

**Example**:
```python
system.initialize(Path("~/Documents"))
# Creates:
# 10-19-Administration/
# 20-29-Finance/
# 30-39-Projects/
# etc.
```

#### get_usage_stats()

```python
stats = system.get_usage_stats() -> UsageStats
```

Get usage statistics.

```python
@dataclass
class UsageStats:
    total_items: int
    areas_in_use: int
    categories_in_use: int
    average_items_per_category: float
    full_categories: List[int]
    available_slots: int
```

**Example**:
```python
stats = system.get_usage_stats()
print(f"Total items: {stats.total_items}")
print(f"Categories used: {stats.categories_in_use}/100")
print(f"Available slots: {stats.available_slots}")
```

#### reserve_range()

```python
system.reserve_range(
    start: str,
    end: str,
    reason: Optional[str] = None
) -> None
```

Reserve number range for future use.

**Example**:
```python
system.reserve_range("15.00", "15.99", reason="Future expansion")
```

#### clear_reservations()

```python
system.clear_reservations()
```

Clear all reservations.

#### import_existing_structure()

```python
system.import_existing_structure(
    directory: Path
) -> None
```

Import existing Johnny Decimal structure.

---

## Examples

### Basic Usage

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalGenerator,
    JohnnyDecimalConfig
)

# Setup
config = JohnnyDecimalConfig(
    enabled=True,
    auto_assign=True,
    scheme="business"
)

generator = JohnnyDecimalGenerator(config)

# Assign number
result = generator.assign_number(
    Path("invoice.pdf"),
    content_hint="accounting invoice"
)

print(f"Number: {result.number.full_number}")
print(f"Path: {result.suggested_path}")
```

### Custom Scheme

```python
from file_organizer.methodologies.johnny_decimal import (
    NumberingScheme,
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalGenerator
)

# Create custom scheme
scheme = NumberingScheme(name="Software Development")

# Add areas
code_area = AreaDefinition(
    area_range=(10, 19),
    name="Source Code",
    keywords=["code", "source", "implementation"]
)

docs_area = AreaDefinition(
    area_range=(20, 29),
    name="Documentation",
    keywords=["docs", "readme", "guide"]
)

scheme.add_area(code_area)
scheme.add_area(docs_area)

# Add categories
frontend = CategoryDefinition(
    category_number=11,
    name="Frontend",
    keywords=["ui", "react", "vue"],
    parent_area=code_area
)

backend = CategoryDefinition(
    category_number=12,
    name="Backend",
    keywords=["api", "server", "database"],
    parent_area=code_area
)

scheme.add_category(frontend)
scheme.add_category(backend)

# Use custom scheme
generator = JohnnyDecimalGenerator(scheme=scheme)

result = generator.assign_number(
    Path("api-server.py"),
    content_hint="backend API server"
)
# Assigns to category 12 (Backend)
```

### Batch Assignment

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalGenerator

generator = JohnnyDecimalGenerator()

# Get files
files = list(Path("~/Documents").glob("*.pdf"))

# Batch assign
results = generator.batch_assign(files)

# Move files to numbered locations
for file, result in zip(files, results):
    new_path = Path(result.suggested_path)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    file.rename(new_path)
    print(f"Moved: {file.name} → {result.number.full_number}")
```

### Conflict Resolution

```python
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalGenerator,
    ConflictResolver
)

generator = JohnnyDecimalGenerator()
resolver = ConflictResolver(generator)

# Find conflicts
conflicts = resolver.find_all_conflicts(Path("~/Documents"))

if conflicts:
    print(f"Found {len(conflicts)} conflicts")

    # Resolve automatically
    resolved = resolver.resolve_conflicts(conflicts, strategy="increment")

    for conflict in resolved:
        print(f"Resolved: {conflict.number.full_number}")
```

### System Initialization

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalSystem,
    get_default_scheme
)

# Setup system
scheme = get_default_scheme("business")
system = JohnnyDecimalSystem(scheme)

# Initialize directory structure
root = Path("~/Documents-JD").expanduser()
system.initialize(root)

# Prints:
# Created: 10-19-Administration/
# Created: 11-Company-documents/
# Created: 12-Contracts/
# Created: 20-29-Finance/
# etc.

# Get statistics
stats = system.get_usage_stats()
print(f"System capacity: {stats.available_slots} slots available")
```

---

## Exception Handling

```python
from file_organizer.methodologies.johnny_decimal.exceptions import (
    InvalidNumberError,
    CategoryFullError,
    ConflictError,
    SchemeError
)

try:
    result = generator.assign_number(file_path)
except InvalidNumberError as e:
    print(f"Invalid number format: {e}")
except CategoryFullError as e:
    print(f"Category is full: {e}")
except ConflictError as e:
    print(f"Number conflict: {e}")
except SchemeError as e:
    print(f"Scheme error: {e}")
```

---

## Related APIs

- [PARA Methodology API](para-api.md) - Organization system API
- [File Organization API](organization-api.md) - Core organization API

---

**API Version**: 2.0
**Last Updated**: 2026-01-24
