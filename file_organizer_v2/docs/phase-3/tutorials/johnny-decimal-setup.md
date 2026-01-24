# Quick Start: Johnny Decimal System Setup

This tutorial will guide you through setting up the Johnny Decimal numbering system with File Organizer v2 in under 15 minutes.

## Prerequisites

- File Organizer v2 installed
- A directory to organize
- Basic understanding of Johnny Decimal concepts

## Step 1: Choose Your Scheme (3 minutes)

Select a pre-defined scheme or create your own:

### Option A: Use Pre-defined Scheme

<!-- JD CLI commands not yet implemented
```bash
file-organizer jd list-schemes
file-organizer jd init ~/Documents --scheme business
```
-->

**Note**: Johnny Decimal CLI commands are planned for future release. For now, use the Python API:

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalSystem
from file_organizer.methodologies.johnny_decimal.numbering import NumberingScheme
from pathlib import Path

system = JohnnyDecimalSystem()
# Pre-defined schemes: business, personal, research, creative
scheme = NumberingScheme.load_predefined("business")
system.set_scheme(scheme)
system.initialize_from_directory(Path.home() / "Documents")
```

### Option B: Generate from Existing Structure

```bash
# Analyze existing folders
file-organizer jd generate-scheme ~/Documents --output my-scheme.json

# Review generated scheme
cat my-scheme.json

# Apply scheme
file-organizer jd init ~/Documents --scheme my-scheme.json
```

## Step 2: Initialize Your System (2 minutes)

Create the Johnny Decimal structure:

```bash
# Initialize with chosen scheme
file-organizer jd init ~/Documents-JD --scheme business

# Creates structure:
# 10-19-Administration/
# 20-29-Finance/
# 30-39-Projects/
# 40-49-Marketing/
# 50-59-Operations/
# 60-69-HR/
# 70-79-IT/
# 80-89-Legal/
# 90-99-Archive/
```

## Step 3: Assign Numbers to Existing Files (5 minutes)

Let File Organizer automatically assign numbers:

```bash
# Dry run first
file-organizer jd batch-assign ~/Documents \
    --methodology johnny-decimal \
    --dry-run

# Example output:
# Assigning numbers...
# ├── company-registration.pdf → 11.01 (Company documents)
# ├── contract-template.docx → 12.01 (Contracts)
# ├── invoice-2024.pdf → 21.01 (Accounting)
# └── ...
#
# 156 files analyzed
# 156 numbers assigned
# 0 conflicts detected
```

If results look good, execute:

```bash
file-organizer jd batch-assign ~/Documents \
    --methodology johnny-decimal \
    --output ~/Documents-JD
```

## Step 4: Organize Files (3 minutes)

Move files to their numbered locations:

```bash
# Move files with assigned numbers
file-organizer organize ~/Documents \
    --methodology johnny-decimal \
    --output ~/Documents-JD \
    --include-numbers-in-names
```

Result:
```
~/Documents-JD/
├── 10-19-Administration/
│   ├── 11-Company-documents/
│   │   ├── 11.01-Business-registration.pdf
│   │   ├── 11.02-Insurance-policy.pdf
│   │   └── 11.03-Trade-license.pdf
│   └── 12-Contracts/
│       ├── 12.01-Template-NDA.docx
│       └── 12.02-Client-contract.pdf
└── 20-29-Finance/
    └── 21-Accounting/
        ├── 21.01-Invoice-template.xlsx
        └── 21.02-Q1-report.pdf
```

## Step 5: Create Your Index (2 minutes)

Document your numbering system:

```bash
# Generate index automatically
file-organizer jd generate-index ~/Documents-JD > "00.00 Index.md"
```

Example index:
```markdown
# Johnny Decimal Index

## 10-19 Administration
- **11** Company documents
  - 11.01: Business registration
  - 11.02: Insurance policy
  - 11.03: Trade license
- **12** Contracts
  - 12.01: Template NDA
  - 12.02: Client contracts

## 20-29 Finance
- **21** Accounting
  - 21.01: Invoice templates
  - 21.02: Financial reports
- **22** Budgets
  - 22.01: Annual budget
  - 22.02: Project budgets
```

## Daily Usage

### Adding New Files

```bash
# Let system assign number
file-organizer jd assign new-document.pdf

# Output: Assigned 11.04
# Suggested path: 10-19-Administration/11-Company-documents/11.04-new-document.pdf

# Or specify category
file-organizer jd assign new-document.pdf --category 12
```

### Finding Files

```bash
# Find by number
file-organizer jd find 11.04

# Find by keyword
file-organizer jd search "contract"
# Results: 12.01, 12.02, 12.05

# List all in category
file-organizer jd list --category 11
```

### Checking Usage

```bash
# View statistics
file-organizer jd stats ~/Documents-JD

# Output:
# Total items: 156
# Areas in use: 4/10
# Categories in use: 12/40
# Average items per category: 13
# Full categories: 0
# Available slots: 9,844
```

## Customization

### Add Custom Category

```python
from file_organizer.methodologies.johnny_decimal import (
    CategoryDefinition,
    AreaDefinition
)

# Add new category
marketing_area = AreaDefinition(
    area_range_start=40,
    area_range_end=49,
    name="Marketing",
    description="Marketing and communications"
)

social_media = CategoryDefinition(
    area=40,
    category=41,
    name="Social Media",
    description="Social media campaigns and content",
    keywords=["social", "twitter", "facebook", "linkedin"]
)

# Register with system
system.add_category(social_media)
```

### Reserve Number Ranges

```bash
# Reserve range for future use
file-organizer jd reserve 15.00-15.99 --reason "Future expansion"

# List reservations
file-organizer jd reservations

# Clear reservation
file-organizer jd clear-reservation 15
```

## Tips for Success

### DO:
✅ Keep your index updated
✅ Use the system consistently
✅ Document your decisions
✅ Archive old numbers
✅ Keep categories balanced (< 50 items each)

### DON'T:
❌ Skip numbers arbitrarily
❌ Create too many categories
❌ Use category 99 for important files
❌ Forget to update the index
❌ Mix numbered and non-numbered files

## Troubleshooting

**Problem**: Category is full (99 items)

**Solution**:
```bash
# Check what's in the category
file-organizer jd list --category 11

# Archive old items
file-organizer jd archive 11 --older-than 1year

# Or split into two categories
file-organizer jd split-category 11 --into 11,15
```

**Problem**: Number conflict

**Solution**:
```bash
# Find conflicts
file-organizer jd check-conflicts ~/Documents-JD

# Auto-resolve
file-organizer jd resolve-conflicts ~/Documents-JD --strategy increment
```

**Problem**: Wrong category assignment

**Solution**:
```bash
# Move to correct category
file-organizer jd reassign 11.04 --to-category 12

# System will update to 12.XX automatically
```

## Integration with PARA

Combine both systems:

```
1-Projects/
├── 30-39-Active-Projects/
│   ├── 31-Client-Work/
│   │   ├── 31.01-Project-Alpha/
│   │   └── 31.02-Project-Beta/
└── 32-Internal/
    └── 32.01-Website-Redesign/

2-Areas/
└── 20-29-Finance/
    └── 21-Accounting/
        ├── 21.01-Invoices/
        └── 21.02-Reports/
```

Setup:
```bash
# Enable both methodologies
file-organizer organize ~/Documents \
    --methodology para,johnny-decimal \
    --output ~/Documents-Organized
```

## What's Next?

### Automation

```bash
# Auto-assign numbers to new files
file-organizer watch ~/Downloads \
    --methodology johnny-decimal \
    --output ~/Documents-JD \
    --daemon
```

### Learn More

- [Full Johnny Decimal Guide](../johnny-decimal.md)
- [Custom Schemes Guide](johnny-decimal-schemes.md)
- [Advanced Numbering](johnny-decimal-advanced.md)

## Quick Reference

```bash
# Initialize
file-organizer jd init DIR --scheme SCHEME

# Assign number
file-organizer jd assign FILE [--category N]

# Batch assign
file-organizer jd batch-assign DIR

# Find file
file-organizer jd find NUMBER

# Statistics
file-organizer jd stats DIR

# Generate index
file-organizer jd generate-index DIR
```

---

**Time to completion**: ~15 minutes
**System capacity**: 9,900 items (99 categories × 100 items each)
**Maintenance**: Minimal after setup

Start organizing with precision! 🎯
