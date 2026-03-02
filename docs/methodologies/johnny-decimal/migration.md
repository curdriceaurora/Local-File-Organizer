# Johnny Decimal Migration Guide

## Overview

This guide walks you through migrating your existing folder structure to the Johnny Decimal system using File Organizer v2.0's automated migration tools.

## Before You Begin

### Prerequisites

1. **Python 3.12+** installed
2. **File Organizer v2.0** installed
3. **Backup** of your files (migration tool creates backups, but better safe than sorry)
4. **Time** to plan your structure (30-60 minutes)
5. **Review permissions** on folders you want to migrate

### Understanding the Migration Process

The migration workflow consists of four stages:

1. **Scan**: Analyze existing structure and detect patterns
2. **Transform**: Create transformation plan with JD number assignments
3. **Validate**: Check for conflicts and issues
4. **Execute**: Apply transformations (with rollback support)

## Step-by-Step Migration

### Step 1: Scan Your Current Structure

First, analyze your existing folder structure:

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import FolderScanner

# Initialize scanner
scanner = FolderScanner()

# Scan your directory
root_path = Path("/path/to/your/folders")
scan_result = scanner.scan_directory(root_path)

# Review scan results
print(f"Total folders: {scan_result.total_folders}")
print(f"Total files: {scan_result.total_files}")
print(f"Max depth: {scan_result.max_depth}")
print(f"Detected patterns: {scan_result.detected_patterns}")
```

**Scan Output Example:**

```text
Total folders: 45
Total files: 1,234
Max depth: 4
Detected patterns: ['PARA methodology detected', 'Deep hierarchical structure']
```

### Step 2: Configure Your Migration

Create a configuration that matches your needs:

```python
from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalConfig,
    ConfigBuilder,
)

# Option A: Default configuration
config = create_default_config()

# Option B: Custom configuration
config = (
    ConfigBuilder("my-system")
    .add_area(10, "Personal", "Personal documents and records")
    .add_area(20, "Work", "Work-related files")
    .add_area(30, "Projects", "Active projects")
    .add_area(40, "Archive", "Completed items")
    .with_migration_config(
        preserve_names=True,  # Keep original folder names
        create_backups=True,  # Create backups before migration
        max_depth=10          # Maximum depth to scan
    )
    .build()
)

# Option C: PARA-compatible configuration
from file_organizer.methodologies.johnny_decimal import create_para_compatible_config
config = create_para_compatible_config()
```

### Step 3: Create Migration Plan

Generate a detailed migration plan:

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalMigrator

# Initialize migrator with configuration
migrator = JohnnyDecimalMigrator(
    scheme=config.scheme,
    preserve_original_names=True
)

# Create migration plan
plan, scan_result = migrator.create_migration_plan(root_path)

# Review plan statistics
print(f"Total transformations: {len(plan.rules)}")
print(f"Conflicts: {len(plan.conflicts)}")
print(f"Warnings: {len(plan.warnings)}")
```

### Step 4: Preview Migration

Before executing, preview what will change:

```python
# Generate human-readable preview
preview = migrator.generate_preview(plan, scan_result)
print(preview)
```

**Preview Example:**

```markdown
# Johnny Decimal Migration Preview

## Source Analysis
- Root: /Users/username/Documents
- Total folders: 45
- Total files: 1,234
- Max depth: 4

## Detected Patterns
- PARA methodology detected
- Deep hierarchical structure

## Migration Plan
- Total transformations: 45
- Conflicts: 0
- Warnings: 2

## Sample Transformations (first 10)
- Projects → 10 Projects
- Projects/Website → 10.01 Website
- Projects/App Development → 10.02 App Development
- Areas → 20 Areas
- Areas/Health → 20.01 Health
- Areas/Finance → 20.02 Finance
...
```

### Step 5: Validate Plan

Check for issues before execution:

```python
# Validate transformation plan
validation = migrator.validate_plan(plan)

if validation.is_valid:
    print("✅ Plan is valid and ready for execution")
else:
    print("❌ Plan has errors that must be fixed:")
    report = migrator.validator.generate_report(validation)
    print(report)
```

**Validation Report Example:**

```markdown
# Transformation Plan Validation Report

✅ **Plan is VALID** - Ready for execution

- Errors: 0
- Warnings: 2
- Info: 5

## Warnings (Should Review)
- **Rule 12**: Target path already exists: /path/to/folder
  💡 May need to merge or rename existing folder
- **Rule 15**: Nested transformation: Documents is under another transformed folder
  💡 Ensure parent folder is transformed first
```

### Step 6: Execute Migration (Dry Run)

Always do a dry run first:

```python
# Execute in dry-run mode (no actual changes)
result = migrator.execute_migration(
    plan,
    dry_run=True,
    create_backup=True
)

# Review dry-run results
print(f"Would transform: {result.transformed_count} folders")
print(f"Would fail: {result.failed_count} folders")
print(f"Would skip: {result.skipped_count} folders")
```

### Step 7: Execute Migration (For Real)

If dry run looks good, execute the migration:

```python
# Execute actual migration
result = migrator.execute_migration(
    plan,
    dry_run=False,
    create_backup=True  # Always create backups!
)

# Check results
if result.success:
    print(f"✅ Migration successful!")
    print(f"Transformed: {result.transformed_count} folders")
    print(f"Backup location: {result.backup_path}")
else:
    print(f"❌ Migration had issues:")
    print(f"Failed: {result.failed_count} folders")
    for path, error in result.failed_paths:
        print(f"  - {path}: {error}")
```

### Step 8: Verify and Test

After migration:

1. **Verify structure**: Navigate your folders to ensure everything looks correct
2. **Check files**: Spot-check that files are in the right places
3. **Test access**: Make sure you can still access all your files
4. **Update bookmarks**: Update any saved paths or bookmarks

## Migration Strategies

### Strategy 1: Incremental Migration

Migrate one area at a time:

```python
# Migrate just one top-level folder
subfolder_path = root_path / "Projects"
plan, scan_result = migrator.create_migration_plan(subfolder_path)

# Execute migration for this folder only
result = migrator.execute_migration(plan, dry_run=False)

# Repeat for other folders
```

### Strategy 2: PARA to Johnny Decimal

If you're using PARA, use the compatibility layer:

```python
from file_organizer.methodologies.johnny_decimal import (
    create_para_compatible_config,
    PARAJohnnyDecimalBridge,
)

# Use PARA-compatible configuration
config = create_para_compatible_config()

# Initialize migrator
migrator = JohnnyDecimalMigrator(
    scheme=config.scheme,
    preserve_original_names=True
)

# Create and execute plan
plan, scan_result = migrator.create_migration_plan(root_path)
result = migrator.execute_migration(plan, dry_run=False)
```

### Strategy 3: Custom Mappings

Define custom folder-to-area mappings:

```python
config = (
    ConfigBuilder("custom")
    .add_area(10, "Finance")
    .add_area(20, "Health")
    .add_area(30, "Work")
    .add_custom_mapping("money", 10)        # "money" → Area 10
    .add_custom_mapping("medical", 20)       # "medical" → Area 20
    .add_custom_mapping("career", 30)        # "career" → Area 30
    .build()
)

migrator = JohnnyDecimalMigrator(scheme=config.scheme)
```

## Handling Special Cases

### Deeply Nested Structures

If you have folders nested more than 3 levels:

```python
# The migrator automatically flattens deep structures
# Level 1 → Area (XX)
# Level 2 → Category (XX.XX)
# Level 3+ → ID (XX.XX.XXX)

# Deep structure:
# Projects/Web/ClientA/Site/Pages/Home
# Becomes:
# 10.01.001 ClientA (with contents consolidated)
```

### Large Folder Hierarchies

For very large structures (hundreds of folders):

```python
# Use max_depth to limit scanning
scanner = FolderScanner(max_depth=5)

# Process in batches
batch_size = 50
for i in range(0, len(plan.rules), batch_size):
    batch_rules = plan.rules[i:i+batch_size]
    # Process batch...
```

### Mixed Content

If folders contain both files and subfolders:

```python
# Files are preserved in their parent folders
# Only folders are renamed with JD numbers
# Example:
# Projects/
#   ├─ document.pdf        (stays here)
#   └─ Website/           (becomes 10.01 Website)
#       └─ files...
```

## Rollback and Recovery

### Automatic Rollback

If something goes wrong, use the rollback feature:

```python
# Rollback latest migration
success = migrator.rollback()

if success:
    print("✅ Rollback successful")
else:
    print("❌ Rollback failed - check backup")
```

### Manual Recovery

If automatic rollback fails:

1. **Locate backup**: Check `result.backup_path` from execution
2. **Restore manually**: Copy files from backup to original location
3. **Review logs**: Check what failed and why

### Rollback Information

```python
# View rollback history
for info in migrator._rollback_history:
    print(f"Migration ID: {info.migration_id}")
    print(f"Timestamp: {info.timestamp}")
    print(f"Backup: {info.backup_path}")
    print(f"Changes: {len(info.original_structure)} folders")
```

## Best Practices

### Before Migration

- ✅ **Back up your data** (even though tool creates backups)
- ✅ **Close applications** using the folders
- ✅ **Test on a copy** first if possible
- ✅ **Plan your structure** before running migration
- ✅ **Document your scheme** for future reference

### During Migration

- ✅ **Always dry-run first**
- ✅ **Review validation warnings**
- ✅ **Monitor progress** for large migrations
- ✅ **Keep backups enabled**
- ✅ **Don't interrupt** the migration process

### After Migration

- ✅ **Verify structure** manually
- ✅ **Update bookmarks** and shortcuts
- ✅ **Test access** to important files
- ✅ **Keep backups** for a while
- ✅ **Document changes** for team members

## Troubleshooting

### Issue: Migration Fails with Permission Error

**Solution**:

```python
# Check folder permissions
import os
os.access(root_path, os.W_OK)  # Should return True

# Run with elevated permissions if needed (macOS/Linux)
# sudo python migration_script.py
```

### Issue: Conflicts Detected

**Solution**:

```python
# Review conflicts in validation
validation = migrator.validate_plan(plan)

# Fix conflicts manually before migration
for issue in validation.errors:
    print(f"Error: {issue.message}")
    print(f"Suggestion: {issue.suggestion}")
```

### Issue: Dry Run Shows Unexpected Changes

**Solution**:

- Review the transformation plan carefully
- Adjust your numbering scheme if needed
- Use custom mappings for specific folders
- Consider incremental migration

### Issue: Backup Takes Too Much Space

**Solution**:

```python
# Disable backups (only if you have external backup)
result = migrator.execute_migration(
    plan,
    dry_run=False,
    create_backup=False  # Use with caution!
)
```

### Issue: Some Folders Skipped

**Solution**:

```python
# Check skipped paths
for path in result.skipped_paths:
    print(f"Skipped: {path}")
    # Manually review why they were skipped
    # Usually due to target already existing
```

## Examples

### Example 1: Simple Migration

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalMigrator

# Simple migration with defaults
migrator = JohnnyDecimalMigrator()
root = Path("~/Documents").expanduser()

# One-liner: scan, plan, execute
plan, scan = migrator.create_migration_plan(root)
result = migrator.execute_migration(plan, dry_run=False)

print(f"Done! Transformed {result.transformed_count} folders")
```

### Example 2: PARA Migration

```python
from file_organizer.methodologies.johnny_decimal import (
    create_para_compatible_config,
    JohnnyDecimalMigrator,
)

# PARA-compatible migration
config = create_para_compatible_config()
migrator = JohnnyDecimalMigrator(scheme=config.scheme)

root = Path("~/PARA")
plan, scan = migrator.create_migration_plan(root)

# Preview before executing
preview = migrator.generate_preview(plan, scan)
print(preview)

# Execute
result = migrator.execute_migration(plan, dry_run=False)
```

### Example 3: Custom Structure with Validation

```python
from file_organizer.methodologies.johnny_decimal import (
    ConfigBuilder,
    JohnnyDecimalMigrator,
)

# Custom configuration
config = (
    ConfigBuilder("work-docs")
    .add_area(10, "Clients")
    .add_area(20, "Internal")
    .add_area(30, "Marketing")
    .add_custom_mapping("client", 10)
    .add_custom_mapping("hr", 20)
    .build()
)

migrator = JohnnyDecimalMigrator(scheme=config.scheme)

root = Path("~/Work")
plan, scan = migrator.create_migration_plan(root)

# Validate thoroughly
validation = migrator.validate_plan(plan)
if not validation.is_valid:
    print("Fix these errors first:")
    print(migrator.validator.generate_report(validation))
    exit(1)

# Execute with confidence
result = migrator.execute_migration(plan, dry_run=False)
```

## Next Steps

- Review the [User Guide](user-guide.md) for daily usage
- Check [PARA Compatibility](para-compatibility.md) for hybrid setups
- See [API Reference](api-reference.md) for programmatic access
- Read the [FAQ](faq.md) for common questions

---

*Remember: Migration is a tool to help you organize, not a one-time event. You can always adjust and refine your structure as your needs evolve.*
