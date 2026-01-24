# Johnny Decimal FAQ

## General Questions

### What is Johnny Decimal?

Johnny Decimal is a decimal-based numbering system for organizing files and folders hierarchically. It uses three levels:
- **Areas (10-99)**: Broad categories
- **Categories (XX.XX)**: Specific topics within areas
- **IDs (XX.XX.XXX)**: Individual items within categories

### Why use Johnny Decimal?

**Benefits:**
- Fast navigation with unique numbers
- Scalable to large collections
- Prevents naming conflicts
- Easy to reference items
- Works across platforms
- Human-readable structure

### How is this different from just using folders?

Johnny Decimal adds:
- **Consistent structure**: Same patterns everywhere
- **Unique identifiers**: Easy to reference
- **Number-based navigation**: Faster than clicking through folders
- **Scalability**: Grows without chaos
- **Metadata-free**: Structure is self-explanatory

### Is Johnny Decimal right for me?

Good fit if you:
- ✅ Manage many files/folders (100+)
- ✅ Need quick reference system
- ✅ Want consistent organization
- ✅ Like structured approaches
- ✅ Share files with others

Maybe not if you:
- ❌ Have very few files (<20 folders)
- ❌ Prefer tag-based systems
- ❌ Don't like numbers
- ❌ Need extreme flexibility

## Getting Started

### How do I start using Johnny Decimal?

1. **Plan**: List your main categories (areas)
2. **Assign**: Give each area a base number (10, 20, 30...)
3. **Structure**: Create categories within each area
4. **Migrate**: Use the migration tool or start fresh
5. **Maintain**: Keep structure consistent

See [User Guide](user-guide.md) for detailed instructions.

### Should I migrate existing files or start fresh?

**Start Fresh** if:
- You have relatively few files
- Current organization is chaotic
- You want a clean slate

**Migrate** if:
- You have many files
- Current organization has some structure
- You can't afford downtime

Use the [Migration Tool](migration.md) for automated migration.

### How long does migration take?

Depends on scale:
- **100 folders**: 15-30 minutes
- **500 folders**: 1-2 hours
- **1000+ folders**: 2-4 hours

Includes planning, preview, and execution.

### What if I mess up during migration?

The migrator includes:
- **Automatic backups**: Created before execution
- **Dry-run mode**: Preview changes first
- **Rollback support**: Undo if needed
- **Validation**: Catch issues before execution

See [Migration Guide](migration.md) for safety features.

## Numbering System

### Why start at 10, not 01?

Areas start at 10 to:
- Reserve 00-09 for system/admin use
- Make numbers easier to say ("ten" vs "oh-one")
- Follow original Johnny Decimal convention
- Leave room for future extensions

### What if I run out of numbers?

You have:
- **90 areas** (10-99)
- **99 categories per area** (01-99)
- **999 IDs per category** (001-999)

That's **8,910,990** possible items. If you hit limits:
- Review if you're over-categorizing
- Consolidate similar categories
- Archive old items
- Use sub-categories instead of new areas

### Can I skip numbers?

Yes! Leaving gaps is recommended:
- Allows future expansion
- Groups related items
- Makes structure clearer

Example:
```
10-19: Personal
20-29: Work
30-39: (reserved for future)
40-49: Archive
```

### Can I use 00-09 for areas?

Not recommended. Those are reserved for:
- System folders
- Admin/meta information
- Special purposes

But File Organizer doesn't enforce this if you really need it.

### Do I have to use all three levels?

No! Use what you need:
- **Areas only**: Good for simple structures
- **Areas + Categories**: Most common
- **All three levels**: For complex hierarchies

## Organization Strategies

### How do I decide on areas?

Ask yourself:
1. What are my main domains of information?
2. What are my major responsibilities?
3. How do I naturally think about my work?

Common approaches:
- **By department**: Finance, Marketing, Operations
- **By role**: Projects, Areas, Resources, Archive (PARA)
- **By lifecycle**: Planning, Execution, Archive
- **By topic**: Personal, Work, Hobbies

### Should I keep original folder names?

Recommended: **Yes**
```
10 Finance
11.01 Annual Budgets
11.01.001 Budget 2024
```

Alternative: **Numbers only**
```
10
11.01
11.01.001
```

Original names are more user-friendly.

### How do I handle shared folders?

Options:
1. **Duplicate**: Copy to multiple areas
2. **Reference**: Keep original, link from others
3. **Choose one**: File in primary location
4. **Special area**: Create "00-09 Shared" area

Choose based on how often items are shared.

### How do I organize by date?

**Option 1**: Date in ID level
```
11.01.001 Budget 2024-Q1
11.01.002 Budget 2024-Q2
```

**Option 2**: Date as category
```
11 Budgets
11.24 Budget 2024
11.25 Budget 2025
```

**Option 3**: Chronological IDs
```
11.01.001 Latest Budget (rotate periodically)
```

Choose based on access patterns.

## PARA Integration

### Can I use Johnny Decimal with PARA?

Yes! See [PARA Compatibility Guide](para-compatibility.md).

**Option 1**: PARA at top level
```
10 Projects/
20 Areas/
30 Resources/
40 Archive/
```

**Option 2**: Map areas to PARA
```
10-19: Projects
20-29: Areas
30-39: Resources
40-49: Archive
```

### How do I move items between PARA categories?

When moving from Projects to Archive:

1. Decide new JD number in Archive range
2. Rename folder with new number
3. Update any references/links
4. Document the move

File Organizer provides tools to help with this.

### Which is better: PARA or Johnny Decimal?

Neither! They serve different purposes:

**PARA**: Actionability-based categorization
**Johnny Decimal**: Hierarchical structure with numbers

Best approach: Use both together!
- PARA for high-level organization
- JD for detailed structure within each

## Technical Questions

### Does it work on Windows/Mac/Linux?

Yes! Johnny Decimal is just a naming convention, so it works on all platforms.

File Organizer v2.0 supports:
- ✅ macOS
- ✅ Linux
- ✅ Windows
- ✅ Cloud storage (Dropbox, Google Drive, OneDrive)

### What about special characters in names?

Recommended naming:
```
10 Finance
11.01 Annual Budgets
```

Avoid:
- ❌ Slashes: /\
- ❌ Colons: :
- ❌ Pipes: |
- ❌ Quotes: "
- ❌ Asterisks: *
- ❌ Question marks: ?

These cause issues on some platforms.

### Can I use Johnny Decimal with Git?

Yes! Johnny Decimal works great with Git:
- Structure is version-controlled
- Numbers make references stable
- Easy to reference in commits
- Works across branches

Example commit:
```
feat: Add budget template to 11.01.003
```

### Does it work with cloud storage?

Yes! Works perfectly with:
- Dropbox
- Google Drive
- OneDrive
- iCloud Drive
- Box
- Any file sync service

Numbers make syncing easier (no conflicts from renames).

## Migration & Maintenance

### How do I handle migration errors?

1. **Check validation report** before executing
2. **Run dry-run first** to preview changes
3. **Review backup location** before real execution
4. **Fix issues manually** if automatic rollback fails

See [Migration Guide](migration.md) for troubleshooting.

### Can I undo a migration?

Yes! Use the rollback feature:

```python
success = migrator.rollback()
```

Or restore from automatic backup created during migration.

### How do I maintain the system over time?

**Daily**: File new items correctly
**Weekly**: Review uncategorized items
**Monthly**: Audit category assignments
**Quarterly**: Review area structure
**Annually**: Archive old content

### What if my structure changes?

Johnny Decimal is flexible:
- Add new areas as needed
- Create new categories
- Consolidate old categories
- Migrate items to new numbers

The system grows with your needs.

## Advanced Topics

### Can I use custom number ranges?

Yes! Use ConfigBuilder:

```python
config = (
    ConfigBuilder("custom")
    .add_area(10, "Personal")
    .add_area(50, "Work")  # Skip to 50
    .build()
)
```

### How do I handle very deep hierarchies?

File Organizer automatically flattens deep structures:
- Level 1 → Area
- Level 2 → Category
- Level 3+ → ID (consolidated)

Or manually restructure to be flatter.

### Can I integrate with other systems?

Yes! File Organizer provides adapters for:
- PARA methodology
- Generic filesystems
- Custom methodologies (extend MethodologyAdapter)

See [API Reference](api-reference.md) for details.

### How do I automate organization?

Use the API:

```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalSystem

system = JohnnyDecimalSystem()

# Automate structure creation
for area_num, area_name in areas:
    system.create_area(area_num, area_name)
```

See [API Reference](api-reference.md) for full automation options.

## Best Practices

### What are common mistakes?

❌ **Over-categorizing**: Too many areas/categories
- Fix: Consolidate related items

❌ **Inconsistent naming**: Mixed formats
- Fix: Stick to one naming pattern

❌ **Not leaving gaps**: Sequential numbers
- Fix: Leave room for growth

❌ **Wrong level**: Using IDs when categories suffice
- Fix: Review hierarchy needs

❌ **No documentation**: Forgetting what numbers mean
- Fix: Maintain a master index

### How detailed should I be?

Start simple, add detail as needed:

**Phase 1**: Areas only
```
10 Finance
20 Marketing
30 Operations
```

**Phase 2**: Add categories
```
10 Finance
  11 Budgets
  12 Invoices
```

**Phase 3**: Add IDs if needed
```
11 Budgets
  11.01 Annual
  11.02 Quarterly
```

### How do I handle one-off items?

**Option 1**: Create "Miscellaneous" category
```
19 Finance - Misc
29 Marketing - Misc
```

**Option 2**: File in closest related category

**Option 3**: Create new category if item grows

### Should I document my system?

Yes! Create a master index:
```
Johnny Decimal Index

10-19: Finance
  11: Budgets
    11.01: Annual Budgets
    11.02: Quarterly Budgets
  12: Invoices
    12.01: Client Invoices
    12.02: Vendor Invoices

20-29: Marketing
  21: Campaigns
  22: Materials
```

Keep this index updated as structure evolves.

## Getting Help

### Where can I learn more?

- **Original system**: [johnnydecimal.com](https://johnnydecimal.com)
- **User Guide**: [user-guide.md](user-guide.md)
- **Migration Guide**: [migration.md](migration.md)
- **API Reference**: [api-reference.md](api-reference.md)
- **PARA Guide**: [para-compatibility.md](para-compatibility.md)

### How do I report bugs?

Open an issue on GitHub with:
- Description of the problem
- Steps to reproduce
- Expected vs. actual behavior
- Error messages (if any)
- Your configuration

### Can I contribute?

Yes! Contributions welcome:
- Bug fixes
- Documentation improvements
- New features
- Examples and tutorials
- Adapters for other methodologies

See project README for contribution guidelines.

### Is there a community?

Check:
- GitHub Discussions
- Project Discord/Slack (if available)
- Original Johnny Decimal forum at johnnydecimal.com

## Quick Reference

### Essential Concepts

- **Area (10-99)**: Broad category
- **Category (XX.XX)**: Specific topic within area
- **ID (XX.XX.XXX)**: Individual item within category

### Essential Commands

```python
# Create system
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalSystem
system = JohnnyDecimalSystem()

# Migrate existing
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalMigrator
migrator = JohnnyDecimalMigrator()

# PARA integration
from file_organizer.methodologies.johnny_decimal import create_para_compatible_config
config = create_para_compatible_config()
```

### Essential Resources

- User Guide: [user-guide.md](user-guide.md)
- Migration: [migration.md](migration.md)
- API Docs: [api-reference.md](api-reference.md)
- PARA: [para-compatibility.md](para-compatibility.md)

---

**Still have questions? Open an issue on GitHub or consult the documentation!**
