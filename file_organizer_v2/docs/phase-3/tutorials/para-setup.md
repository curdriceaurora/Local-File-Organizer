# Quick Start: PARA Methodology Setup

This tutorial will guide you through setting up and using the PARA methodology with File Organizer v2 in under 10 minutes.

## Prerequisites

- File Organizer v2 installed
- Basic familiarity with command line
- A directory of files to organize

## Step 1: Enable PARA (2 minutes)

Create a configuration file:

```python
# config.py
from file_organizer.methodologies.para import PARAConfig

config = PARAConfig(
    enabled=True,
    auto_categorize=True,
    confidence_threshold=0.7,
    use_smart_suggestions=True
)

# Save configuration
config.save("~/.config/file-organizer/para.json")
```

Or use CLI:
```bash
file-organizer config set para.enabled true
file-organizer config set para.auto_categorize true
```

## Step 2: Analyze Your Files (2 minutes)

Preview how your files would be categorized:

```bash
file-organizer analyze ~/Downloads --methodology para --dry-run
```

Example output:
```
Analysis Results:
├── Projects: 15 files
│   ├── Q1-Report-Draft.docx (92% confidence)
│   ├── Project-Proposal.pdf (88% confidence)
│   └── ...
├── Areas: 32 files
│   ├── Budget-2024.xlsx (85% confidence)
│   ├── Monthly-Review.docx (78% confidence)
│   └── ...
├── Resources: 47 files
│   ├── Python-Tutorial.pdf (95% confidence)
│   ├── Design-Inspiration.png (89% confidence)
│   └── ...
└── Archive: 8 files
    ├── Old-Project-Final.docx (91% confidence)
    └── ...

Total: 102 files analyzed
Average confidence: 87%
```

## Step 3: Organize Your First Folder (3 minutes)

Start with a small test:

```bash
# Create backup first
cp -r ~/Downloads ~/Downloads-backup

# Organize into PARA structure
file-organizer organize ~/Downloads \
    --methodology para \
    --output ~/Documents-PARA \
    --verbose
```

Watch the magic happen:
```
Processing files...
[1/102] Q1-Report-Draft.docx → 1-Projects/Q1-Marketing/
[2/102] Budget-2024.xlsx → 2-Areas/Finance/
[3/102] Python-Tutorial.pdf → 3-Resources/Learning/
...
✅ Complete! 102 files organized
```

## Step 4: Review Results (2 minutes)

Check your new PARA structure:

```bash
tree ~/Documents-PARA -L 2
```

Output:
```
~/Documents-PARA/
├── 1-Projects/
│   ├── Q1-Marketing/
│   ├── Website-Redesign/
│   └── Client-Deliverables/
├── 2-Areas/
│   ├── Finance/
│   ├── Health/
│   └── Career-Development/
├── 3-Resources/
│   ├── Learning/
│   ├── Design-Inspiration/
│   └── Reference-Materials/
└── 4-Archive/
    └── Completed-2023/
```

## Step 5: Fine-Tune (1 minute)

Review low-confidence categorizations:

```bash
file-organizer review ~/Documents-PARA --confidence-below 0.7
```

Adjust if needed:
```bash
# Move file to correct category
file-organizer move document.pdf --to areas/finance --feedback
```

## What's Next?

### Customize Rules

Create custom categorization rules:

```python
from file_organizer.methodologies.para import PARARule, PARACategory

# Work-specific rule
work_rule = PARARule(
    name="Work Projects",
    category=PARACategory.PROJECTS,
    conditions={
        "keywords": ["client", "deliverable", "deadline"],
        "path_contains": "/work/"
    }
)

config.add_rule(work_rule)
config.save()
```

### Set Up Automation

Auto-organize new files:

```bash
# Watch Downloads folder
file-organizer watch ~/Downloads \
    --methodology para \
    --output ~/Documents-PARA \
    --daemon
```

### Learn More

- [Full PARA Guide](../para-methodology.md)
- [PARA API Reference](../../api/para-api.md)
- [Migration Guide](../migration-guide.md)

## Troubleshooting

**Files in wrong category?**
- Check confidence score
- Add custom rules
- Provide feedback to improve AI

**Too many subcategories?**
- Simplify: Keep hierarchy flat
- Use `--max-depth 2` flag

**Mixed results?**
- Lower confidence threshold: `--confidence-threshold 0.8`
- Enable manual review: `--manual-review`

## Quick Reference

```bash
# Analyze
file-organizer analyze DIR --methodology para --dry-run

# Organize
file-organizer organize DIR --methodology para --output DEST

# Review
file-organizer review DEST --confidence-below 0.7

# Watch
file-organizer watch DIR --methodology para --daemon
```

---

**Time to completion**: ~10 minutes
**Files organized**: Unlimited
**Effort required**: Minimal after setup

Start organizing smarter with PARA! 🚀
