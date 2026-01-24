# Johnny Decimal User Guide

## Introduction

Welcome to the Johnny Decimal methodology in File Organizer v2.0. This guide will help you understand and implement the Johnny Decimal system for organizing your files and folders.

## What is Johnny Decimal?

Johnny Decimal is a decimal-based numbering system that provides a structured, scalable way to organize information. It uses a three-level hierarchy:

- **Areas (10-99)**: Broad categories for grouping related items
- **Categories (XX.XX)**: Specific topics within an area
- **IDs (XX.XX.XXX)**: Individual items within a category

### Example Structure

```
10-19 Finance/
  ├─ 11 Budgets/
  │   ├─ 11.01 Annual Budgets/
  │   │   ├─ 11.01.001 Budget 2024/
  │   │   └─ 11.01.002 Budget 2025/
  │   └─ 11.02 Quarterly Budgets/
  └─ 12 Invoices/
      └─ 12.01 Client Invoices/
```

## Key Concepts

### 1. Areas (10-99)

Areas are the highest level of organization. They represent major domains of your information.

**Guidelines:**
- Use numbers 10-99 (90 possible areas)
- Group related categories together
- Leave gaps for future expansion
- Keep area definitions stable over time

**Example Areas:**
- 10-19: Finance
- 20-29: Marketing
- 30-39: Operations
- 40-49: Human Resources

### 2. Categories (XX.XX)

Categories subdivide areas into specific topics.

**Guidelines:**
- First two digits match the parent area
- Second two digits range from 01-99
- Each area can have up to 99 categories
- Use descriptive names

**Example Categories in Finance (10-19):**
- 11.01: Annual Budgets
- 11.02: Quarterly Budgets
- 12.01: Client Invoices
- 12.02: Vendor Invoices

### 3. IDs (XX.XX.XXX)

IDs are the most granular level, representing individual items.

**Guidelines:**
- Inherit area and category numbers
- Final three digits range from 001-999
- Use for individual files or sub-folders
- Chronological or logical ordering

**Example IDs:**
- 11.01.001: Budget 2024
- 11.01.002: Budget 2025
- 12.01.001: Client A Invoice

## Getting Started

### Step 1: Plan Your Areas

Identify the major categories of information you manage:

1. List all your current top-level folders
2. Group similar items together
3. Define 5-10 broad areas
4. Assign each a base number (10, 20, 30, etc.)

### Step 2: Define Categories

For each area, identify subcategories:

1. List the types of items in each area
2. Group related items into categories
3. Assign numbers within the area range
4. Document category purposes

### Step 3: Apply the System

#### Option A: Fresh Start

Create a new organized structure:

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalSystem

system = JohnnyDecimalSystem()

# Create area
area = system.create_area(10, "Finance")

# Create category
category = system.create_category(10, 1, "Budgets")

# Create ID
id_number = system.create_id(10, 1, 1, "Budget 2024")
```

#### Option B: Migrate Existing Structure

Use the migration tool to convert your current organization:

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalMigrator

migrator = JohnnyDecimalMigrator()

# Create migration plan
plan, scan_result = migrator.create_migration_plan(root_path)

# Preview changes
preview = migrator.generate_preview(plan, scan_result)
print(preview)

# Execute migration (dry run first!)
result = migrator.execute_migration(plan, dry_run=True)
```

See [Migration Guide](migration.md) for detailed migration instructions.

## Best Practices

### Naming Conventions

**With Original Names (Recommended):**
```
10 Finance/
├─ 11.01 Annual Budgets/
└─ 11.02 Quarterly Budgets/
```

**Numbers Only (Advanced):**
```
10/
├─ 11.01/
└─ 11.02/
```

### Organization Tips

1. **Keep it Simple**: Start with fewer areas and expand as needed
2. **Be Consistent**: Use the same structure across all areas
3. **Document Your System**: Maintain a master index of your numbering scheme
4. **Review Regularly**: Adjust categories as your needs change
5. **Don't Overthink**: You can always refactor later

### Common Patterns

#### By Department
```
10-19 Executive
20-29 Finance
30-39 Marketing
40-49 Sales
50-59 Operations
```

#### By Project Phase
```
10-19 Planning
20-29 Design
30-39 Development
40-49 Testing
50-59 Deployment
```

#### By Content Type
```
10-19 Documents
20-29 Spreadsheets
30-39 Presentations
40-49 Media
50-59 Archives
```

## Working with Johnny Decimal

### Finding Items

With Johnny Decimal, finding files becomes intuitive:

1. **Know the area**: What domain does this belong to?
2. **Know the category**: What specific topic?
3. **Know the ID**: Which specific item?

Example: Looking for the 2024 budget?
- Area 10: Finance
- Category 11.01: Annual Budgets
- ID 11.01.001: Budget 2024

Path: `10 Finance/11.01 Annual Budgets/11.01.001 Budget 2024`

### Adding New Items

When adding new content:

1. Determine the appropriate area
2. Find or create a matching category
3. Assign the next available ID
4. Create the folder/file with JD number + name

### Maintaining the System

#### Regular Maintenance

- **Weekly**: Ensure new files are properly categorized
- **Monthly**: Review category assignments
- **Quarterly**: Audit area structure
- **Annually**: Consider archiving old content

#### Handling Growth

When categories fill up:
- Create sub-categories using the ID level
- Restructure the category if needed
- Archive old items to free up space

When areas fill up:
- Review area definitions
- Consider consolidating similar areas
- Expand into unused number ranges

## Integration with PARA

Johnny Decimal can work alongside PARA methodology. See [PARA Compatibility Guide](para-compatibility.md) for details.

**Hybrid Structure:**
```
10 Projects/
├─ 10.01 Active Projects/
└─ 10.02 On Hold Projects/
20 Areas/
├─ 20.01 Health/
└─ 20.02 Finance/
30 Resources/
└─ 30.01 References/
40 Archive/
└─ 40.01 Completed Projects/
```

## Advanced Features

### Custom Numbering Schemes

Define your own area and category mappings:

```python
from file_organizer.methodologies.johnny_decimal import (
    ConfigBuilder, AreaDefinition, CategoryDefinition
)

config = (
    ConfigBuilder("my-scheme")
    .add_area(10, "Finance", "Financial documents and records")
    .add_category(10, 1, "Budgets", "Annual and quarterly budgets")
    .add_category(10, 2, "Invoices", "Client and vendor invoices")
    .build()
)
```

### Automated Migration

The migration engine can automatically:
- Scan your existing structure
- Detect organizational patterns
- Suggest JD number assignments
- Preview changes before execution
- Create backups
- Support rollback

### Validation and Safety

Before any migration:
- Plans are validated for conflicts
- Warnings are generated for potential issues
- Dry-run mode lets you preview changes
- Backups are automatically created
- Rollback information is preserved

## Troubleshooting

### Problem: Too Many Categories

**Solution**: Consider whether some categories could be IDs instead, or consolidate related categories.

### Problem: Can't Decide on Area Boundaries

**Solution**: Start with broader areas and refine over time. It's okay to restructure as you learn.

### Problem: Running Out of Numbers

**Solution**:
- Areas: You have 90 possible areas (10-99)
- Categories: 99 per area
- IDs: 999 per category

This is rarely a real constraint. If you hit it, consider whether you're over-categorizing.

### Problem: Migration Conflicts

**Solution**: Use the validator to identify issues before execution:

```python
validation = migrator.validate_plan(plan)
if not validation.is_valid:
    print(migrator.validator.generate_report(validation))
```

## Next Steps

- Read the [Migration Guide](migration.md) to convert your existing files
- Check out [PARA Compatibility](para-compatibility.md) if you use PARA
- Review the [API Reference](api-reference.md) for programmatic usage
- Browse the [FAQ](faq.md) for common questions

## Resources

- Original system: [johnnydecimal.com](https://johnnydecimal.com)
- File Organizer documentation: [Main docs](../../README.md)
- Community examples: [Examples](examples/)

## Support

For issues or questions:
- Check the [FAQ](faq.md)
- Review [examples](examples/)
- Open an issue on GitHub
- Consult the API documentation

---

*Remember: Johnny Decimal is a tool, not a rule. Adapt it to your needs and iterate as you learn what works best for you.*
