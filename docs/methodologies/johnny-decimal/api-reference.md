# Johnny Decimal API Reference

## Overview

This document provides comprehensive API documentation for the Johnny Decimal methodology implementation in File Organizer v2.0.

## Installation

```bash
pip install file-organizer-v2
```

## Quick Start

```python
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalSystem,
    JohnnyDecimalMigrator,
    create_para_compatible_config,
)

# Create a JD system
system = JohnnyDecimalSystem()

# Or migrate existing structure
migrator = JohnnyDecimalMigrator()
```

## Core Classes

### JohnnyDecimalNumber

Represents a Johnny Decimal number.

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalNumber, NumberLevel

# Create a category number (10.01)
number = JohnnyDecimalNumber(
    area=10,
    category=1,
    id_number=None,
    level=NumberLevel.CATEGORY
)

print(number.formatted_number)  # "10.01"
print(number.level)             # NumberLevel.CATEGORY
```

**Attributes:**
- `area` (int): Area number (10-99)
- `category` (Optional[int]): Category number (01-99)
- `id_number` (Optional[int]): ID number (001-999)
- `level` (NumberLevel): Hierarchy level
- `formatted_number` (str): Formatted string representation

**Properties:**
- `is_area() -> bool`: Check if this is an area-level number
- `is_category() -> bool`: Check if this is a category-level number
- `is_id() -> bool`: Check if this is an ID-level number

### NumberLevel

Enum defining hierarchy levels.

```python
from file_organizer.methodologies.johnny_decimal import NumberLevel

NumberLevel.AREA       # Area level (10)
NumberLevel.CATEGORY   # Category level (10.01)
NumberLevel.ID         # ID level (10.01.001)
```

### JohnnyDecimalSystem

Main system class for creating and managing JD structure.

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalSystem

system = JohnnyDecimalSystem()

# Create area
area_num = system.create_area(10, "Finance")
# Returns: JohnnyDecimalNumber(area=10, ...)

# Create category
cat_num = system.create_category(10, 1, "Budgets")
# Returns: JohnnyDecimalNumber(area=10, category=1, ...)

# Create ID
id_num = system.create_id(10, 1, 1, "2024 Budget")
# Returns: JohnnyDecimalNumber(area=10, category=1, id_number=1, ...)
```

**Methods:**

#### create_area(area_number, title) -> JohnnyDecimalNumber
Create an area-level number.

**Parameters:**
- `area_number` (int): Area number (10-99)
- `title` (str): Area title

**Returns:** JohnnyDecimalNumber at area level

#### create_category(area_number, category_number, title) -> JohnnyDecimalNumber
Create a category-level number.

**Parameters:**
- `area_number` (int): Parent area number
- `category_number` (int): Category number (01-99)
- `title` (str): Category title

**Returns:** JohnnyDecimalNumber at category level

#### create_id(area_number, category_number, id_number, title) -> JohnnyDecimalNumber
Create an ID-level number.

**Parameters:**
- `area_number` (int): Parent area number
- `category_number` (int): Parent category number
- `id_number` (int): ID number (001-999)
- `title` (str): ID title

**Returns:** JohnnyDecimalNumber at ID level

### JohnnyDecimalGenerator

Manages number generation and allocation.

```python
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalGenerator,
    get_default_scheme,
)

scheme = get_default_scheme()
generator = JohnnyDecimalGenerator(scheme)

# Generate next available area
area = generator.generate_area()

# Generate category in area 10
category = generator.generate_category(area_number=10)

# Generate ID in category 10.01
id_num = generator.generate_id(area_number=10, category_number=1)

# Check if number is available
is_available = generator.is_number_available(number)

# Register existing number
generator.register_number(number)
```

**Methods:**

#### generate_area() -> NumberingResult
Generate next available area number.

#### generate_category(area_number: int) -> NumberingResult
Generate next available category in area.

#### generate_id(area_number: int, category_number: int) -> NumberingResult
Generate next available ID in category.

#### is_number_available(number: JohnnyDecimalNumber) -> bool
Check if number is available for use.

#### register_number(number: JohnnyDecimalNumber, description: str = "") -> None
Register a number as used.

## Migration Classes

### FolderScanner

Scans existing folder structures.

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import FolderScanner

scanner = FolderScanner(
    scheme=None,        # Optional numbering scheme
    max_depth=10,       # Maximum scan depth
    skip_hidden=True    # Skip hidden files/folders
)

# Scan directory
result = scanner.scan_directory(Path("/path/to/folders"))

# Access results
print(f"Total folders: {result.total_folders}")
print(f"Total files: {result.total_files}")
print(f"Max depth: {result.max_depth}")
print(f"Patterns: {result.detected_patterns}")
```

**Returns:** ScanResult with:
- `root_path` (Path): Scanned root path
- `total_folders` (int): Number of folders found
- `total_files` (int): Number of files found
- `total_size` (int): Total size in bytes
- `max_depth` (int): Maximum nesting depth
- `folder_tree` (List[FolderInfo]): Hierarchical folder structure
- `detected_patterns` (List[str]): Organizational patterns detected
- `warnings` (List[str]): Potential issues

### FolderTransformer

Creates transformation plans for migration.

```python
from file_organizer.methodologies.johnny_decimal import (
    FolderTransformer,
    JohnnyDecimalGenerator,
    get_default_scheme,
)

scheme = get_default_scheme()
generator = JohnnyDecimalGenerator(scheme)
transformer = FolderTransformer(
    scheme=scheme,
    generator=generator,
    preserve_original_names=True  # Keep folder names after numbers
)

# Create transformation plan
plan = transformer.create_transformation_plan(
    folder_tree=scan_result.folder_tree,
    root_path=Path("/path")
)

# Generate preview
preview = transformer.generate_preview(plan)
print(preview)
```

**Returns:** TransformationPlan with:
- `root_path` (Path): Root directory path
- `rules` (List[TransformationRule]): Transformation rules
- `estimated_changes` (int): Number of changes
- `conflicts` (List[str]): Detected conflicts
- `warnings` (List[str]): Warnings

### MigrationValidator

Validates transformation plans.

```python
from file_organizer.methodologies.johnny_decimal import (
    MigrationValidator,
    JohnnyDecimalGenerator,
)

generator = JohnnyDecimalGenerator(scheme)
validator = MigrationValidator(generator)

# Validate plan
result = validator.validate_plan(plan)

if result.is_valid:
    print("✅ Plan is valid")
else:
    print(f"❌ Errors: {len(result.errors)}")
    for error in result.errors:
        print(f"  - {error.message}")

# Generate report
report = validator.generate_report(result)
print(report)
```

**Returns:** ValidationResult with:
- `is_valid` (bool): Whether plan is valid
- `issues` (List[ValidationIssue]): All issues
- `errors` (List[ValidationIssue]): Blocking errors
- `warnings` (List[ValidationIssue]): Non-blocking warnings
- `info` (List[ValidationIssue]): Informational messages

### JohnnyDecimalMigrator

Orchestrates complete migration workflow.

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalMigrator

migrator = JohnnyDecimalMigrator(
    scheme=None,                      # Optional scheme (default if None)
    preserve_original_names=True      # Keep folder names
)

# Create migration plan
plan, scan_result = migrator.create_migration_plan(Path("/path"))

# Validate plan
validation = migrator.validate_plan(plan)

# Generate preview
preview = migrator.generate_preview(plan, scan_result, validation)
print(preview)

# Execute migration
result = migrator.execute_migration(
    plan,
    dry_run=True,          # Preview mode
    create_backup=True     # Create backup
)

# Check results
print(f"Transformed: {result.transformed_count}")
print(f"Failed: {result.failed_count}")
print(f"Backup: {result.backup_path}")

# Rollback if needed
success = migrator.rollback()
```

**Methods:**

#### create_migration_plan(root_path: Path) -> Tuple[TransformationPlan, ScanResult]
Create complete migration plan.

#### validate_plan(plan: TransformationPlan) -> ValidationResult
Validate transformation plan.

#### execute_migration(plan, dry_run=True, create_backup=True) -> MigrationResult
Execute transformation plan.

#### rollback(migration_id: Optional[str] = None) -> bool
Rollback a migration.

#### generate_preview(plan, scan_result, validation=None) -> str
Generate human-readable preview.

#### generate_report(result: MigrationResult) -> str
Generate migration report.

## Configuration Classes

### JohnnyDecimalConfig

Complete configuration for JD system.

```python
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalConfig,
    create_default_config,
    create_para_compatible_config,
)

# Create default config
config = create_default_config()

# Create PARA-compatible config
config = create_para_compatible_config()

# Load from file
config = JohnnyDecimalConfig.load_from_file(Path("config.json"))

# Save to file
config.save_to_file(Path("config.json"))

# Convert to/from dict
config_dict = config.to_dict()
config = JohnnyDecimalConfig.from_dict(config_dict)
```

**Attributes:**
- `scheme` (NumberingScheme): Numbering scheme
- `migration` (MigrationConfig): Migration settings
- `compatibility` (CompatibilityConfig): Compatibility settings
- `custom_mappings` (Dict[str, int]): Custom folder mappings

### ConfigBuilder

Fluent API for building configurations.

```python
from file_organizer.methodologies.johnny_decimal import ConfigBuilder

config = (
    ConfigBuilder("my-scheme")
    .add_area(10, "Finance", "Financial documents")
    .add_category(10, 1, "Budgets", "Annual budgets")
    .add_category(10, 2, "Invoices", "Client invoices")
    .with_migration_config(
        preserve_names=True,
        create_backups=True,
        max_depth=10
    )
    .with_para_integration(
        enabled=True,
        projects_area=10,
        areas_area=20,
        resources_area=30,
        archive_area=40
    )
    .add_custom_mapping("finance", 10)
    .add_custom_mapping("personal", 20)
    .build()
)
```

**Methods:**

#### add_area(area_number, title, description="") -> ConfigBuilder
Add area definition.

#### add_category(area_number, category_number, title, description="") -> ConfigBuilder
Add category definition.

#### with_migration_config(...) -> ConfigBuilder
Configure migration settings.

#### with_para_integration(...) -> ConfigBuilder
Enable PARA integration.

#### add_custom_mapping(folder_name, area_number) -> ConfigBuilder
Add custom folder mapping.

#### build() -> JohnnyDecimalConfig
Build configuration.

## Compatibility Classes

### PARACategory

Enum for PARA methodology categories.

```python
from file_organizer.methodologies.johnny_decimal import PARACategory

PARACategory.PROJECTS    # Active projects
PARACategory.AREAS       # Ongoing responsibilities
PARACategory.RESOURCES   # Reference materials
PARACategory.ARCHIVE     # Completed items
```

### PARAJohnnyDecimalBridge

Bridge between PARA and JD systems.

```python
from file_organizer.methodologies.johnny_decimal import (
    PARAJohnnyDecimalBridge,
    PARAIntegrationConfig,
    PARACategory,
)

config = PARAIntegrationConfig(
    enabled=True,
    projects_area=10,
    areas_area=20,
    resources_area=30,
    archive_area=40
)

bridge = PARAJohnnyDecimalBridge(config)

# Convert PARA to JD area
jd_area = bridge.para_to_jd_area(PARACategory.PROJECTS, index=0)
# Returns: 10

# Convert JD area to PARA
para_cat = bridge.jd_area_to_para(15)
# Returns: PARACategory.PROJECTS

# Check if area is in PARA range
is_para = bridge.is_para_area(15)
# Returns: True

# Get path suggestion
path = bridge.get_para_path_suggestion(
    PARACategory.PROJECTS,
    "Website Redesign"
)
# Returns: "10 Projects / 10.01 Website Redesign"

# Create PARA structure
paths = bridge.create_para_structure(Path("/root"))
# Creates all PARA category folders
```

### CompatibilityAnalyzer

Analyzes structures for PARA patterns.

```python
from file_organizer.methodologies.johnny_decimal import CompatibilityAnalyzer

analyzer = CompatibilityAnalyzer(config)

# Detect PARA structure
detected = analyzer.detect_para_structure(Path("/path"))
# Returns: Dict[PARACategory, Optional[Path]]

# Check for mixed structure
is_mixed = analyzer.is_mixed_structure(Path("/path"))
# Returns: bool

# Get migration strategy
strategy = analyzer.suggest_migration_strategy(Path("/path"))
# Returns: Dict with recommendations
```

### HybridOrganizer

Manages hybrid PARA + JD structures.

```python
from file_organizer.methodologies.johnny_decimal import HybridOrganizer

organizer = HybridOrganizer(config)

# Create hybrid structure
paths = organizer.create_hybrid_structure(Path("/root"))

# Categorize item
jd_number = organizer.categorize_item(
    "Website Project",
    PARACategory.PROJECTS
)

# Get item path
path = organizer.get_item_path(
    Path("/root"),
    PARACategory.PROJECTS,
    jd_number,
    "Website Project"
)
```

## Adapter Classes

### OrganizationItem

Generic item in any organizational system.

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import OrganizationItem

item = OrganizationItem(
    name="Budget 2024",
    path=Path("Finance/Budgets/2024"),
    category="finance",
    metadata={"year": 2024}
)
```

### PARAAdapter

Adapter for PARA methodology.

```python
from file_organizer.methodologies.johnny_decimal import (
    PARAAdapter,
    OrganizationItem,
)

adapter = PARAAdapter(config)

# Adapt PARA item to JD
para_item = OrganizationItem(
    name="Website Project",
    path=Path("Projects/Website"),
    category="projects",
    metadata={}
)

jd_number = adapter.adapt_to_jd(para_item)

# Adapt JD to PARA item
para_item = adapter.adapt_from_jd(jd_number, "Website Project")

# Check if item can be adapted
can_adapt = adapter.can_adapt(para_item)
```

### FileSystemAdapter

Adapter for generic filesystem organization.

```python
from file_organizer.methodologies.johnny_decimal import FileSystemAdapter

adapter = FileSystemAdapter(config)

# Adapt filesystem item to JD
fs_item = OrganizationItem(
    name="Documents",
    path=Path("Documents"),
    category="filesystem",
    metadata={}
)

jd_number = adapter.adapt_to_jd(fs_item)
para_item = adapter.adapt_from_jd(jd_number, "Documents")
```

### AdapterRegistry

Registry for managing multiple adapters.

```python
from file_organizer.methodologies.johnny_decimal import (
    AdapterRegistry,
    create_default_registry,
)

# Create with default adapters
registry = create_default_registry(config)

# Get adapter for item
adapter = registry.get_adapter(item)

# Adapt to JD
jd_number = registry.adapt_to_jd(item)

# Adapt from JD
item = registry.adapt_from_jd(jd_number, "Item Name", "para")
```

## Exceptions

### NumberConflictError

Raised when JD number is already in use.

```python
from file_organizer.methodologies.johnny_decimal import NumberConflictError

try:
    generator.register_number(number)
except NumberConflictError as e:
    print(f"Number conflict: {e}")
```

### InvalidNumberError

Raised when JD number is invalid.

```python
from file_organizer.methodologies.johnny_decimal import InvalidNumberError

try:
    number = JohnnyDecimalNumber(area=5, ...)  # Invalid: must be 10-99
except InvalidNumberError as e:
    print(f"Invalid number: {e}")
```

## Data Classes

### AreaDefinition

Defines a JD area.

```python
from file_organizer.methodologies.johnny_decimal import AreaDefinition

area = AreaDefinition(
    area_number=10,
    title="Finance",
    description="Financial documents and records"
)
```

### CategoryDefinition

Defines a JD category.

```python
from file_organizer.methodologies.johnny_decimal import CategoryDefinition

category = CategoryDefinition(
    area_number=10,
    category_number=1,
    title="Budgets",
    description="Annual and quarterly budgets"
)
```

### NumberingScheme

Complete numbering scheme definition.

```python
from file_organizer.methodologies.johnny_decimal import (
    NumberingScheme,
    get_default_scheme,
)

# Get default scheme
scheme = get_default_scheme()

# Create custom scheme
scheme = NumberingScheme(
    name="my-scheme",
    areas=[area1, area2],
    categories=[cat1, cat2]
)
```

## Utility Functions

### get_default_scheme() -> NumberingScheme
Get default numbering scheme.

### create_default_config() -> JohnnyDecimalConfig
Create default configuration.

### create_para_compatible_config() -> JohnnyDecimalConfig
Create PARA-compatible configuration.

### create_default_registry(config) -> AdapterRegistry
Create adapter registry with default adapters.

## Complete Examples

### Example 1: Basic Usage

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalSystem

system = JohnnyDecimalSystem()

# Create structure
area = system.create_area(10, "Finance")
category = system.create_category(10, 1, "Budgets")
id_num = system.create_id(10, 1, 1, "2024 Budget")

print(f"Created: {id_num.formatted_number}")
```

### Example 2: Migration

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalMigrator

migrator = JohnnyDecimalMigrator()
root = Path("~/Documents").expanduser()

# Full workflow
plan, scan = migrator.create_migration_plan(root)
validation = migrator.validate_plan(plan)

if validation.is_valid:
    result = migrator.execute_migration(plan, dry_run=False)
    print(f"Migrated {result.transformed_count} folders")
```

### Example 3: PARA Integration

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import (
    create_para_compatible_config,
    HybridOrganizer,
    PARACategory,
)

config = create_para_compatible_config()
organizer = HybridOrganizer(config)
root = Path("~/Documents")

# Create hybrid structure
organizer.create_hybrid_structure(root)

# Add project
jd_num = organizer.categorize_item("Website", PARACategory.PROJECTS)
path = organizer.get_item_path(root, PARACategory.PROJECTS, jd_num, "Website")
path.mkdir(parents=True, exist_ok=True)
```

## See Also

- [User Guide](user-guide.md): End-user documentation
- [Migration Guide](migration.md): Migration walkthrough
- [PARA Compatibility](para-compatibility.md): PARA integration guide
- [FAQ](faq.md): Frequently asked questions

---

*For bug reports or feature requests, please open an issue on GitHub.*
