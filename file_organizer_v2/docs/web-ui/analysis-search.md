# Analysis & Search Guide

Learn how to search, filter, and analyze your files in File Organizer.

## Search Basics

### Quick Search

Use the search bar at the top of any page:

1. Click the search box (or press `/`)
1. Type your search query
1. Results appear as you type
1. Click a result to view it

### Search Results

Results show:

- File name and type
- Location
- Size and date
- Match relevance
- Preview (if available)

### Saving Searches

Save searches for later use:

1. Enter search query
1. Click **Save Search**
1. Give it a name
1. Access from **Saved Searches** sidebar
1. Saved searches update automatically

## Advanced Search

Access advanced search from the **Search** section:

### Search Query

Enter search terms using natural language:

```
- "quarterly report"    # Exact phrase
- report AND 2024      # Multiple terms
- report NOT draft     # Exclude terms
- report*              # Wildcard matching
```

### Operators

Use search operators for precision:

| Operator | Example | Result |
|----------|---------|--------|
| `type:` | `type:pdf` | PDF files only |
| `size:` | `size:>10mb` | Larger than 10 MB |
| `date:` | `date:>2024-01` | After Jan 2024 |
| `path:` | `path:/documents` | In Documents folder |
| `tag:` | `tag:important` | Tagged as important |
| `modified:` | `modified:last7days` | Modified in last 7 days |

### Filters

Refine results with filters:

**File Type**

- Document (PDF, Word, etc.)
- Image (JPEG, PNG, etc.)
- Video
- Audio
- Archive
- Other

**Date Range**

- Any time
- Last 24 hours
- Last 7 days
- Last 30 days
- Last year
- Custom range

**File Size**

- All sizes
- < 1 MB (small)
- 1-10 MB (medium)
- 10-100 MB (large)
- > 100 MB (huge)

**Location**

- All locations
- Specific folder
- Multiple folders

**Tags**

- Select specific tags
- Multiple tags
- Exclude tags

### Sorting

Sort results by:

- **Relevance** - Best match first
- **Name** - Alphabetical
- **Date Modified** - Newest first
- **File Size** - Largest first
- **Type** - Group by type

## Analytics

### Storage Usage

View breakdown of disk usage:

**By File Type**

- See which types use most space
- Compare document vs images vs video
- Identify large file categories

**By Folder**

- See folder size breakdown
- Identify large folders
- Navigate to folders

**By Size Range**

- Tiny (< 1 MB)
- Small (1-10 MB)
- Medium (10-100 MB)
- Large (> 100 MB)
- Show largest files

### View Analytics

1. Click **Analysis** → **Storage**
1. See charts and breakdowns
1. Click sections to drill down
1. Export report if needed

### Storage Tips

- Review monthly
- Archive old items
- Delete large unused files
- Clean up duplicates

## Duplicate Detection

Find and manage duplicate files.

### Running Detection

1. Click **Analysis** → **Duplicates**
1. Choose folder(s) to scan
1. Choose detection method:
   - **Exact**: Byte-for-byte match
   - **Smart**: Content-based similarity
   - **All**: Both exact and similar
1. Click **Scan**
1. Wait for analysis to complete

### Understanding Results

**Duplicate Groups**

- Exact duplicates (100% match)
- Similar (90%+ match)
- Possible (80%+ match)

For each group:

- Number of duplicates
- File details (name, size, location)
- Similarity percentage

### Managing Duplicates

For each duplicate group:

**Keep This File**

- Mark which copy to keep
- Other copies deleted

**Delete All But One**

- Quick delete all duplicates
- Keep one copy

**Merge Files**

- Combine into single file
- Keep all content

**Ignore**

- Skip this group
- Don't delete

### Duplicate Best Practices

- **Backup First**: Before deleting duplicates
- **Review**: Check files before deleting
- **Regular Scans**: Find duplicates quarterly
- **Cleanup**: Delete duplicates regularly

## File Analytics

### Individual File Analysis

Click a file to see:

**Content Analysis**

- AI-generated description
- Extracted text/metadata
- Language detection
- Category suggestions

**Properties**

- File type
- Size
- Creation/modification date
- Location

**Related Files**

- Similar files
- Potential duplicates
- Same category

### Batch Analysis

Analyze multiple files:

1. Select multiple files
1. Click **Analyze**
1. See combined statistics:
   - Total size
   - File count by type
   - Average file size
   - Age distribution

## Insights

### Usage Patterns

File Organizer analyzes your file usage:

- Most common file types
- File growth over time
- Organization effectiveness
- Search patterns

### Recommendations

Based on analysis:

- Organize messy folders
- Clean up old files
- Archive completed projects
- Remove duplicates

### Trends

See trends over time:

- File growth
- Organization changes
- Activity levels
- Storage changes

## Exporting Results

### Export Search Results

1. Create search
1. Apply filters
1. Click **Export**
1. Choose format:
   - CSV spreadsheet
   - JSON data
   - ZIP archive (includes files)
1. Download starts

### Export Reports

1. Create report (search, analysis, etc.)
1. Click **Export Report**
1. Choose format:
   - PDF (formatted)
   - CSV (data only)
   - JSON (raw data)
1. Download

### Scheduled Exports

Set up automatic exports:

1. Click **Schedules** → **New Export**
1. Configure:
   - What to export (search, analysis)
   - When to run
   - Export format
   - Destination
1. Exports run automatically

## Search Tips

### Better Search Results

**Tips**:

- Use quotes for exact phrases: `"quarterly report"`
- Use wildcards: `report*` finds report, reports, reporting
- Combine operators: `type:pdf AND size:>5mb`
- Use date ranges: `date:>2024-01-01`

**Examples**:

- Find all PDFs: `type:pdf`
- Find recent documents: `type:document AND date:>7days`
- Find large images: `type:image AND size:>50mb`
- Find by folder: `path:/projects AND tag:active`

### Common Searches

**Recent Files**

```
date:last7days
```

**Large Files to Clean**

```
size:>100mb
```

**Unorganized Files**

```
path:/downloads
```

**Project Files**

```
tag:project-x OR path:/projects/x
```

## Troubleshooting

### Search Not Finding Files

- Check search query syntax
- Verify files aren't excluded
- Try broader search terms
- Refresh browser

### Slow Searches

- Add filters to narrow results
- Use specific operators
- Search in specific folder
- Try exact phrase search

### Duplicate Detection Slow

- Scan smaller folder first
- Check available disk space
- Close other applications
- Try scan at off-peak time

## Next Steps

- [File Management](file-management.md)
- [Organization](organization.md)
- [Settings](settings.md)
