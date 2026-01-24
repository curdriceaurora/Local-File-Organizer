# Phase 3 Migration Guide

## Overview

This guide helps you migrate to Phase 3 features from earlier versions or from manual file organization systems. Covers PARA methodology, Johnny Decimal numbering, and enhanced file format support.

## Table of Contents

- [Upgrading from Phase 2](#upgrading-from-phase-2)
- [Migrating to PARA](#migrating-to-para)
- [Migrating to Johnny Decimal](#migrating-to-johnny-decimal)
- [Combined Migration](#combined-migration)
- [Format Support Migration](#format-support-migration)
- [Data Preservation](#data-preservation)

---

## Upgrading from Phase 2

### Prerequisites

**Backup Your Data**:
```bash
# Create complete backup
cp -r ~/Documents ~/Documents-backup-$(date +%Y%m%d)

# Or use tar
tar -czf documents-backup-$(date +%Y%m%d).tar.gz ~/Documents
```

**Check Current Version**:
```bash
file-organizer --version
# Should show: file-organizer 1.x or 2.x
```

### Installation

**Update Package**:
```bash
# Upgrade to Phase 3
pip install --upgrade file-organizer-v2

# Verify installation
file-organizer --version
# Should show: file-organizer 2.0+
```

**Install Phase 3 Features**:
```bash
# All Phase 3 features
pip install file-organizer-v2[phase3-all]

# Or install selectively:
pip install file-organizer-v2[para]          # PARA methodology
pip install file-organizer-v2[johnny]        # Johnny Decimal
pip install file-organizer-v2[formats]       # Enhanced formats
pip install file-organizer-v2[audio]         # Audio support
pip install file-organizer-v2[video]         # Video support
```

### Configuration Migration

**Migrate Settings**:
```bash
# Automatic migration
file-organizer config migrate --from-version 1.x

# Manual migration
# Copy old config and update
cp ~/.config/file-organizer/config.yaml ~/.config/file-organizer/config-old.yaml
file-organizer config create --defaults phase3
```

**New Phase 3 Settings**:
```yaml
# ~/.config/file-organizer/config.yaml

phase3:
  # PARA Methodology
  para:
    enabled: true
    auto_categorize: true
    confidence_threshold: 0.7
    use_smart_suggestions: true

  # Johnny Decimal System
  johnny_decimal:
    enabled: true
    scheme: business  # or personal, research, creative
    auto_assign: true
    include_numbers_in_names: true

  # Enhanced File Formats
  file_formats:
    epub_enhanced: true
    archive_support: true
    cad_support: true
```

### Database Migration

**Upgrade Database Schema**:
```bash
# Automatic migration
file-organizer db migrate

# Check migration status
file-organizer db status
```

**Preserve History**:
```bash
# Export Phase 2 history
file-organizer history export phase2-history.json

# Import into Phase 3
file-organizer history import phase2-history.json --merge
```

---

## Migrating to PARA

### From Flat Directory Structure

**Before**:
```
~/Documents/
├── project1.pdf
├── work-report.docx
├── recipe.pdf
├── tax-2023.pdf
└── vacation-photos/
```

**After PARA**:
```
~/Documents-PARA/
├── 1-Projects/
│   └── Project1/
│       └── project1.pdf
├── 2-Areas/
│   ├── Finance/
│   │   └── tax-2023.pdf
│   └── Work/
│       └── work-report.docx
├── 3-Resources/
│   ├── Recipes/
│   │   └── recipe.pdf
│   └── Photos/
│       └── vacation-photos/
└── 4-Archive/
```

**Migration Steps**:

1. **Analyze Current Structure**:
```bash
# Preview PARA categorization
file-organizer analyze ~/Documents --methodology para --dry-run

# Output:
# Analyzed 156 files:
# - Projects: 23 files
# - Areas: 45 files
# - Resources: 67 files
# - Archive: 21 files
```

2. **Review Suggestions**:
```bash
# Review low-confidence categorizations
file-organizer analyze ~/Documents --methodology para --show-low-confidence

# Export review list
file-organizer analyze ~/Documents --methodology para --export-csv review.csv
```

3. **Execute Migration**:
```bash
# Migrate to PARA structure
file-organizer migrate ~/Documents ~/Documents-PARA --methodology para

# Progress output:
# Processing [##########] 100% Complete
# ✅ 156 files organized
# - Projects: 23 files
# - Areas: 45 files
# - Resources: 67 files
# - Archive: 21 files
```

4. **Verify Results**:
```bash
# Check structure
tree ~/Documents-PARA -L 2

# Validate organization
file-organizer validate ~/Documents-PARA --methodology para
```

### From Dated Folders

**Before**:
```
~/Documents/
├── 2024-01-Project-Alpha/
├── 2024-02-Budget/
├── 2023-12-Old-Project/
└── Ongoing-Tasks/
```

**Migration Strategy**:
```python
from file_organizer import FileOrganizer
from file_organizer.methodologies.para import PARAConfig

# Configure migration
config = PARAConfig(
    auto_categorize=True,
    use_smart_suggestions=True,
    # Date-based rules
    auto_archive=True,
    archive_after_days=180  # Projects older than 6 months → Archive
)

organizer = FileOrganizer()
organizer.migrate(
    input_path="~/Documents",
    output_path="~/Documents-PARA",
    methodology="para",
    para_config=config
)
```

### From Topic-Based Folders

**Before**:
```
~/Documents/
├── Work/
│   ├── Current/
│   └── Completed/
├── Personal/
└── Reference/
```

**Mapping to PARA**:
```python
# Define custom mapping
category_mapping = {
    "Work/Current": "1-Projects",
    "Work/Completed": "4-Archive",
    "Personal": "2-Areas",
    "Reference": "3-Resources"
}

# Apply mapping
file-organizer migrate ~/Documents ~/Documents-PARA \
    --methodology para \
    --mapping-file category_mapping.json
```

---

## Migrating to Johnny Decimal

### From Flat Structure

**Before**:
```
~/Documents/
├── invoice-jan.pdf
├── invoice-feb.pdf
├── contract-clientA.pdf
├── budget-2024.xlsx
```

**After Johnny Decimal**:
```
~/Documents-JD/
├── 10-19-Administration/
│   └── 12-Contracts/
│       └── 12.01-contract-clientA.pdf
└── 20-29-Finance/
    ├── 21-Accounting/
    │   ├── 21.01-invoice-jan.pdf
    │   └── 21.02-invoice-feb.pdf
    └── 22-Budgets/
        └── 22.01-budget-2024.xlsx
```

**Migration Steps**:

1. **Choose Numbering Scheme**:
```bash
# List available schemes
file-organizer jd list-schemes

# Available:
# - business: For business/company files
# - personal: For personal file management
# - research: For academic/research work
# - creative: For creative projects
```

2. **Generate Scheme from Existing Structure**:
```bash
# Analyze and suggest scheme
file-organizer jd generate-scheme ~/Documents --output custom-scheme.json

# Review and edit
cat custom-scheme.json

# Apply scheme
file-organizer jd init ~/Documents-JD --scheme custom-scheme.json
```

3. **Assign Numbers**:
```bash
# Dry run first
file-organizer jd batch-assign ~/Documents \
    --scheme custom-scheme.json \
    --dry-run

# Review assignments
# Then execute
file-organizer jd batch-assign ~/Documents \
    --scheme custom-scheme.json \
    --output ~/Documents-JD
```

4. **Create Index**:
```bash
# Generate Johnny Decimal index
file-organizer jd generate-index ~/Documents-JD > "00.00 Index.md"

# Place in root directory
mv "00.00 Index.md" ~/Documents-JD/
```

### From Existing Numbering System

If you already use a numbering system (e.g., folders named "01", "02", etc.):

**Before**:
```
~/Documents/
├── 01-Admin/
├── 02-Finance/
├── 03-Projects/
```

**Migration**:
```bash
# Import existing structure
file-organizer jd import-structure ~/Documents --map-to-areas

# Maps:
# 01-Admin → 10-19 Administration
# 02-Finance → 20-29 Finance
# 03-Projects → 30-39 Projects

# Then assign individual file numbers
file-organizer jd batch-assign ~/Documents --preserve-folders
```

### From Topic Folders with Many Files

**Before**:
```
~/Documents/
└── Invoices/
    ├── invoice1.pdf
    ├── invoice2.pdf
    ├── ... (150 files)
```

**Strategy**:
```bash
# Use Johnny Decimal to organize large folders
file-organizer jd organize ~/Documents/Invoices \
    --category 21 \
    --auto-assign \
    --output ~/Documents-JD/20-29-Finance/21-Accounting/

# Result:
# 21.01-invoice1.pdf
# 21.02-invoice2.pdf
# ...
# 21.99-invoice99.pdf
# 22.01-invoice100.pdf (overflows to next category)
```

---

## Combined Migration

### PARA + Johnny Decimal

Combine both methodologies for maximum organization:

**Result**:
```
~/Documents-Organized/
├── 1-Projects/
│   └── 30-39-Active-Projects/
│       ├── 31-Client-Work/
│       │   ├── 31.01-Project-Alpha/
│       │   └── 31.02-Project-Beta/
│       └── 32-Internal/
│           └── 32.01-Website-Redesign/
├── 2-Areas/
│   └── 20-29-Finance/
│       ├── 21-Accounting/
│       │   ├── 21.01-Invoices/
│       │   └── 21.02-Statements/
│       └── 22-Budgets/
│           └── 22.01-Annual-Budget/
├── 3-Resources/
│   └── 70-79-Learning/
│       ├── 71-Courses/
│       └── 72-Books/
└── 4-Archive/
    └── 90-99-Completed/
```

**Migration Command**:
```bash
# Apply both methodologies
file-organizer migrate ~/Documents ~/Documents-Organized \
    --methodology para,johnny-decimal \
    --para-config para-config.yaml \
    --jd-scheme business

# Or with Python API
```python
from file_organizer import FileOrganizer
from file_organizer.methodologies.para import PARAConfig
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalConfig

para_config = PARAConfig(
    enabled=True,
    auto_categorize=True
)

jd_config = JohnnyDecimalConfig(
    enabled=True,
    scheme="business",
    auto_assign=True
)

organizer = FileOrganizer()
organizer.migrate(
    input_path="~/Documents",
    output_path="~/Documents-Organized",
    methodologies=["para", "johnny-decimal"],
    para_config=para_config,
    jd_config=jd_config
)
```

---

## Format Support Migration

### Enhanced EPUB Support

**No migration needed** - Phase 3 automatically uses enhanced EPUB processing.

**Enable Features**:
```yaml
file_formats:
  epub_enhanced: true
  epub_extract_chapters: true
  epub_detect_series: true
  epub_extract_cover: true
```

**Re-organize Existing Books**:
```bash
# Re-analyze with enhanced features
file-organizer re-organize ~/Books --format epub --use-enhanced
```

### Archive File Support

**Before**: Archives ignored or treated as single files.

**After**: Archives analyzed and organized by contents.

**Enable**:
```yaml
file_formats:
  archive_support: true
  analyze_archive_contents: true
```

**Re-process Archives**:
```bash
# Re-analyze existing archives
file-organizer re-organize ~/Downloads/*.zip --analyze-contents
```

---

## Data Preservation

### Preserving Metadata

**File Timestamps**:
```bash
# Preserve original timestamps during migration
file-organizer migrate ~/Documents ~/Documents-PARA \
    --preserve-timestamps
```

**Extended Attributes** (macOS/Linux):
```bash
# Preserve extended attributes (tags, comments)
file-organizer migrate ~/Documents ~/Documents-PARA \
    --preserve-xattrs
```

**File Permissions**:
```bash
# Preserve file permissions
file-organizer migrate ~/Documents ~/Documents-PARA \
    --preserve-permissions
```

### Preserving History

**Export Operation History**:
```bash
# Export history before migration
file-organizer history export ~/Documents-history.json

# After migration, import history with new paths
file-organizer history import ~/Documents-history.json \
    --remap-paths ~/Documents:~/Documents-PARA
```

### Creating Migration Log

```bash
# Log all migration operations
file-organizer migrate ~/Documents ~/Documents-PARA \
    --methodology para \
    --log-file migration-log.txt

# Review log
cat migration-log.txt
```

---

## Rollback Strategy

### Before Migration

**Create Restore Point**:
```bash
# Snapshot before migration
file-organizer snapshot create ~/Documents --name before-phase3

# List snapshots
file-organizer snapshot list

# Restore if needed
file-organizer snapshot restore before-phase3 ~/Documents
```

### After Migration

**Verify Before Deleting Original**:
```bash
# Compare original and migrated
file-organizer compare ~/Documents ~/Documents-PARA

# Check for missing files
file-organizer verify ~/Documents-PARA --against ~/Documents

# Only delete original after verification
rm -rf ~/Documents  # Use with caution!
```

### Incremental Migration

**Migrate in Stages**:
```bash
# Stage 1: Migrate projects only
file-organizer migrate ~/Documents ~/Documents-PARA \
    --filter "projects/*"

# Stage 2: Verify and continue
file-organizer migrate ~/Documents ~/Documents-PARA \
    --filter "work/*" \
    --incremental

# Stage 3: Complete migration
file-organizer migrate ~/Documents ~/Documents-PARA \
    --complete
```

---

## Post-Migration

### Validation

**Validate Structure**:
```bash
# Validate PARA structure
file-organizer validate ~/Documents-PARA --methodology para

# Validate Johnny Decimal numbers
file-organizer jd validate ~/Documents-JD --check-conflicts

# Validate file integrity
file-organizer verify ~/Documents-PARA --check-hashes
```

### Setup Automation

**Watch for New Files**:
```bash
# Auto-organize new files
file-organizer watch ~/Downloads \
    --methodology para,johnny-decimal \
    --output ~/Documents-Organized \
    --daemon
```

**Scheduled Maintenance**:
```bash
# Add to crontab
crontab -e

# Auto-archive old projects weekly
0 0 * * 0 file-organizer archive-old --days 90

# Cleanup and optimize monthly
0 0 1 * * file-organizer maintenance
```

### Update Workflows

**Update Shortcuts**:
```bash
# Update shell aliases
echo 'alias docs="cd ~/Documents-PARA"' >> ~/.bashrc
echo 'alias work="cd ~/Documents-PARA/1-Projects"' >> ~/.bashrc

# Reload
source ~/.bashrc
```

**Update Backup Scripts**:
```bash
# Update backup paths
sed -i 's|~/Documents|~/Documents-PARA|g' backup-script.sh
```

---

## Troubleshooting Migration

### Migration Failed

**Check Logs**:
```bash
# View migration log
tail -f ~/.config/file-organizer/logs/migration.log

# Check for errors
grep ERROR ~/.config/file-organizer/logs/migration.log
```

**Retry Failed Files**:
```bash
# Get list of failed files
file-organizer migration status --show-failures > failed-files.txt

# Retry
file-organizer migrate failed-files.txt ~/Documents-PARA --retry
```

### Partial Migration

**Resume Interrupted Migration**:
```bash
# Check migration progress
file-organizer migration status

# Resume from checkpoint
file-organizer migrate ~/Documents ~/Documents-PARA --resume
```

### Conflicts During Migration

**Resolve Naming Conflicts**:
```bash
# Find conflicts
file-organizer migration check-conflicts ~/Documents-PARA

# Resolve
file-organizer migration resolve-conflicts ~/Documents-PARA \
    --strategy rename  # or skip, overwrite
```

---

## Best Practices

### Before Migration

1. ✅ **Backup everything**
2. ✅ **Test with sample files first**
3. ✅ **Review configuration**
4. ✅ **Check disk space** (migration needs ~2x space temporarily)
5. ✅ **Close other applications** accessing files

### During Migration

1. ✅ **Use dry-run mode first**
2. ✅ **Start with small batches**
3. ✅ **Monitor progress**
4. ✅ **Don't interrupt process**
5. ✅ **Keep logs**

### After Migration

1. ✅ **Validate results**
2. ✅ **Test file access**
3. ✅ **Update shortcuts and scripts**
4. ✅ **Keep original for 30 days**
5. ✅ **Document custom rules**

---

## Migration Checklist

```markdown
## Phase 3 Migration Checklist

### Pre-Migration
- [ ] Backup all data
- [ ] Update to latest version
- [ ] Install Phase 3 dependencies
- [ ] Review configuration
- [ ] Test with sample files
- [ ] Check disk space (need 2x)

### Migration
- [ ] Run dry-run analysis
- [ ] Review categorization results
- [ ] Execute migration
- [ ] Verify file counts match
- [ ] Check for errors in log

### Post-Migration
- [ ] Validate structure
- [ ] Test file access
- [ ] Update shortcuts
- [ ] Setup automation
- [ ] Archive old structure (after 30 days)

### Rollback Plan
- [ ] Have backup ready
- [ ] Know restore procedure
- [ ] Test restore on sample
- [ ] Document issues
```

---

## Getting Help

- **Migration Issues**: https://github.com/your-org/file-organizer-v2/issues/migration
- **Migration Guide**: [Online Documentation](https://docs.file-organizer.io/migration)
- **Community Forums**: https://community.file-organizer.io

---

**Last Updated**: 2026-01-24
**Migration Support**: migration@file-organizer.io
