# Johnny Decimal + PARA Compatibility Guide

## Overview

This guide explains how to combine Johnny Decimal and PARA methodologies for a powerful hybrid organizational system.

## Introduction to PARA

PARA (Projects, Areas, Resources, Archive) is an organizational system that categorizes information based on actionability:

- **Projects**: Short-term efforts with deadlines
- **Areas**: Long-term responsibilities
- **Resources**: Topics of ongoing interest
- **Archive**: Inactive items from other categories

## Why Combine JD and PARA?

Each system has strengths:

**PARA Strengths:**
- Simple, actionability-based categorization
- Clear distinction between active and reference material
- Easy to understand and adopt

**Johnny Decimal Strengths:**
- Precise hierarchical structure
- Scalable to large information collections
- Quick navigation with numbers
- Avoids naming conflicts

**Together:**
- PARA provides high-level organization
- JD provides detailed structure within each PARA category
- Best of both worlds!

## Integration Approaches

### Approach 1: PARA at Top, JD Within

Use PARA categories as top-level organization, with JD numbering inside each:

```
10 Projects/
├─ 10.01 Website Redesign/
├─ 10.02 App Launch/
└─ 10.03 Q1 Campaign/

20 Areas/
├─ 20.01 Health & Fitness/
├─ 20.02 Personal Finance/
└─ 20.03 Career Development/

30 Resources/
├─ 30.01 Design References/
├─ 30.02 Code Snippets/
└─ 30.03 Marketing Templates/

40 Archive/
├─ 40.01 Completed Projects 2024/
└─ 40.02 Old Reference Materials/
```

**Pros:**
- Intuitive top-level structure
- Easy to move items between PARA categories
- Clear separation of active vs. reference

**Cons:**
- Number ranges must be managed carefully
- Moving between PARA categories requires renumbering

### Approach 2: JD Areas Map to PARA

Map JD areas directly to PARA categories:

```
10-19: Projects
20-29: Areas
30-39: Resources
40-49: Archive
```

Structure example:
```
10 Projects - Website Redesign/
11 Projects - App Launch/
12 Projects - Q1 Campaign/

20 Areas - Health & Fitness/
21 Areas - Personal Finance/
22 Areas - Career Development/

30 Resources - Design References/
31 Resources - Code Snippets/
32 Resources - Marketing Templates/

40 Archive - 2024 Completed/
41 Archive - Reference Materials/
```

**Pros:**
- Unified numbering system
- JD benefits throughout
- Easy to see PARA category from number

**Cons:**
- Limits areas within each PARA category
- May feel redundant to include category name

### Approach 3: Hybrid Custom Mapping

Create custom mappings that fit your specific needs:

```
00-09: Admin & System
10-19: Active Projects (PARA: Projects)
20-39: Life Areas (PARA: Areas)
40-59: Work Areas (PARA: Areas)
60-79: Resources (PARA: Resources)
80-89: Reference Archives (PARA: Archive)
90-99: Personal Archives (PARA: Archive)
```

## Implementation Guide

### Setting Up PARA-Compatible JD

```python
from file_organizer.methodologies.johnny_decimal import (
    create_para_compatible_config,
    JohnnyDecimalMigrator,
    PARAJohnnyDecimalBridge,
)

# Create PARA-compatible configuration
config = create_para_compatible_config()

# The configuration maps:
# Projects → Areas 10-19
# Areas → Areas 20-29
# Resources → Areas 30-39
# Archive → Areas 40-49

# Initialize bridge for PARA-JD translation
bridge = PARAJohnnyDecimalBridge(config.compatibility.para_integration)

# Example: Get JD area for a project
projects_area = bridge.para_to_jd_area(PARACategory.PROJECTS, index=0)
# Returns: 10

# Example: Check if area is in PARA range
is_para = bridge.is_para_area(15)
# Returns: True (15 is in Projects range: 10-19)

# Example: Get PARA category from JD area
para_cat = bridge.jd_area_to_para(25)
# Returns: PARACategory.AREAS
```

### Creating Hybrid Structure

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import HybridOrganizer

# Initialize hybrid organizer
organizer = HybridOrganizer(config)

# Create hybrid structure
root = Path("~/Documents")
created_paths = organizer.create_hybrid_structure(root)

# Access created paths
projects_path = created_paths['para_projects']
areas_path = created_paths['para_areas']
```

### Migrating PARA to Hybrid

```python
from file_organizer.methodologies.johnny_decimal import (
    CompatibilityAnalyzer,
    JohnnyDecimalMigrator,
)

# Analyze existing PARA structure
analyzer = CompatibilityAnalyzer(config)
para_detected = analyzer.detect_para_structure(root)

# Get migration recommendations
strategy = analyzer.suggest_migration_strategy(root)
print(strategy['recommendations'])

# Execute migration
migrator = JohnnyDecimalMigrator(scheme=config.scheme)
plan, scan_result = migrator.create_migration_plan(root)
result = migrator.execute_migration(plan, dry_run=False)
```

## Workflow Examples

### Example 1: Adding a New Project

```python
from file_organizer.methodologies.johnny_decimal import (
    HybridOrganizer,
    PARACategory,
    JohnnyDecimalNumber,
    NumberLevel,
)

organizer = HybridOrganizer(config)

# Categorize new project
project_name = "Website Redesign"
jd_number = organizer.categorize_item(project_name, PARACategory.PROJECTS)

# Get full path in hybrid structure
project_path = organizer.get_item_path(
    root,
    PARACategory.PROJECTS,
    jd_number,
    project_name
)

# Create the project folder
project_path.mkdir(parents=True, exist_ok=True)

# Result: ~/Documents/10 Projects/10.01 Website Redesign/
```

### Example 2: Moving Project to Archive

```python
# Original location
project_jd = JohnnyDecimalNumber(
    area=10,
    category=1,
    id_number=None,
    level=NumberLevel.CATEGORY
)

# Get current path
current_path = organizer.get_item_path(
    root,
    PARACategory.PROJECTS,
    project_jd,
    "Website Redesign"
)

# New location in Archive
archive_jd = JohnnyDecimalNumber(
    area=40,  # Archive area
    category=1,
    id_number=None,
    level=NumberLevel.CATEGORY
)

archive_path = organizer.get_item_path(
    root,
    PARACategory.ARCHIVE,
    archive_jd,
    "Website Redesign"
)

# Move the folder
current_path.rename(archive_path)

# Result: Moved from 10 Projects/ to 40 Archive/
```

### Example 3: Organizing Resources by Topic

```python
# Add resources with JD numbers
resources = [
    ("Design References", 1),
    ("Code Snippets", 2),
    ("Marketing Templates", 3),
]

for resource_name, category_num in resources:
    jd_number = JohnnyDecimalNumber(
        area=30,  # Resources area
        category=category_num,
        id_number=None,
        level=NumberLevel.CATEGORY
    )

    path = organizer.get_item_path(
        root,
        PARACategory.RESOURCES,
        jd_number,
        resource_name
    )

    path.mkdir(parents=True, exist_ok=True)

# Result:
# 30 Resources/
#   ├─ 30.01 Design References/
#   ├─ 30.02 Code Snippets/
#   └─ 30.03 Marketing Templates/
```

## Adapters for Seamless Integration

### Using PARA Adapter

```python
from file_organizer.methodologies.johnny_decimal import (
    PARAAdapter,
    OrganizationItem,
)
from pathlib import Path

# Initialize adapter
adapter = PARAAdapter(config)

# Create PARA item
para_item = OrganizationItem(
    name="Website Redesign",
    path=Path("Projects/Website Redesign"),
    category="projects",
    metadata={"subcategory": 1}
)

# Convert to JD
jd_number = adapter.adapt_to_jd(para_item)
print(jd_number.formatted_number)  # Output: "10.01"

# Convert back to PARA
para_item_back = adapter.adapt_from_jd(jd_number, "Website Redesign")
print(para_item_back.category)  # Output: "projects"
```

### Using Adapter Registry

```python
from file_organizer.methodologies.johnny_decimal import (
    create_default_registry,
    OrganizationItem,
)

# Create registry with all adapters
registry = create_default_registry(config)

# Adapt items automatically
item = OrganizationItem(
    name="Q1 Budget",
    path=Path("Areas/Finance/Q1 Budget"),
    category="areas",
    metadata={}
)

# Registry picks the right adapter
jd_number = registry.adapt_to_jd(item)
print(jd_number.formatted_number)  # Output: "20.01"
```

## Best Practices

### Choosing the Right Approach

**Use Approach 1** (PARA at Top) if:
- You're new to both systems
- You frequently move items between PARA categories
- You want familiar PARA structure

**Use Approach 2** (JD Areas as PARA) if:
- You want unified numbering
- You're comfortable with JD system
- You rarely move between PARA categories

**Use Approach 3** (Custom Mapping) if:
- You have specific organizational needs
- You're an advanced user
- You want maximum flexibility

### Managing Number Ranges

**Allocate Wisely:**
```
Projects: 10-19 (10 possible areas)
Areas: 20-29 (10 possible areas)
Resources: 30-39 (10 possible areas)
Archive: 40-49 (10 possible areas)
```

**Expand if Needed:**
```
Projects: 10-19
Areas: 20-39 (20 areas for more life/work separation)
Resources: 40-59 (20 areas for extensive resources)
Archive: 60-79 (20 areas for long-term storage)
```

### Transitioning Between Categories

When moving items between PARA categories:

1. **Decide on new location**: Which PARA category?
2. **Assign new JD number**: Use appropriate area range
3. **Move folder**: Rename with new JD number
4. **Update references**: Fix any links or bookmarks

### Maintaining the Hybrid System

**Weekly Review:**
- Move completed projects to archive
- Update project statuses
- File new resources appropriately

**Monthly Review:**
- Audit PARA categorization
- Consolidate similar items
- Archive old materials

**Quarterly Review:**
- Restructure if needed
- Update numbering scheme
- Optimize organization

## Advanced Topics

### Automated PARA Assignment

```python
from file_organizer.methodologies.johnny_decimal import PARAAdapter

def auto_categorize(item_name, keywords):
    """Automatically determine PARA category from keywords."""
    item_lower = item_name.lower()

    # Check for project indicators
    project_keywords = ['project', 'campaign', 'launch', 'deadline']
    if any(kw in item_lower for kw in project_keywords):
        return "projects"

    # Check for area indicators
    area_keywords = ['health', 'finance', 'career', 'personal']
    if any(kw in item_lower for kw in area_keywords):
        return "areas"

    # Check for resource indicators
    resource_keywords = ['template', 'reference', 'guide', 'tutorial']
    if any(kw in item_lower for kw in resource_keywords):
        return "resources"

    # Default to resources
    return "resources"

# Usage
category = auto_categorize("Website Redesign Project", None)
# Returns: "projects"
```

### Mixed Structure Detection

```python
analyzer = CompatibilityAnalyzer(config)

# Check if structure mixes PARA and JD
is_mixed = analyzer.is_mixed_structure(root)

if is_mixed:
    print("Mixed structure detected!")
    strategy = analyzer.suggest_migration_strategy(root)
    print("Recommendations:")
    for rec in strategy['recommendations']:
        print(f"  - {rec}")
```

### Custom PARA-JD Mappings

```python
from file_organizer.methodologies.johnny_decimal import (
    ConfigBuilder,
    PARAIntegrationConfig,
)

# Custom PARA ranges
config = (
    ConfigBuilder("custom-para")
    .add_area(10, "Projects")
    .add_area(25, "Personal Areas")
    .add_area(45, "Work Areas")
    .add_area(65, "Resources")
    .add_area(85, "Archive")
    .with_para_integration(
        enabled=True,
        projects_area=10,
        areas_area=25,      # Custom mapping
        resources_area=65,  # Custom mapping
        archive_area=85,    # Custom mapping
    )
    .build()
)
```

## Troubleshooting

### Issue: Items in Wrong PARA Category

**Solution**: Use migration tool to reorganize:
```python
# Scan and identify misplaced items
analyzer = CompatibilityAnalyzer(config)
detected = analyzer.detect_para_structure(root)

# Manually review and recategorize
```

### Issue: Running Out of Numbers in PARA Range

**Solution**: Expand the ranges:
```python
config.compatibility.para_integration.projects_area = 10  # 10-19
config.compatibility.para_integration.areas_area = 20     # 20-39 (expanded)
```

### Issue: Confusion Between PARA and JD Numbering

**Solution**: Add clear naming:
```
10 [P] Website Redesign/
20 [A] Personal Finance/
30 [R] Design References/
40 [X] 2024 Archive/
```

## Examples

### Complete Hybrid Setup

```python
from pathlib import Path
from file_organizer.methodologies.johnny_decimal import (
    create_para_compatible_config,
    HybridOrganizer,
    PARACategory,
)

# Setup
root = Path("~/Documents")
config = create_para_compatible_config()
organizer = HybridOrganizer(config)

# Create structure
organizer.create_hybrid_structure(root)

# Add items
items = [
    ("Website Redesign", PARACategory.PROJECTS),
    ("Health Tracking", PARACategory.AREAS),
    ("Code Snippets", PARACategory.RESOURCES),
]

for name, category in items:
    jd_num = organizer.categorize_item(name, category)
    path = organizer.get_item_path(root, category, jd_num, name)
    path.mkdir(parents=True, exist_ok=True)
    print(f"Created: {path}")
```

## Next Steps

- Read the [User Guide](user-guide.md) for JD basics
- Review [Migration Guide](migration.md) for converting existing structures
- Check [API Reference](api-reference.md) for programmatic usage
- See [FAQ](faq.md) for common questions

## Resources

- PARA method: Tiago Forte's "Building a Second Brain"
- Johnny Decimal: [johnnydecimal.com](https://johnnydecimal.com)
- File Organizer docs: [Main documentation](../../README.md)

---

*The best system is the one you'll actually use. Don't overthink it—start simple and iterate!*
