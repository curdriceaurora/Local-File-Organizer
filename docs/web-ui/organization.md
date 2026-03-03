# Organization Guide

Master the file organization workflows in File Organizer.

## Understanding Organization

### What is Organization?

File organization is the process of:

1. Analyzing files
1. Categorizing them based on content
1. Moving/renaming them into a structured hierarchy
1. Applying consistent naming conventions

### Organization Methodologies

File Organizer supports multiple systems:

## PARA Methodology

**P**rojects, **A**reas, **R**esources, **A**rchives - A flexible system for knowledge workers.

### PARA Structure

```text
PARA/
├── Projects/           # Active projects with deadlines
│   ├── Website Redesign/
│   ├── Research Paper/
│   └── Product Launch/
├── Areas/              # Ongoing responsibilities
│   ├── Health/
│   ├── Finance/
│   └── Career/
├── Resources/          # Reference materials
│   ├── Templates/
│   ├── Tools/
│   └── Articles/
└── Archives/           # Completed items
    ├── 2023 Projects/
    └── Old Areas/
```

### PARA Organization Steps

1. Click **Organize** → **PARA**
1. Select files
1. Choose which category they fit:
   - **Projects**: Time-bound initiatives
   - **Areas**: Ongoing areas of life
   - **Resources**: Reference material
   - **Archives**: Completed/inactive
1. AI analyzes content and suggests categories
1. Review and confirm
1. Click **Apply**

### PARA Best Practices

- Review projects quarterly
- Archive completed items
- Keep resources organized by type
- Use consistent folder structure
- Combine with tags for flexibility

## Johnny Decimal System

**JD** is a hierarchical, numbered system. Perfect for structured organization.

### Johnny Decimal Structure

```text
JD/
├── 10-19 Career/
│   ├── 11 CV & Applications/
│   ├── 12 Job Offers/
│   └── 13 Training & Development/
├── 20-29 Finance/
│   ├── 21 Taxes/
│   ├── 22 Invoices/
│   └── 23 Bank Statements/
├── 30-39 Health/
│   ├── 31 Medical Records/
│   ├── 32 Prescriptions/
│   └── 33 Fitness/
└── 40-49 Personal/
    ├── 41 Travel/
    ├── 42 Family/
    └── 43 Hobbies/
```

### Johnny Decimal Organization Steps

1. Click **Organize** → **Johnny Decimal**
1. Select files
1. Choose category (10-99)
1. Choose subcategory
1. Enter decimal number
1. Review organization
1. Click **Apply**

### Johnny Decimal Rules

- **X0-X9**: 10 main categories
- **X0-X9**: 10 subcategories each
- **X.XX**: File numbering within subcategory
- **Max 10 items** per level
- **Simple, clear structure**

### Johnny Decimal Best Practices

- Plan categories before starting
- Keep similar items together
- Use consistent naming
- Don't skip numbers
- Review structure regularly

## Custom Methodologies

Create your own organization system.

### Creating Custom Rules

1. Click **Organize** → **Custom**
1. Click **Create New Rule**
1. Define rule:
   - **Name**: Rule identifier
   - **Condition**: What files match (e.g., type:pdf)
   - **Action**: Where to put them
1. Add more rules
1. Test with **Preview**
1. Apply when ready

### Rule Conditions

Match files by:

- **File Type**: pdf, image, video, etc.
- **File Size**: >10mb, \<1mb, etc.
- **Extension**: .pdf, .docx, etc.
- **Date**: Recent (last month, etc.)
- **Name**: Pattern matching
- **Content**: Keywords in file

### Rule Actions

Actions for matched files:

- **Move to Folder**: Specific path
- **Rename**: Pattern-based renaming
- **Tag**: Add tags automatically
- **Copy**: Keep original + copy
- **Archive**: Move to archive folder

### Example Custom Rules

**Rule 1: PDF Documents**

- Condition: `type:pdf`
- Action: Move to `Documents/PDFs/`

**Rule 2: Recent Photos**

- Condition: `type:image AND date:>30days`
- Action: Move to `Photos/Recent/`

**Rule 3: Large Files**

- Condition: `size:>100mb`
- Action: Move to `Archive/Large Files/`

## Organization Workflow

### Step 1: Select Files

1. Navigate to **Organize**
1. Click **Select Files**
1. Choose:
   - **Specific Files**: Click individual files
   - **Folder**: Select entire folder
   - **Search Results**: Organize search results
1. See count of selected files

### Step 2: Choose Methodology

1. Select methodology:
   - PARA
   - Johnny Decimal
   - Custom
   - None (undo previous)
1. Configure options:
   - Dry run (preview only)
   - Preserve originals
   - Create folders
   - Apply metadata

### Step 3: Review Preview

1. See preview showing:
   - Current location of each file
   - Proposed new location
   - Metadata changes
1. **Issues** appear if any:
   - Invalid paths
   - Permission problems
   - Naming conflicts
1. Fix issues if needed

### Step 4: Apply Organization

1. Review looks good
1. Click **Apply**
1. Progress bar shows organization status
1. See results when complete:
   - Files organized
   - Files skipped (and why)
   - Any errors

## Organization Options

### Dry Run (Preview Only)

See what would happen without actually organizing:

1. Enable **Dry Run**
1. Complete organization workflow
1. See preview and results
1. No files are moved
1. Run again with **Dry Run** off to apply

### Preserve Originals

Keep original files while organizing:

1. Enable **Preserve Originals**
1. Files are copied (not moved)
1. Originals remain in source folder
1. Useful as backup

### Create Folders

Automatically create folder structure:

1. Enable **Create Folders**
1. Non-existent folders are created
1. Avoids "file not found" errors
1. Useful for new methodologies

### Apply Metadata

Extract and apply file metadata:

1. Enable **Apply Metadata**
1. AI extracts information
1. Creates metadata files
1. Updates file properties

## Monitoring Organization

### Job Progress

During organization:

1. Progress bar shows % complete
1. Current file being organized
1. Estimated time remaining
1. Speed (files/second)

### Pause & Resume

1. Click **Pause** to stop
1. Work resumes where it left off
1. Click **Resume** to continue
1. Or click **Cancel** to stop entirely

### Job History

View past organization jobs:

1. Click **History**
1. See all past organization jobs
1. Job details:
   - Date/time started
   - Files organized
   - Methodology used
   - Duration
1. Click job to see details

## Undoing Organization

### Immediate Undo

If you organize by mistake:

1. Click **Undo** (or Ctrl+Z)
1. Last operation is reversed
1. All files return to original locations
1. Original names restored

### Undo Limitations

- Can only undo recent operations
- Undo history limited to ~20 operations
- Cannot undo after server restart
- For older changes, restore from backup

### Reverting Organization

To revert all organization:

1. Click **Organize**
1. Choose **Original Structure**
1. Select organized files
1. Click **Apply**
1. Files return to original structure

## Scheduling Organization

Automatically organize files on a schedule.

### Creating Schedule

1. Click **Organize** → **Schedule**
1. Create new schedule:
   - **Name**: Schedule name
   - **Folder**: Watch this folder
   - **Methodology**: Use this method
   - **Frequency**: Daily/Weekly/Monthly
   - **Time**: When to run
1. Click **Create**

### Managing Schedules

1. View active schedules
1. Pause/resume schedule
1. Edit schedule settings
1. See schedule results
1. Delete when no longer needed

### Schedule History

View scheduled organization results:

1. Click **Schedule** → **History**
1. See all past runs
1. Details for each run:
   - Date/time
   - Files organized
   - Success/failures
1. Export results if needed

## Best Practices

### Before Organizing

- **Backup**: Make backup of important files
- **Review**: Check files for duplicates
- **Plan**: Decide on methodology first
- **Test**: Use dry-run on small sample first

### During Organization

- **Monitor**: Watch progress
- **Avoid Edits**: Don't modify files while organizing
- **Keep Power**: Ensure system stays on
- **Good Connection**: Stable network if remote

### After Organization

- **Verify**: Check organized files
- **Update**: Update any shortcuts/links
- **Share**: Let users know new locations
- **Document**: Record organization decisions

## Troubleshooting

### Files Not Organizing

- Check file permissions
- Ensure destination folder exists
- Verify methodology settings
- Try dry-run to see issues

### Duplicates Found

- Review duplicates before organizing
- Use duplicate detection to clean up
- Decide which to keep
- Then organize

### Slow Performance

- Organize in smaller batches
- Close other applications
- Use wired connection if possible
- Check available disk space

## Next Steps

- [File Management](file-management.md)
- [Analysis & Search](analysis-search.md)
- [Settings](settings.md)
