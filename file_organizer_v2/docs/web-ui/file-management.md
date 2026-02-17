# File Management Guide

Learn how to upload, browse, and manage your files in the File Organizer web interface.

## Uploading Files

### Quick Upload

Click the **Upload Files** button on the dashboard or in the Files section.

1. A file browser opens
1. Select one or more files
1. Click **Open** to upload
1. See progress in the notification area

### Drag & Drop Upload

1. Locate the **upload area** (marked with a dashed border)
1. Drag files from your desktop
1. Drop them onto the area
1. Files upload automatically

### Batch Upload

Upload multiple files at once:

- Select multiple files in the file browser (Ctrl+Click or Shift+Click)
- Use Ctrl+A to select all files in a folder
- Drag multiple files at once

### Upload Settings

Configure upload behavior in **Settings → Upload**:

- **Max File Size**: Limit on individual files
- **Max Batch Size**: Total size for batch uploads
- **Auto-Scan**: Automatically scan for duplicates
- **Create Backups**: Keep originals during organization

### Upload Status

Monitor uploads in the **Notifications** area:

- Progress bar shows upload speed
- ETA remaining is displayed
- Pause or cancel any upload
- Retry failed uploads

## Browsing Files

### File Library

Click **Files** to view your file library.

**Features**:

- Thumbnail previews
- Sort by name, date, size, type
- Filter by file type
- Search while browsing
- Select multiple files

### File Preview

Click a file to see details:

- **Thumbnail** preview (for images/documents)
- **File Properties**:
  - Name, size, type
  - Date created/modified
  - Location
  - Metadata
- **Quick Actions**:
  - Download
  - Delete
  - Move
  - Organize
  - Add to collection

### View Modes

Switch between view modes:

**Grid View**

- Large thumbnails
- Quick visual browsing
- Best for images/videos

**List View**

- Detailed information
- Sort columns
- Best for documents

**Compact View**

- Minimal space
- More files visible
- Best for large collections

## File Properties

### Viewing Metadata

Click a file to see detailed properties:

**Basic Info**

- Filename and extension
- File size and format
- Creation and modification dates
- Current location

**Content Analysis** (AI-generated)

- File description
- Category suggestions
- Extracted text/metadata
- Duplicate matches

**File Type Specific**

- Images: Dimensions, EXIF data
- Documents: Page count, language
- Audio: Duration, bitrate
- Video: Resolution, duration, codec

### Editing Properties

Some properties can be edited directly:

1. Click on a property to edit
1. Enter new value
1. Click **Save** or press Enter
1. Changes are saved immediately

**Editable Properties**:

- Custom tags
- Description/notes
- Category
- Priority

## File Collections

Organize files into collections for easy access.

### Creating a Collection

1. Click **Create Collection**
1. Give it a name (e.g., "Project X", "To Review")
1. Optionally add description
1. Click **Create**

### Adding to Collections

**Method 1: File Context Menu**

1. Right-click a file
1. Select "Add to Collection"
1. Choose collection or create new
1. File is added

**Method 2: Drag & Drop**

1. Drag file onto collection
1. File is added automatically

**Method 3: Bulk Add**

1. Select multiple files
1. Click "Add to Collection"
1. Choose collection
1. All selected files added

### Managing Collections

View and manage collections in **Files → Collections**:

- **View Members**: See all files in collection
- **Rename**: Change collection name
- **Delete**: Remove collection (files stay)
- **Export**: Download collection as ZIP
- **Share**: Generate shared link (if enabled)

## Organizing Files

### Quick Organize

Organize individual files:

1. Click the **three dots** menu on a file
1. Select **Organize**
1. Choose destination or methodology
1. Confirm

### Batch Organize

Organize multiple files at once:

1. Select files (Ctrl+Click each)
1. Click **Organize Selected**
1. Choose destination
1. Click **Apply**

### Organization Preview

Before organizing:

1. Select files and methodology
1. Click **Preview**
1. See where files will go
1. Make changes if needed
1. Click **Apply** to organize

## Searching Files

### Quick Search

Use the search bar at the top:

1. Click search box
1. Type search term
1. Results appear as you type
1. Click result to view

### Advanced Search

Access from **Search** section:

- **Query**: Search terms or keywords
- **Filters**:
  - File type
  - Date range
  - Size range
  - Location
  - Tags
- **Sort**: By relevance, date, size, name
- **Results**: View with filters applied

### Search Operators

Use these in search queries:

| Operator | Example | Result |
|----------|---------|--------|
| `type:` | `type:pdf` | PDF files only |
| `size:` | `size:>10mb` | Files larger than 10MB |
| `date:` | `date:2024` | Files from 2024 |
| `path:` | `path:/documents` | In Documents folder |
| `tag:` | `tag:important` | Files with "important" tag |

### Saved Searches

Save searches for frequent use:

1. Create a search
1. Click **Save Search**
1. Give it a name
1. Access from sidebar
1. Saved searches update automatically

## Deleting Files

### Move to Trash

1. Click file's **three dots** menu
1. Select **Delete**
1. File moves to trash
1. Confirm deletion

### Permanent Delete

From trash:

1. Click **Trash** in sidebar
1. View deleted files
1. Right-click file
1. Select **Delete Permanently**
1. Confirm (cannot be undone)

### Bulk Delete

1. Select multiple files
1. Click **Delete**
1. Files move to trash
1. Confirm

### Trash Management

**Empty Trash**:

1. Click **Trash** in sidebar
1. Click **Empty Trash**
1. All files permanently deleted

**Restore**:

1. Click **Trash**
1. Find file
1. Click **Restore**
1. File returns to original location

## Tagging Files

### Adding Tags

1. Select a file
1. In properties panel, click **Tags**
1. Type new tag or select existing
1. Press Enter to add
1. Tags appear on file

### Bulk Tag

Tag multiple files:

1. Select multiple files
1. Click **Add Tags**
1. Enter tag(s)
1. Click **Apply**
1. Tag added to all selected

### Tag Organization

Use tags to:

- Mark files for review
- Categorize by project
- Flag duplicates
- Indicate status

### Searching by Tag

- Click a tag to see all files with it
- Use `tag:` operator in search
- Filter results by tags

## Download & Export

### Downloading Files

1. Click file or select multiple
1. Click **Download**
1. Files downloaded as-is or in ZIP

### Export Collections

Export entire collections:

1. Open collection
1. Click **Export**
1. Choose format:
   - ZIP archive
   - Folder structure
   - Manifest list
1. Download starts

### Batch Export

Export search results:

1. Create search
1. Apply filters
1. Click **Export Results**
1. Files packaged for download

## Duplicate Detection

File Organizer can find similar or identical files.

### Running Duplicate Detection

1. Click **Analysis** → **Duplicates**
1. Choose folder to scan
1. Wait for analysis
1. View duplicate groups

### Understanding Similarity

**Exact Duplicates** (100% match)

- Same file content
- Different names/locations

**Similar** (90%+ match)

- Very similar content
- Small differences

**Possible Duplicates** (80%+ match)

- Similar but with changes

### Managing Duplicates

For each group:

1. **Keep**: Mark which files to keep
1. **Delete**: Remove duplicates
1. **Merge**: Combine into one
1. **Ignore**: Don't delete but remember

## Tips & Best Practices

### Organization

- Use collections for projects
- Tag files consistently
- Create hierarchical folders
- Use naming conventions

### Search

- Use operators for precision
- Save frequent searches
- Use filters to narrow results
- Try different keywords

### Performance

- Batch upload large files
- Close browser tabs when processing
- Enable auto-scan for duplicates
- Export large collections in batches

### Backup

- Keep originals when organizing
- Use collections as backups
- Export important files regularly
- Monitor trash before emptying

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `/` | Focus search |
| `N` | New collection |
| `Ctrl+A` | Select all visible files |
| `Delete` | Delete selected |
| `Ctrl+C` | Copy file path |
| `Ctrl+V` | Paste in upload area |

## Troubleshooting

### Upload Fails

- Check file size limits
- Verify file format is supported
- Try smaller file first
- Check network connection

### Files Not Appearing

- Refresh browser (F5)
- Clear browser cache
- Wait for scan to complete
- Check search filters

### Preview Not Loading

- Try different file format
- Check file corruption
- Reduce preview size
- Try downloading file instead

## Next Steps

- **Organize Files**: [Organization Guide](organization.md)
- **Search & Analyze**: [Analysis & Search Guide](analysis-search.md)
- **Settings**: [Settings Guide](settings.md)

______________________________________________________________________

**Questions?** See [FAQ](../faq.md) or [Troubleshooting](../troubleshooting.md)
