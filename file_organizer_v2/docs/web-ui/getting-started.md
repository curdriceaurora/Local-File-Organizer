# Getting Started with Web UI

This guide covers the basics of using the File Organizer web interface.

## Accessing the Web Interface

The web UI is served at the `/ui/` path prefix. The API is available at `/api/v1/`
and the interactive API docs are at `/docs` and `/redoc`.

### Local Deployment

If you're running File Organizer locally:

```
http://localhost:8000/ui/
```

### Remote Deployment

If deployed on a remote server:

```
http://your-server-address:8000/ui/
```

Contact your administrator for the correct address.

## Initial Login

### First Time Setup

1. **Open** File Organizer in your browser
1. **Accept** the license agreement
1. **Create** your account (username and password)
1. **Configure** your workspace path
1. **Start** organizing files

### Logging In

Enter your username and password, then click **Login**.

**Forgot password?** Click "Need help?" to reset.

## Dashboard Overview

The dashboard is your home page. It shows:

- **Welcome Message** - Personalized greeting
- **Storage Summary** - Used/available space
- **Quick Stats** - File count, organization status
- **Recent Activity** - Latest operations
- **Quick Actions** - Common tasks

### Quick Actions

Common tasks available from the dashboard:

- **Upload Files** - Add new files
- **Organize Now** - Start organization job
- **Search Files** - Find specific files
- **View Analytics** - See storage breakdown
- **Settings** - Configure preferences

## Main Navigation

### Top Navigation Bar

The header bar includes:

**Logo** (left) - Click to return to dashboard

**Search Bar** (center) - Search from anywhere

**Notifications** (right) - See job status and alerts

**User Menu** (gear icon) - Access settings and logout

### Side Menu (when visible)

Navigate between main sections:

- Dashboard
- Files
- Organize
- Analysis
- Search
- Settings

To toggle the menu, click the **menu icon** (three lines).

## First Task: Upload Files

### Method 1: Click to Upload

1. Click the **Upload Files** button
1. Choose files from your computer
1. Click **Open** to upload
1. Wait for upload to complete

### Method 2: Drag & Drop

1. Drag files from your computer
1. Drop them onto the upload area
1. Files upload automatically
1. See progress in the notification area

### Supported Files

File Organizer accepts 43+ file formats:

**Documents**: PDF, Word, Excel, PowerPoint, Markdown
**Images**: JPEG, PNG, GIF, BMP, TIFF
**Video**: MP4, AVI, MKV, MOV, WMV
**Audio**: MP3, WAV, FLAC, M4A, OGG
**Archives**: ZIP, 7Z, TAR, RAR
**Plus**: Scientific formats, CAD files, and more

### Upload Tips

- **Batch Upload**: Select multiple files at once
- **Drag Multiple**: Drag several files together
- **Large Files**: You can upload up to 500 MB per file
- **Progress**: See progress bar during upload
- **Resume**: Connection drops? Restart the upload

## Second Task: Organize Files

### Basic Organization

1. Click **Organize** in the navigation
1. Select files to organize (or use "Select All")
1. Choose an organization **Methodology**:
   - **PARA**: Projects, Areas, Resources, Archives
   - **Johnny Decimal**: Numbered system
   - **Custom**: Your own rules
1. Review the **Preview** showing where files will go
1. Click **Apply** to organize

### Understanding Methodologies

**PARA** is best for:

- Knowledge workers
- Complex project management
- Flexible organization

**Johnny Decimal** is best for:

- Hierarchical organization
- Fixed categories
- Simple structure

### Reviewing Results

After organization:

1. See the **Results Summary** with:
   - Files organized
   - Files skipped
   - Any errors
1. Click on files to see their new locations
1. Use **Undo** if you want to revert

### Organization Options

Customize how files are organized:

- **Dry Run**: Preview changes without applying
- **Create Folders**: Automatically create categories
- **Preserve Original**: Keep copies of originals
- **Apply Metadata**: Use file metadata for categorization

## Third Task: Find Files

### Quick Search

Use the search bar at the top:

1. Click the **search bar** (or press `/`)
1. Type your search term
1. Results appear as you type
1. Click a result to open it

### Advanced Search

Click **Search** in the navigation for advanced features:

1. Enter your search query
1. Add **Filters**:
   - File type (PDF, image, etc.)
   - Date range
   - File size
   - Location
1. View results with preview
1. Click a file to open or download

### Search Tips

- **Quotes**: "exact phrase" for exact matches
- **Wildcards**: Use * for partial matches
- **Operators**: type:pdf, size:>10mb, date:2024
- **Saved Searches**: Save queries for later use

## Fourth Task: Check Storage Usage

### View Analytics

1. Click **Analysis** in the navigation
1. Select **Storage Usage**
1. See breakdown by:
   - File type
   - Folder
   - Size
1. Click sections to drill down
1. Export report if needed

### Find Duplicates

1. Click **Analysis**
1. Select **Detect Duplicates**
1. Choose folder to scan
1. Wait for analysis to complete
1. Review duplicate groups
1. Mark files to remove or merge

## Settings Basics

### Access Settings

Click the **gear icon** (⚙️) in the top right, then **Settings**.

### Important Settings

**Workspace**

- Change workspace path
- Set default methodology
- Configure file limits

**User Preferences**

- Theme (light/dark)
- Language
- Notification preferences
- Display density

**API Keys**

- Generate API tokens
- Revoke old tokens
- Set expiration dates

**Security**

- Change password
- Enable two-factor authentication
- Manage connected apps

## Understanding Status Icons

Throughout the interface, you'll see icons indicating status:

- ✅ **Green checkmark**: Successful operation
- ⏳ **Hourglass**: Operation in progress
- ⚠️ **Yellow warning**: Needs attention
- ❌ **Red X**: Error or failure
- 🔵 **Blue circle**: Information or pending

## Notifications

### Notification Center

Click the **bell icon** to see all notifications:

- **Job Status**: Organization, analysis progress
- **Alerts**: Warnings or errors
- **Updates**: System updates and maintenance

### Notification Types

- **Success**: Green background
- **Info**: Blue background
- **Warning**: Yellow background
- **Error**: Red background

Click a notification to dismiss or take action.

## Keyboard Shortcuts

Common keyboard shortcuts:

| Shortcut | Action |
|----------|--------|
| `/` | Focus search bar |
| `Ctrl+Z` | Undo last operation |
| `Ctrl+Shift+Z` | Redo last operation |
| `Escape` | Close dialogs |
| `?` | Show help |

## Common Questions

### How do I change my password?

1. Click the gear icon (⚙️)
1. Select "Settings"
1. Click "Security"
1. Enter old password
1. Enter new password twice
1. Click "Update"

### Can I organize files without uploading?

Yes! You can organize files that are already on your server or in a watched folder.

1. Click **Organize**
1. Select **Browse Local Folder**
1. Choose files to organize
1. Proceed as normal

### What if I organize by mistake?

No problem! Click **Undo** to revert the operation. All original files are restored.

### How do I generate an API key?

1. Click the gear icon (⚙️)
1. Select "API Keys"
1. Click "Generate New Key"
1. Copy the token (shown only once!)
1. Use in API requests

## Next Steps

Now that you understand the basics:

- **Upload & Organize**: [File Management Guide](file-management.md)
- **Advanced Organization**: [Organization Guide](organization.md)
- **Search & Analyze**: [Analysis & Search Guide](analysis-search.md)
- **Customize Settings**: [Settings Guide](settings.md)

## Need Help?

- **Documentation**: Click **?** in the top right
- **Troubleshooting**: See [Troubleshooting Guide](../troubleshooting.md)
- **FAQ**: See [FAQ](../faq.md)
- **Report Issue**: [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues)

______________________________________________________________________

**Ready to explore more?** Continue to [File Management Guide](file-management.md)!
