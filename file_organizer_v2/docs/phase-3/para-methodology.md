# PARA Methodology Guide

## Overview

The PARA methodology is a universal organizational system that helps you organize digital information based on actionability. PARA stands for **Projects**, **Areas**, **Resources**, and **Archive** - four distinct categories that represent different levels of engagement with your files and information.

File Organizer v2 provides automatic PARA categorization using AI-powered heuristics to analyze your files and suggest the most appropriate category.

## What is PARA?

### The Four Categories

**Projects** - Short-term efforts with specific goals and deadlines
- Active work with clear end dates
- Examples: "Q1 Marketing Campaign", "Website Redesign", "Conference Presentation"
- Characteristics: Time-bound, goal-oriented, temporary

**Areas** - Long-term responsibilities requiring ongoing attention
- Continuous maintenance without end dates
- Examples: "Finance", "Health", "Professional Development", "Home Management"
- Characteristics: Standards to maintain, indefinite timeline, recurring

**Resources** - Topics of ongoing interest and reference materials
- Information you want to keep for future reference
- Examples: "Recipes", "Design Inspiration", "Programming Tutorials", "Travel Ideas"
- Characteristics: Reference material, learning resources, inspiration

**Archive** - Inactive items from Projects, Areas, or Resources
- Completed projects, outdated resources, old documents
- Examples: "2023 Tax Returns", "Completed Projects", "Old Course Materials"
- Characteristics: No longer active, kept for records, infrequently accessed

## Getting Started

### Quick Start

1. **Enable PARA categorization** in your configuration:
```python
from file_organizer.methodologies.para import PARAConfig

config = PARAConfig(
    auto_categorize=True,
    preserve_user_overrides=True,
    manual_review_threshold=0.6
)
```

2. **Organize your first file**:
```bash
file-organizer organize ~/Downloads/project-plan.pdf --methodology para
```

3. **View categorization results**:
The file will be automatically categorized into one of the four PARA categories based on content analysis.

### Installation

PARA support is built into File Organizer v2. No additional installation required.

## Automatic Categorization

### How It Works

File Organizer uses multiple heuristics to determine the appropriate PARA category:

1. **Temporal Heuristics** - Analyzes time-related indicators
   - Deadlines, dates, timeframes
   - Frequency indicators (daily, weekly, ongoing)
   - Completion markers

2. **Content Heuristics** - Examines file content
   - Goal-oriented language (deliver, complete, finish)
   - Maintenance language (maintain, monitor, track)
   - Reference indicators (guide, tutorial, reference)
   - Archive markers (old, completed, final)

3. **Structural Heuristics** - Looks at file organization
   - Existing folder structure hints
   - File naming patterns
   - Metadata and tags

### Confidence Scoring

Each categorization includes a confidence score:
- **High (>80%)**: Strong indicators, reliable categorization
- **Medium (50-80%)**: Some indicators, may need review
- **Low (<50%)**: Ambiguous, manual review recommended

Example output:
```
File: quarterly-report-draft.docx
Category: Projects (Confidence: 92%)
Reasoning: Contains deadline, goal-oriented language, temporary nature
```

## Creating Custom Rules

### Rule Engine

Define custom rules to override automatic categorization:

```python
from file_organizer.methodologies.para.rules import Rule, RuleCondition, RuleAction
from file_organizer.methodologies.para.rules.engine import ConditionType, ActionType
from file_organizer.methodologies.para import PARACategory

# Rule for work projects
work_rule = Rule(
    name="work-projects",
    description="Categorize work-related project files",
    priority=10,  # Higher priority rules checked first
    conditions=[
        RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["client", "deliverable", "deadline"]),
        RuleCondition(type=ConditionType.FILE_EXTENSION, values=[".docx", ".xlsx", ".pptx"]),
        RuleCondition(type=ConditionType.PATH_CONTAINS, values=["/work/"])
    ],
    actions=[
        RuleAction(type=ActionType.CATEGORIZE, category=PARACategory.PROJECT, confidence=0.9)
    ]
)

# Rule for personal finance (Area)
finance_rule = Rule(
    name="personal-finance",
    description="Categorize recurring finance documents",
    priority=8,
    conditions=[
        RuleCondition(type=ConditionType.CONTENT_KEYWORD, values=["budget", "invoice", "receipt", "tax"]),
        RuleCondition(type=ConditionType.TEMPORAL, metadata={"recurring": True})
    ],
    actions=[
        RuleAction(type=ActionType.CATEGORIZE, category=PARACategory.AREA, confidence=0.85)
    ]
)

# Add rules to config
config.add_rule(work_rule)
config.add_rule(finance_rule)
```

### Rule Priority

Rules are evaluated in priority order (highest first):
- Priority 10: Critical overrides
- Priority 5-9: Custom category rules
- Priority 1-4: Minor adjustments
- Priority 0: Default heuristics

## Smart Suggestions

### Context-Aware Recommendations

File Organizer learns from your organization patterns:

```python
from file_organizer.methodologies.para import PARASuggestionEngine

engine = PARASuggestionEngine()

# Get suggestions for a file
suggestions = engine.suggest(
    file_path="new-document.pdf",
    context={
        "recent_activity": "project planning",
        "current_focus": ["Q2 goals", "team collaboration"]
    }
)

for suggestion in suggestions:
    print(f"{suggestion.category}: {suggestion.reasoning} (Confidence: {suggestion.confidence}%)")
```

### Learning from Feedback

The system improves with use:

```python
# Accept a suggestion
engine.accept_suggestion(file_path, suggested_category)

# Reject and provide correct category
engine.reject_suggestion(
    file_path,
    suggested_category=PARACategory.PROJECTS,
    correct_category=PARACategory.AREAS,
    feedback="This is ongoing maintenance, not a project"
)
```

## Migration from Flat Structure

### Step-by-Step Migration

1. **Analyze existing structure**:
```bash
file-organizer analyze ~/Documents --methodology para --dry-run
```

This scans your files and provides a migration preview.

2. **Review categorization**:
```
Analysis Complete:
- 234 files analyzed
- Projects: 45 files
- Areas: 89 files
- Resources: 76 files
- Archive: 24 files
```

3. **Execute migration**:
```bash
file-organizer migrate ~/Documents --methodology para --target ~/Documents-PARA
```

4. **Verify results**:
```
Migration Complete:
~/Documents-PARA/
├── 1-Projects/
│   ├── Q1-Marketing-Campaign/
│   └── Website-Redesign/
├── 2-Areas/
│   ├── Finance/
│   └── Health/
├── 3-Resources/
│   ├── Design-Inspiration/
│   └── Programming-Tutorials/
└── 4-Archive/
    └── 2023-Tax-Returns/
```

### Handling Edge Cases

**Mixed content folders**:
```python
# Configure behavior for folders with multiple categories
config.mixed_folder_strategy = "split"  # or "dominant", "manual"
```

**Uncertain categorization**:
```python
# Set threshold for manual review
config.manual_review_threshold = 0.6  # Files with confidence < 60% flagged for review
```

## PARA Folder Structure

### Recommended Structure

```
~/Documents/
├── 1-Projects/              # Active projects
│   ├── Q1-Marketing/
│   ├── Website-Redesign/
│   └── Conference-Talk/
├── 2-Areas/                 # Ongoing responsibilities
│   ├── Finance/
│   ├── Health/
│   └── Career/
├── 3-Resources/             # Reference materials
│   ├── Design-Inspiration/
│   ├── Recipes/
│   └── Learning-Materials/
└── 4-Archive/               # Inactive items
    ├── Completed-Projects/
    └── Old-Resources/
```

### Numbering Convention

The 1-2-3-4 prefixes ensure correct sorting and visual hierarchy:
- **1-Projects**: Always first (highest priority)
- **2-Areas**: Second (important but not urgent)
- **3-Resources**: Third (reference material)
- **4-Archive**: Last (lowest priority)

### Sub-organization

Within each category:

**Projects** - Group by status or timeframe:
```
1-Projects/
├── Active/
├── On-Hold/
└── Planning/
```

**Areas** - Group by life domain:
```
2-Areas/
├── Personal/
├── Professional/
└── Creative/
```

**Resources** - Group by topic:
```
3-Resources/
├── Technical/
├── Creative/
└── Reference/
```

## Integration with Existing Workflows

### CLI Usage

```bash
# Organize single file
file-organizer organize document.pdf --methodology para

# Organize directory
file-organizer organize ~/Downloads --methodology para --recursive

# Preview without moving files
file-organizer organize ~/Downloads --methodology para --dry-run

# Use custom rules
file-organizer organize ~/Work --methodology para --rules-file ./para-rules.json
```

### Python API

```python
from file_organizer import FileOrganizer
from file_organizer.methodologies.para import PARAConfig

# Initialize organizer
organizer = FileOrganizer()

# Configure PARA
para_config = PARAConfig(
    enabled=True,
    auto_categorize=True,
    confidence_threshold=0.7
)

# Organize files
result = organizer.organize(
    input_path="~/Downloads",
    output_path="~/Documents-PARA",
    methodology="para",
    config=para_config
)

print(f"Organized {result.files_processed} files")
print(f"Projects: {result.categories['projects']} files")
print(f"Areas: {result.categories['areas']} files")
print(f"Resources: {result.categories['resources']} files")
print(f"Archive: {result.categories['archive']} files")
```

### Batch Processing

```python
from pathlib import Path

# Process multiple directories
directories = [
    Path("~/Documents"),
    Path("~/Downloads"),
    Path("~/Desktop")
]

for directory in directories:
    result = organizer.organize(
        input_path=directory,
        methodology="para",
        incremental=True  # Only process new files
    )
```

## Tips for Effective PARA Organization

### Best Practices

1. **Review regularly**: Move completed projects to Archive monthly
2. **Keep it simple**: Don't over-subdivide categories
3. **Trust the process**: Let the system learn from your patterns
4. **Be consistent**: Use the same naming conventions
5. **Archive liberally**: Don't keep active what's inactive

### Common Patterns

**Time-based archiving**:
```python
# Automatically archive old projects
config.auto_archive = True
config.archive_after_days = 90  # Archive projects inactive for 90 days
```

**Seasonal organization**:
```
1-Projects/
├── 2024-Q1/
├── 2024-Q2/
└── Current/
```

**Hybrid approach**:
Combine PARA with other systems (e.g., Johnny Decimal for sub-organization)

## Common Pitfalls

### Avoid These Mistakes

❌ **Too many subcategories**
- Don't create Projects/Work/Client-A/Project-X/Phase-1/...
- Keep hierarchy flat: Projects/Client-A-Project-X/

❌ **Mixing categories**
- Don't put Resources in Projects folder
- Trust the automatic categorization

❌ **Never archiving**
- Regular archiving keeps your system clean
- Set up automatic archiving rules

❌ **Ignoring context**
- Same file name in different contexts = different categories
- Use content analysis, not just filenames

✅ **Do this instead**:
- Keep categories distinct and clear
- Archive completed projects promptly
- Let the AI handle categorization
- Review and adjust rules as needed

## Troubleshooting

### File Categorized Incorrectly

**Problem**: File placed in wrong category

**Solutions**:
1. Check confidence score - low confidence needs manual review
2. Add custom rule for this file type
3. Provide feedback to improve AI:
```python
organizer.provide_feedback(
    file_path="document.pdf",
    suggested_category=PARACategory.PROJECTS,
    correct_category=PARACategory.AREAS,
    reason="This is ongoing maintenance"
)
```

### Can't Decide Between Categories

**Problem**: Unclear if file is Project or Area

**Rule of thumb**:
- Has deadline or completion criteria? → **Project**
- Ongoing without end date? → **Area**
- Just for reference? → **Resource**
- No longer active? → **Archive**

### Migration Issues

**Problem**: Existing structure doesn't fit PARA

**Solutions**:
1. Use `--mixed-folder-strategy split` to separate mixed folders
2. Set `--confidence-threshold 0.8` for stricter categorization
3. Enable `--manual-review` for ambiguous files

## Advanced Usage

### Custom Heuristics

Define your own categorization logic:

```python
from file_organizer.methodologies.para.detection import CustomHeuristic

class ProjectDeadlineHeuristic(CustomHeuristic):
    """Categorize files with deadlines as Projects."""

    def evaluate(self, file_content, metadata):
        deadline_keywords = ["due date", "deadline", "by", "deliver"]

        for keyword in deadline_keywords:
            if keyword in file_content.lower():
                return {
                    "category": PARACategory.PROJECTS,
                    "confidence": 0.9,
                    "reasoning": f"Found deadline indicator: {keyword}"
                }

        return None  # Let other heuristics decide

# Register custom heuristic
config.add_heuristic(ProjectDeadlineHeuristic())
```

### Integration with Other Systems

**Combine with Johnny Decimal**:
```
1-Projects/
├── 10-19-Active-Projects/
│   ├── 11.01-Website-Redesign/
│   └── 12.01-Q1-Marketing/
└── 20-29-Planning/
    └── 21.01-Q2-Goals/
```

**Sync with Cloud Storage**:
```python
# Automatically sync PARA structure to cloud
from file_organizer.integrations import CloudSync

sync = CloudSync(provider="dropbox")
sync.sync_structure(
    local_path="~/Documents-PARA",
    remote_path="/PARA",
    methodology="para"
)
```

## Related Features

- [Johnny Decimal System](johnny-decimal.md) - Combine with PARA for deeper organization
- [Smart Suggestions](../api/smart-suggestions-api.md) - AI-powered categorization
- [File Organization API](../api/organization-api.md) - Programmatic access

## Further Reading

- [PARA Official Documentation](https://fortelabs.com/blog/para/)
- [Building a Second Brain](https://www.buildingasecondbrain.com/)
- [PARA Implementation Examples](tutorials/para-setup.md)

---

**Next Steps**: Try organizing your first directory with PARA using the [Quick Start Tutorial](tutorials/para-setup.md)
