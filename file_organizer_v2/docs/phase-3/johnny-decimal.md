# Johnny Decimal System Guide

## Overview

The Johnny Decimal system is a structured numbering scheme that provides a clear, logical way to organize files and folders. Every item in your system is assigned a unique number in the format **XX.YY**, making it easy to find, reference, and maintain your digital organization.

File Organizer v2 provides automatic Johnny Decimal number generation, conflict resolution, and integration with existing folder structures.

## What is Johnny Decimal?

### The Numbering System

Johnny Decimal uses a two-level hierarchy:

**Areas (00-99)** - Broad categories
- 10-19: Administration
- 20-29: Finance
- 30-39: Projects
- etc.

**Categories (00-99)** - Specific topics within areas
- 11: Company documents
- 12: Contracts
- 13: Policies
- etc.

**IDs (00-99)** - Individual items within categories
- 11.01: Business registration
- 11.02: Insurance documents
- 12.01: Client contract template
- etc.

### Example Structure

```
10-19 Administration/
├── 11 Company documents/
│   ├── 11.01 Business registration/
│   ├── 11.02 Insurance/
│   └── 11.03 Licenses/
├── 12 Contracts/
│   ├── 12.01 Templates/
│   └── 12.02 Signed contracts/
└── 13 Policies/
    ├── 13.01 HR policies/
    └── 13.02 IT policies/

20-29 Finance/
├── 21 Accounting/
│   ├── 21.01 Invoices sent/
│   ├── 21.02 Invoices received/
│   └── 21.03 Bank statements/
└── 22 Budgets/
    ├── 22.01 Annual budgets/
    └── 22.02 Project budgets/
```

## Getting Started

### Quick Start

1. **Initialize Johnny Decimal system**:
```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalSystem

system = JohnnyDecimalSystem()
system.initialize("~/Documents")
```

2. **Organize your first file**:
```bash
file-organizer organize document.pdf --methodology johnny-decimal
```

3. **View assigned number**:
```
File: document.pdf
Assigned: 11.04
Category: 11 Company documents
Area: 10-19 Administration
```

### Installation

Johnny Decimal support is built into File Organizer v2. No additional setup required.

## Auto-Generation

### How It Works

File Organizer automatically assigns Johnny Decimal numbers based on:

1. **Content Analysis** - Examines file content to determine topic
2. **Existing Structure** - Looks at where file currently resides
3. **Naming Patterns** - Analyzes filename for category hints
4. **Metadata** - Uses file metadata (tags, descriptions)

### Number Assignment

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalGenerator

generator = JohnnyDecimalGenerator()

# Assign number to a file
result = generator.assign_number(
    file_path="invoice-2024.pdf",
    content_hint="accounting invoice",
    suggested_area=20  # Finance area
)

print(f"Assigned: {result.number}")  # e.g., "21.05"
print(f"Category: {result.category.name}")  # "21 Accounting"
print(f"Confidence: {result.confidence}%")
```

### Confidence Scoring

- **High (>90%)**: Clear indicators, reliable assignment
- **Medium (70-90%)**: Good match, minor ambiguity
- **Low (<70%)**: Manual review recommended

## Creating Custom Numbering Schemes

### Define Your Own Structure

```python
from file_organizer.methodologies.johnny_decimal import (
    NumberingScheme,
    AreaDefinition,
    CategoryDefinition
)

# Create custom scheme
scheme = NumberingScheme(name="My Custom Scheme")

# Define areas
admin_area = AreaDefinition(
    area_range=(10, 19),
    name="Administration",
    description="Company admin and operations"
)

# Define categories within area
company_docs = CategoryDefinition(
    category_number=11,
    name="Company documents",
    keywords=["registration", "license", "insurance"],
    parent_area=admin_area
)

contracts = CategoryDefinition(
    category_number=12,
    name="Contracts",
    keywords=["contract", "agreement", "terms"],
    parent_area=admin_area
)

# Add to scheme
scheme.add_area(admin_area)
scheme.add_category(company_docs)
scheme.add_category(contracts)

# Use custom scheme
generator = JohnnyDecimalGenerator(scheme=scheme)
```

### Pre-defined Schemes

File Organizer includes standard schemes:

```python
from file_organizer.methodologies.johnny_decimal import get_default_scheme

# Business scheme
business_scheme = get_default_scheme("business")

# Personal scheme
personal_scheme = get_default_scheme("personal")

# Research scheme
research_scheme = get_default_scheme("research")

# Creative scheme
creative_scheme = get_default_scheme("creative")
```

## Conflict Resolution

### Detecting Conflicts

```python
# Check if number is available
if generator.is_number_available("11.04"):
    print("Number is free to use")
else:
    conflicts = generator.find_conflicts("11.04")
    print(f"Conflicts found: {conflicts}")
```

### Resolution Strategies

**Auto-increment**:
```python
# Automatically find next available number
result = generator.assign_number(
    file_path="document.pdf",
    preferred_category=11,
    conflict_resolution="increment"
)
# If 11.04 is taken, tries 11.05, 11.06, etc.
```

**Skip to next category**:
```python
result = generator.assign_number(
    file_path="document.pdf",
    preferred_category=11,
    conflict_resolution="skip"
)
# If category 11 is full, moves to category 12
```

**Manual resolution**:
```python
result = generator.assign_number(
    file_path="document.pdf",
    preferred_category=11,
    conflict_resolution="manual"
)
# Flags for user review
if result.needs_manual_review:
    print(f"Please assign number manually. Suggested: {result.suggested_alternatives}")
```

## Integration with Existing Structures

### Migration from Traditional Folders

**Step 1: Analyze existing structure**
```bash
file-organizer analyze ~/Documents --methodology johnny-decimal --generate-scheme
```

This scans your folders and suggests a Johnny Decimal scheme:
```
Suggested Scheme:
10-19: Administration (found 45 admin files)
  11: Company documents (12 files)
  12: Contracts (18 files)
  13: Policies (15 files)
20-29: Finance (found 89 finance files)
  21: Accounting (52 files)
  22: Budgets (24 files)
  23: Reports (13 files)
```

**Step 2: Review and customize**
```bash
file-organizer scheme edit ~/Documents/.jd-scheme.json
```

**Step 3: Execute migration**
```bash
file-organizer migrate ~/Documents --methodology johnny-decimal --preserve-originals
```

### Preserving Partial Numbering

If you already have some Johnny Decimal numbers:

```python
# Import existing numbers
generator.import_existing_structure("~/Documents")

# Assign new numbers without conflicts
result = generator.assign_number(
    file_path="new-file.pdf",
    respect_existing=True  # Won't reassign existing numbers
)
```

## Number Validation

### Validation Rules

Johnny Decimal enforces strict rules:

```python
from file_organizer.methodologies.johnny_decimal import validate_number

# Valid numbers
validate_number("11.04")  # ✅ Valid
validate_number("11.99")  # ✅ Valid
validate_number("00.01")  # ✅ Valid (edge case)

# Invalid numbers
validate_number("11.100")  # ❌ ID must be 00-99
validate_number("100.01")  # ❌ Category must be 00-99
validate_number("11")      # ❌ Missing ID component
validate_number("11.4")    # ❌ ID must be two digits
```

### Range Validation

```python
# Check if number fits in category's range
category = scheme.get_category(11)

if category.is_in_range("11.04"):
    print("Number is valid for this category")

# Check area ranges
area = scheme.get_area_for_category(11)
if area.contains_category(11):
    print("Category is in correct area")
```

## Configuration

### System Configuration

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalConfig

config = JohnnyDecimalConfig(
    # Auto-generation settings
    auto_assign=True,
    auto_increment=True,
    skip_full_categories=True,

    # Validation settings
    enforce_strict_ranges=True,
    allow_category_99=False,  # Reserve 99 for misc

    # Conflict resolution
    default_conflict_strategy="increment",
    max_retries=10,

    # Numbering preferences
    start_from="01",  # Start IDs from 01 not 00
    reserve_ranges=[],  # Reserved numbers

    # Naming format
    include_number_in_name=True,
    separator=" - ",  # "11.04 - Document name"
)
```

### Per-Category Configuration

```python
# Configure specific categories
config.set_category_config(
    category=11,
    settings={
        "max_items": 50,  # Limit items per category
        "auto_archive_at": 45,  # Archive when nearing limit
        "priority": "high",  # Prefer this category for ambiguous files
    }
)
```

## Best Practices

### Structuring Your System

**Start with areas (10s)**:
- 10-19: Administration
- 20-29: Finance
- 30-39: Projects
- 40-49: Marketing
- 50-59: Operations
- 60-69: HR
- 70-79: IT
- 80-89: Research
- 90-99: Archive/Misc

**Keep it balanced**:
- Aim for 3-7 categories per area
- Don't go beyond 50 items per category
- Use area 90-99 for overflow

**Be consistent**:
- Use same numbering logic across areas
- Document your scheme
- Train team members

### Naming Conventions

**Include numbers in folder names**:
```
11 Company documents/
12 Contracts/
13 Policies/
```

**Include numbers in file names**:
```
11.01 Business registration certificate.pdf
11.02 Insurance policy.pdf
11.03 Trade license.pdf
```

**Alternative format**:
```
11.01 - Business registration certificate.pdf
```

### Documentation

Create a Johnny Decimal index:

```markdown
# Johnny Decimal Index

## 10-19 Administration
- 11: Company documents
  - 11.01: Business registration
  - 11.02: Insurance
  - 11.03: Licenses
- 12: Contracts
  - 12.01: Templates
  - 12.02: Signed contracts
- 13: Policies
  - 13.01: HR policies
  - 13.02: IT policies

## 20-29 Finance
- 21: Accounting
  - 21.01: Invoices sent
  - 21.02: Invoices received
  - 21.03: Bank statements
```

Save as `00.00 Johnny Decimal Index.md`

## CLI Usage

### Commands

```bash
# Initialize system
file-organizer jd init ~/Documents

# Assign number to file
file-organizer jd assign document.pdf --category 11

# Find next available number
file-organizer jd next-available --category 11

# Validate number
file-organizer jd validate 11.04

# Generate scheme from existing structure
file-organizer jd generate-scheme ~/Documents

# Export scheme
file-organizer jd export-scheme > my-scheme.json

# Import scheme
file-organizer jd import-scheme my-scheme.json

# Show usage statistics
file-organizer jd stats ~/Documents
```

### Batch Operations

```bash
# Assign numbers to all files in directory
file-organizer jd batch-assign ~/Documents/11-company-docs/

# Renumber existing files
file-organizer jd renumber ~/Documents --start-from 11.01
```

## API Reference

### Basic Usage

```python
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalSystem,
    JohnnyDecimalGenerator,
    NumberingScheme
)

# Initialize system
system = JohnnyDecimalSystem()

# Generate numbers
generator = JohnnyDecimalGenerator()

# Assign number
result = generator.assign_number("document.pdf")

print(f"Number: {result.number}")
print(f"Category: {result.category}")
print(f"Path: {result.suggested_path}")
```

### Advanced Features

```python
# Get usage statistics
stats = system.get_usage_stats()
print(f"Total items: {stats.total_items}")
print(f"Categories used: {stats.categories_in_use}")
print(f"Available slots: {stats.available_slots}")

# Find conflicts
conflicts = system.find_conflicts("11.04")
for conflict in conflicts:
    print(f"Conflict: {conflict.file_path} already uses {conflict.number}")

# Reserve number ranges
system.reserve_range("15.00", "15.99", reason="Future expansion")

# Clear reservations
system.clear_reservations()
```

## Troubleshooting

### Common Issues

**Problem**: Running out of numbers in category

**Solution**:
1. Archive old items to free up numbers
2. Use sub-categories (11.01a, 11.01b) temporarily
3. Split category into two categories

**Problem**: Conflicting numbers

**Solution**:
```bash
# Find all conflicts
file-organizer jd check-conflicts ~/Documents

# Auto-resolve conflicts
file-organizer jd resolve-conflicts ~/Documents --strategy increment
```

**Problem**: Incorrect auto-assignment

**Solution**:
1. Provide better content hints
2. Add custom categories for your domain
3. Use manual assignment for edge cases

### Validation Errors

**Invalid number format**:
```python
try:
    result = generator.assign_number("document.pdf", preferred_number="11.4")
except ValueError as e:
    print(f"Error: {e}")
    # Use next available instead
    result = generator.assign_number("document.pdf", category=11)
```

## Advanced Usage

### Custom Number Formats

```python
class CustomNumberFormat:
    """Custom number format: AA.BB.CC for deeper hierarchy."""

    def format(self, area, category, id, subcategory=None):
        if subcategory:
            return f"{area:02d}.{category:02d}.{id:02d}.{subcategory:02d}"
        return f"{area:02d}.{category:02d}.{id:02d}"

    def parse(self, number_string):
        parts = number_string.split(".")
        return {
            "area": int(parts[0]),
            "category": int(parts[1]),
            "id": int(parts[2]),
            "subcategory": int(parts[3]) if len(parts) > 3 else None
        }

generator.set_number_format(CustomNumberFormat())
```

### Integration with PARA

Combine Johnny Decimal with PARA:

```
1-Projects/
├── 30-39-Active-Projects/
│   ├── 31 Client work/
│   │   ├── 31.01 Project Alpha/
│   │   └── 31.02 Project Beta/
│   └── 32 Internal projects/
│       └── 32.01 Website redesign/
2-Areas/
├── 20-29-Finance/
│   └── 21 Accounting/
│       ├── 21.01 Invoices/
│       └── 21.02 Statements/
```

### Automated Workflows

```python
# Watch directory and auto-assign numbers
from file_organizer.watchers import DirectoryWatcher

watcher = DirectoryWatcher("~/Documents/Inbox")

@watcher.on_new_file
def assign_number(file_path):
    result = generator.assign_number(file_path)
    new_path = result.suggested_path
    os.rename(file_path, new_path)
    print(f"Assigned {result.number} to {file_path.name}")

watcher.start()
```

## Real-World Examples

### Personal Organization

```
10-19 Personal Admin/
├── 11 Identity/
│   ├── 11.01 Passport/
│   ├── 11.02 Driver license/
│   └── 11.03 Birth certificate/
├── 12 Finance/
│   ├── 12.01 Bank accounts/
│   └── 12.02 Investment/
└── 13 Health/
    ├── 13.01 Medical records/
    └── 13.02 Insurance/

20-29 Home/
├── 21 Property/
│   ├── 21.01 Lease/
│   └── 21.02 Utilities/
└── 22 Maintenance/
    └── 22.01 Repairs/
```

### Business Organization

```
10-19 Administration/
20-29 Finance/
30-39 Sales/
40-49 Marketing/
50-59 Operations/
60-69 HR/
70-79 IT/
80-89 Legal/
90-99 Archive/
```

### Academic Research

```
10-19 Literature/
├── 11 Papers/
├── 12 Books/
└── 13 Notes/
20-29 Data/
├── 21 Raw data/
├── 22 Processed data/
└── 23 Analysis/
30-39 Writing/
├── 31 Drafts/
├── 32 Published/
└── 33 Presentations/
```

## Related Features

- [PARA Methodology](para-methodology.md) - Combine with Johnny Decimal
- [Smart Organization](../api/organization-api.md) - Automatic categorization
- [File Organization Patterns](tutorials/organization-patterns.md)

## Further Reading

- [Johnny Decimal Official Site](https://johnnydecimal.com/)
- [Implementation Examples](tutorials/johnny-decimal-setup.md)
- [Scheme Templates](../configuration/johnny-decimal-schemes.md)

---

**Next Steps**: Set up your first Johnny Decimal system using the [Quick Start Tutorial](tutorials/johnny-decimal-setup.md)
