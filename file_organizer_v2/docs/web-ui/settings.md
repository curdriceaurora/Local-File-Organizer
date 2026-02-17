# Settings & Configuration Guide

Customize File Organizer to fit your workflow.

## Accessing Settings

Click the **gear icon** (⚙️) in the top right corner, then select **Settings**.

## Workspace Settings

### Workspace Path

Configure where File Organizer stores its data:

1. Click **Workspace** → **Path**
1. Choose workspace location
1. Ensure sufficient disk space (10+ GB recommended)
1. Click **Save**

**Note**: Changing workspace requires restart

### Workspace Name

Give your workspace a custom name:

1. Click **Workspace** → **Name**
1. Enter workspace name
1. Click **Save**

Uses: Shown in web interface title and API responses

## User Preferences

### Theme

Choose light or dark theme:

1. Click **Appearance** → **Theme**
1. Select:
   - Light mode
   - Dark mode
   - Auto (follows system)
1. Changes apply immediately

### Language

Select interface language:

1. Click **Appearance** → **Language**
1. Choose from:
   - English
   - Spanish
   - French
   - German
   - Japanese
   - (More coming soon)
1. Interface updates immediately

### Display Density

Adjust interface spacing:

1. Click **Appearance** → **Density**
1. Choose:
   - Compact (more content visible)
   - Normal (default)
   - Spacious (easier to read)
1. Updates immediately

### Font Size

Adjust text size:

1. Click **Appearance** → **Font Size**
1. Choose from slider
1. Updates immediately

## Notifications

### Notification Preferences

Control what notifications you receive:

1. Click **Notifications**
1. Toggle notification types:
   - Job completion
   - Errors and warnings
   - System updates
   - Tips and suggestions
1. Click **Save**

### Desktop Notifications

Enable browser desktop notifications:

1. Click **Notifications** → **Desktop**
1. Grant permission when prompted
1. Notifications appear even when tab inactive

### Notification Sound

Enable/disable notification sounds:

1. Click **Notifications** → **Sound**
1. Toggle on/off
1. Test sound button available

## API Configuration

### Generating API Keys

Create API tokens for programmatic access:

1. Click **API Keys**
1. Click **Generate New Key**
1. Configure:
   - **Name**: Identify the key
   - **Expiration**: When key expires
   - **Permissions**: What can be accessed
1. Key is shown once - copy immediately
1. Click **Done**

### Managing API Keys

View and manage your API keys:

**For Each Key**:

- Name and creation date
- Expiration date
- Last used date
- Copy token
- **Revoke**: Delete immediately
- **Regenerate**: Reset with new token

### API Key Permissions

Control what each API key can do:

- **Read Files**: List and view files
- **Write Files**: Upload and modify files
- **Organize**: Start organization jobs
- **Analyze**: Run analysis and search
- **Delete**: Remove files
- **Admin**: Full access (dangerous!)

## Organization Settings

### Default Methodology

Set default organization method:

1. Click **Organization** → **Default**
1. Choose:
   - PARA
   - Johnny Decimal
   - Custom
   - None
1. Click **Save**

### Methodology Options

Configure methodology-specific settings:

**PARA**

- Default folder structure
- Auto-create subfolders

**Johnny Decimal**

- Starting number range
- Subfolder naming
- Archiving rules

**Custom**

- Save custom rules
- Import/export rules
- Create rule templates

### Organization Behavior

Control how organization works:

1. Click **Organization** → **Behavior**
1. Configure:
   - **Dry Run**: Always preview first
   - **Preserve Originals**: Keep copies
   - **Create Folders**: Auto-create structure
   - **Auto-Backup**: Backup before organizing
1. Click **Save**

## File Upload Settings

### Upload Limits

Configure file upload restrictions:

1. Click **Upload** → **Limits**
1. Set:
   - Max file size (per file)
   - Max batch size (total)
   - Supported file types
1. Click **Save**

### Auto-Scan

Enable automatic duplicate detection:

1. Click **Upload** → **Auto-Scan**
1. Toggle **Enable Auto-Scan**
1. Configure:
   - Scan after upload
   - Similarity threshold
1. Click **Save**

### Backup Settings

Configure file backups:

1. Click **Upload** → **Backups**
1. Configure:
   - Keep backups before organizing
   - Backup retention (days)
   - Backup location
1. Click **Save**

## Security Settings

### Change Password

Update your account password:

1. Click **Security** → **Password**
1. Enter current password
1. Enter new password (twice)
1. Click **Change Password**

**Password Requirements**:

- At least 8 characters
- Mix of upper and lowercase
- At least one number
- At least one special character

### Two-Factor Authentication

Enable additional security:

1. Click **Security** → **2FA**
1. Choose method:
   - Authenticator app (Google Authenticator, Authy, etc.)
   - SMS (if configured)
1. Follow setup wizard
1. Save backup codes (securely!)

### Sessions

View and manage active sessions:

1. Click **Security** → **Sessions**
1. See all active sessions:
   - Browser type
   - IP address
   - Last activity
1. Click **Logout** to end session
1. **Logout All** to sign out everywhere

### Login History

Review recent login activity:

1. Click **Security** → **Login History**
1. See:
   - Date and time
   - IP address
   - Browser and OS
   - Success/failure

## Privacy Settings

### Data Collection

Control what data is collected:

1. Click **Privacy** → **Data Collection**
1. Toggle options:
   - Usage analytics
   - Error reporting
   - Feature suggestions
   - No personal data is collected

### Cookies

Manage browser cookies:

1. Click **Privacy** → **Cookies**
1. See what cookies are used:
   - Session management
   - User preferences
   - Analytics
1. Clear cookies if desired

### Third-Party Services

View integrations:

1. Click **Privacy** → **Integrations**
1. No third-party integrations by default
1. Enable if connecting external services

## Storage Settings

### View Storage

See storage usage breakdown:

1. Click **Storage** → **Usage**
1. See:
   - Total capacity
   - Used space
   - Available space
   - Breakdown by category

### Clean Up Storage

Free up disk space:

1. Click **Storage** → **Cleanup**
1. Options:
   - Delete old backups
   - Clear caches
   - Archive old files
   - Remove duplicates
1. Preview what will be deleted
1. Click **Cleanup**

### Storage Alerts

Get notified when storage runs low:

1. Click **Storage** → **Alerts**
1. Configure:
   - Alert at % full (e.g., 80%)
   - Notification method
1. Click **Save**

## Advanced Settings

### System Information

View system details:

1. Click **Advanced** → **System**
1. See:
   - Python version
   - Ollama version
   - Database info
   - Available RAM/CPU

### Import/Export

Backup and restore settings:

**Export Settings**

1. Click **Advanced** → **Import/Export**
1. Click **Export Settings**
1. JSON file downloads

**Import Settings**

1. Click **Import Settings**
1. Choose JSON file
1. Settings are restored

### Logs

Access application logs:

1. Click **Advanced** → **Logs**
1. Filter by level:
   - Debug
   - Info
   - Warning
   - Error
1. View recent logs
1. Download logs file

### Reset to Defaults

Reset all settings:

1. Click **Advanced** → **Reset**
1. Choose what to reset:
   - All settings
   - Workspace only
   - User preferences
1. **WARNING**: This cannot be undone
1. Click **Reset**

## Mobile Settings

### Responsive Mode

The web interface adapts to mobile:

1. Settings accessible on mobile
1. Same functionality as desktop
1. Touch-optimized interface
1. Reduced features on very small screens

### Offline Mode

Some features work offline:

- View cached files
- Read previous searches
- Check settings (read-only)
- No uploads/organization offline

## Shortcuts

Quick keyboard shortcuts in settings:

| Shortcut | Action |
|----------|--------|
| `/` | Focus search in settings |
| `Ctrl+S` | Save current setting |
| `Escape` | Close dialog |

## Troubleshooting Settings

### Settings Not Saving

- Check for validation errors
- Ensure sufficient disk space
- Try browser refresh
- Check browser cookies enabled

### API Key Not Working

- Verify key is copied correctly
- Check key hasn't expired
- Ensure key has required permissions
- Regenerate key if needed

### 2FA Not Working

- Verify time sync on device
- Check backup codes
- Try different authenticator app
- Contact administrator

## Backup Settings

Export all settings before major changes:

1. Click **Advanced** → **Export Settings**
1. Save JSON file
1. Keep in secure location
1. Can restore if needed

## Next Steps

- [File Management](file-management.md)
- [Organization](organization.md)
- [Analysis & Search](analysis-search.md)
