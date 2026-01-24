# Johnny Decimal Numbering System

Implementation of the Johnny Decimal system for hierarchical file organization.

## Overview

The Johnny Decimal system uses a three-level hierarchical numbering scheme:

- **Areas**: 00-99 (e.g., 10-19 for Finance)
- **Categories**: 00.00-99.99 (e.g., 11.01 for Budgets)
- **IDs**: 00.00.000-99.99.999 (e.g., 11.01.001 for Q1 Budget)

This system provides:
- Clear boundaries for organization
- Human-readable numbers
- Easy navigation and search
- Scalable structure (10,000+ items possible)

Based on the Johnny Decimal system by Johnny Noble (johnnydecimal.com).

## Quick Start

### Basic Usage

```python
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalSystem,
    JohnnyDecimalNumber,
)
from pathlib import Path

# Initialize system with default scheme
system = JohnnyDecimalSystem()

# Assign number to a file
result = system.assign_number_to_file(
    file_path=Path("budget-2024.xlsx"),
    content="Annual budget for 2024",
)

print(f"Assigned number: {result.number.formatted_number}")
print(f"Confidence: {result.confidence:.2f}")
print(f"Reasons: {', '.join(result.reasons)}")
```

### Initialize from Existing Directory

```python
# Scan existing directory to detect Johnny Decimal numbers
system.initialize_from_directory(Path("/path/to/organized/files"))

# System will automatically register all found numbers
stats = system.generator.get_usage_statistics()
print(f"Found {stats['total_numbers']} existing numbers")
```

### Custom Number Assignment

```python
# Assign specific number
preferred = JohnnyDecimalNumber(area=10, category=5, name="Reports")

result = system.assign_number_to_file(
    file_path=Path("monthly-report.pdf"),
    preferred_number=preferred,
    auto_register=True,
)
```

### Validate Number

```python
# Check if number is available
number = JohnnyDecimalNumber(area=10, category=1)
result = system.validate_number_assignment(number, Path("test.txt"))

if result.is_confident:
    print("Number is available!")
else:
    print(f"Conflicts: {', '.join(result.conflicts)}")
```

## Custom Schemes

### Define Custom Areas

```python
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalSystem,
    NumberingScheme,
    AreaDefinition,
    CategoryDefinition,
)

# Create custom scheme
scheme = NumberingScheme(
    name="My Custom Scheme",
    description="Custom organization scheme",
)

# Add custom area
custom_area = AreaDefinition(
    area_range_start=60,
    area_range_end=69,
    name="Research & Development",
    description="R&D projects and documentation",
    keywords=["research", "development", "experiment", "prototype"],
    examples=["Research paper", "Prototype design", "Lab results"],
)

scheme.add_area(custom_area)

# Use custom scheme
system = JohnnyDecimalSystem(scheme=scheme)
```

### Define Custom Categories

```python
# Add specific categories within an area
budget_category = CategoryDefinition(
    area=10,
    category=1,
    name="Annual Budgets",
    description="Yearly budget documents",
    keywords=["annual budget", "yearly budget"],
    patterns=["*-budget-*.xlsx", "budget-*.xlsx"],
)

scheme.add_category(budget_category)
```

## Advanced Features

### Content-Based Suggestions

```python
# Suggest number based on file content
content = "This is a marketing campaign plan for Q2 2024"
filename = "q2-campaign.docx"

number, confidence, reasons = system.generator.suggest_number_for_content(
    content=content,
    filename=filename,
    prefer_category=True,
)

print(f"Suggested: {number.formatted_number} (confidence: {confidence:.2f})")
```

### Conflict Resolution

```python
from file_organizer.methodologies.johnny_decimal import NumberConflictError

try:
    result = system.assign_number_to_file(
        file_path=Path("file.txt"),
        preferred_number=number,
    )
except NumberConflictError as e:
    # Handle conflict
    print(f"Conflict: {e}")

    # Resolve by incrementing
    resolved = system.generator.resolve_conflict(number, strategy="increment")
    print(f"Resolved to: {resolved.formatted_number}")
```

### Renumbering

```python
# Renumber an existing file
old_number = JohnnyDecimalNumber(area=10, category=1)
new_number = JohnnyDecimalNumber(area=10, category=5)

result = system.renumber_file(
    old_number=old_number,
    new_number=new_number,
    file_path=Path("file.txt"),
)
```

### Reserve Number Ranges

```python
# Reserve a range of numbers to prevent automatic assignment
start = JohnnyDecimalNumber(area=15, category=0)
end = JohnnyDecimalNumber(area=15, category=9)

system.reserve_number_range(start, end)
```

## Configuration Persistence

### Save Configuration

```python
# Save system state to file
config_path = Path("johnny_decimal_config.json")
system.save_configuration(config_path)
```

### Load Configuration

```python
# Load saved configuration
system = JohnnyDecimalSystem()
system.load_configuration(config_path)
```

## Reporting

### Usage Report

```python
# Get comprehensive usage report
report = system.get_usage_report()

print(f"Scheme: {report['scheme_name']}")
print(f"Total numbers: {report['statistics']['total_numbers']}")
print(f"Areas used: {report['statistics']['areas_used']}")

# View area summaries
for area_summary in report['areas']:
    print(f"  Area {area_summary['area']}: {area_summary['name']}")
    print(f"    Used numbers: {area_summary['used_numbers']}")
```

### Area Summary

```python
# Get details for specific area
summary = system.get_area_summary(10)

print(f"Area 10: {summary['name']}")
print(f"Description: {summary['description']}")
print(f"Numbers in use: {summary['numbers']}")
```

## API Reference

### Core Classes

- `JohnnyDecimalSystem`: Main orchestration class
- `JohnnyDecimalGenerator`: Number generation and validation
- `JohnnyDecimalNumber`: Number data model
- `NumberingScheme`: Complete numbering configuration
- `AreaDefinition`: Area definition with keywords
- `CategoryDefinition`: Category definition with patterns
- `NumberingResult`: Result of number assignment

### Key Methods

#### JohnnyDecimalSystem

- `initialize_from_directory(directory)`: Scan directory for existing numbers
- `assign_number_to_file(file_path, content, preferred_number)`: Assign number to file
- `validate_number_assignment(number, file_path)`: Validate proposed assignment
- `renumber_file(old_number, new_number, file_path)`: Renumber existing file
- `get_usage_report()`: Get comprehensive usage statistics
- `save_configuration(path)`: Save configuration to file
- `load_configuration(path)`: Load configuration from file

#### JohnnyDecimalGenerator

- `generate_area_number(name, description)`: Generate area-level number
- `generate_category_number(area, name)`: Generate category-level number
- `generate_id_number(area, category, name)`: Generate ID-level number
- `suggest_number_for_content(content, filename)`: Suggest based on content
- `validate_number(number)`: Validate number against scheme
- `resolve_conflict(number, strategy)`: Resolve number conflicts

## Examples

See `tests/methodologies/johnny_decimal/` for comprehensive examples and test cases.

## License

MIT License - Part of File Organizer v2.0
