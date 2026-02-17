# Web UI Guide

Welcome to the File Organizer Web Interface! This guide covers all features of the browser-based application for managing, organizing, and analyzing your files.

## Overview

The File Organizer web interface provides a user-friendly, modern way to:

- **Upload & Manage** files with drag-and-drop support
- **Organize** files using PARA, Johnny Decimal, or custom methodologies
- **Search & Filter** with powerful full-text search and faceted navigation
- **Analyze** storage usage and detect duplicate files
- **Monitor** organization jobs in real-time
- **Configure** settings and preferences

## Getting to Know the Interface

### Main Navigation

The web interface has several main sections accessible from the top navigation:

- **Dashboard** - Overview and recent activity
- **Files** - Browse and manage your file library
- **Organize** - Configure and run organization jobs
- **Analysis** - Analyze storage and detect duplicates
- **Search** - Search and filter files
- **Settings** - Configure workspace and user preferences

### Dashboard

The dashboard provides an at-a-glance view of:

- **Storage Summary** - Total space used and available
- **Recent Activity** - Latest file operations
- **Quick Stats** - Number of files, duplicates detected
- **Quick Actions** - Links to organize, search, analyze

### Navigation Bar

The top navigation bar includes:

- **Logo** - Click to return to dashboard
- **Search Bar** - Quick search from anywhere
- **Notifications** - Job status and alerts
- **Settings** - User menu with preferences
- **Help** - Link to documentation

## Browser Support

File Organizer works best on modern browsers:

- **Chrome** 90+ (recommended)
- **Firefox** 88+
- **Safari** 14+
- **Edge** 90+

### Browser Features Required

- JavaScript enabled
- WebSocket support (for real-time updates)
- File drag-and-drop support
- LocalStorage for user preferences

## Getting Started

### 1. Access the Web Interface

Open your browser and navigate to:

```
http://localhost:8000/ui/
```

(Replace `localhost:8000` with your server address if deployed remotely)

### 2. Initial Setup

On first access, you'll see:

1. **Welcome Screen** - Overview and setup instructions
1. **Configuration** - Set workspace path and preferences
1. **Dashboard** - Your home screen

### 3. Upload Your First Files

Click **Upload Files** or drag files into the interface to get started.

## Key Features

### File Management

- Browse file library with thumbnail previews
- View file properties and metadata
- Support for 43+ file formats
- Batch file operations

**Read more**: [File Management Guide](file-management.md)

### Organization

- Choose from multiple methodologies (PARA, Johnny Decimal)
- Preview organization results before applying
- Monitor job progress in real-time
- Undo/redo any operation

**Read more**: [Organization Guide](organization.md)

### Analysis & Insights

- Storage usage breakdown by file type and folder
- Duplicate detection with similarity matching
- Metadata extraction and analysis
- Export analytics data

**Read more**: [Analysis & Search Guide](analysis-search.md)

### Search & Discovery

- Full-text search across file contents
- Faceted search with filters
- Save frequently-used searches
- Export search results

**Read more**: [Analysis & Search Guide](analysis-search.md)

### Configuration

- Customize workspace settings
- Manage user preferences
- Generate API keys
- Configure organization options

**Read more**: [Settings Guide](settings.md)

## Tips & Tricks

### Keyboard Shortcuts

- **/** - Focus search bar
- **Ctrl+Upload** - Upload multiple files
- **Drag & Drop** - Upload or organize files
- **Ctrl+Z** - Undo last operation
- **Ctrl+Shift+Z** - Redo last operation

### Drag & Drop

- Drag files from your computer to upload
- Drag files to create organization rules
- Drag files to move between categories

### Search Operators

Use these in search for precise results:

- `type:pdf` - Find only PDF files
- `size:>10mb` - Find large files
- `date:2024` - Find files from 2024
- `path:/downloads` - Search in specific folder

### Saved Searches

Save frequently-used searches for quick access:

1. Enter search query
1. Click "Save Search"
1. Give it a name
1. Access from sidebar

## Workflows

### Quick Organization

1. Upload files
1. Click **Organize**
1. Select methodology
1. Review preview
1. Click **Apply**

### Duplicate Cleanup

1. Click **Analysis**
1. Select **Detect Duplicates**
1. Choose folder to scan
1. Review results
1. Remove duplicates or merge

### Storage Analysis

1. Click **Analysis**
1. Select **Storage Usage**
1. View breakdown by category
1. Click on sections to drill down
1. Export report

### Backup & Export

1. Click **Search** to find files
1. Select files to export
1. Click **Export**
1. Choose format and location
1. Files are packaged for download

## Real-Time Updates

The web interface uses WebSocket connections for real-time updates:

- Job progress updates appear instantly
- Notifications appear when operations complete
- Search results update as you type
- Storage stats update automatically

## Responsive Design

The interface adapts to different screen sizes:

- **Desktop** (1024px+): Full interface with all features
- **Tablet** (768px-1024px): Optimized layout with collapsible menu
- **Mobile** (< 768px): Mobile-optimized interface

## Performance Tips

### For Better Performance

- Use modern browser (Chrome/Firefox recommended)
- Enable JavaScript and cookies
- Use wired connection for large uploads
- Close unused browser tabs
- Clear browser cache regularly

### For Large File Collections

- Use search/filters instead of browsing
- Organize files in batches
- Monitor job progress
- Reduce upload file sizes

## Accessibility

The web interface includes accessibility features:

- **Keyboard Navigation** - Full keyboard support
- **Screen Readers** - ARIA labels for accessibility
- **High Contrast** - Dark mode support
- **Responsive Text** - Adjustable font sizes

## Session Management

### Login & Logout

- Automatic logout after 30 minutes of inactivity
- "Remember me" option for convenience
- Secure cookie-based sessions

### API Keys

- Generate API keys for programmatic access
- Tokens are secure and revocable
- See [API Reference](../api/index.md) for usage

## Getting Help

### Built-In Help

- **Help Button** (?) in top right opens documentation
- **Tooltips** hover over interface elements
- **Status Messages** explain what's happening

### External Resources

- [Full Documentation](../index.md)
- [Troubleshooting Guide](../troubleshooting.md)
- [FAQ](../faq.md)
- [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues)

## Next Steps

Choose a guide based on what you want to do:

- **Upload & Manage Files**: [File Management Guide](file-management.md)
- **Organize Files**: [Organization Guide](organization.md)
- **Search & Analyze**: [Analysis & Search Guide](analysis-search.md)
- **Customize Settings**: [Settings Guide](settings.md)

---

**Ready to get started?** [Jump to File Management](file-management.md)!
