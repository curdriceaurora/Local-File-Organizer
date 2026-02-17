# Settings & Configuration Guide

Customize File Organizer to fit your workflow.

## Accessing Settings

Click the **gear icon** (⚙️) in the top right corner, then select **Settings**.

## Workspace Settings

### Workspace Path

Configure where File Organizer stores its data:

1. Click **Workspace** → **Path**
2. Choose workspace location
3. Ensure sufficient disk space (10+ GB recommended)
4. Click **Save**

**Note**: Changing workspace requires restart

### Workspace Name

Give your workspace a custom name:

1. Click **Workspace** → **Name**
2. Enter workspace name
3. Click **Save**

Uses: Shown in web interface title and API responses

## User Preferences

### Theme

Choose light or dark theme:

1. Click **Appearance** → **Theme**
2. Select:
   - Light mode
   - Dark mode
   - Auto (follows system)
3. Changes apply immediately

### Language

Select interface language:

1. Click **Appearance** → **Language**
2. Choose from:
   - English
   - Spanish
   - French
   - German
   - Japanese
   - (More coming soon)
3. Interface updates immediately

### Display Density

Adjust interface spacing:

1. Click **Appearance** → **Density**
2. Choose:
   - Compact (more content visible)
   - Normal (default)
   - Spacious (easier to read)
3. Updates immediately

### Font Size

Adjust text size:

1. Click **Appearance** → **Font Size**
2. Choose from slider
3. Updates immediately

## Notifications

### Notification Preferences

Control what notifications you receive:

1. Click **Notifications**
2. Toggle notification types:
   - Job completion
   - Errors and warnings
   - System updates
   - Tips and suggestions
3. Click **Save**

### Desktop Notifications

Enable browser desktop notifications:

1. Click **Notifications** → **Desktop**
2. Grant permission when prompted
3. Notifications appear even when tab inactive

### Notification Sound

Enable/disable notification sounds:

1. Click **Notifications** → **Sound**
2. Toggle on/off
3. Test sound button available

## API Configuration

### Generating API Keys

Create API tokens for programmatic access:

1. Click **API Keys**
2. Click **Generate New Key**
3. Configure:
   - **Name**: Identify the key
   - **Expiration**: When key expires
   - **Permissions**: What can be accessed
4. Key is shown once - copy immediately
5. Click **Done**

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
2. Choose:
   - PARA
   - Johnny Decimal
   - Custom
   - None
3. Click **Save**

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
2. Configure:
   - **Dry Run**: Always preview first
   - **Preserve Originals**: Keep copies
   - **Create Folders**: Auto-create structure
   - **Auto-Backup**: Backup before organizing
3. Click **Save**

## File Upload Settings

### Upload Limits

Configure file upload restrictions:

1. Click **Upload** → **Limits**
2. Set:
   - Max file size (per file)
   - Max batch size (total)
   - Supported file types
3. Click **Save**

### Auto-Scan

Enable automatic duplicate detection:

1. Click **Upload** → **Auto-Scan**
2. Toggle **Enable Auto-Scan**
3. Configure:
   - Scan after upload
   - Similarity threshold
4. Click **Save**

### Backup Settings

Configure file backups:

1. Click **Upload** → **Backups**
2. Configure:
   - Keep backups before organizing
   - Backup retention (days)
   - Backup location
3. Click **Save**

## Security Settings

### Change Password

Update your account password:

1. Click **Security** → **Password**
2. Enter current password
3. Enter new password (twice)
4. Click **Change Password**

**Password Requirements**:

- At least 8 characters
- Mix of upper and lowercase
- At least one number
- At least one special character

### Two-Factor Authentication

Enable additional security:

1. Click **Security** → **2FA**
2. Choose method:
   - Authenticator app (Google Authenticator, Authy, etc.)
   - SMS (if configured)
3. Follow setup wizard
4. Save backup codes (securely!)

### Sessions

View and manage active sessions:

1. Click **Security** → **Sessions**
2. See all active sessions:
   - Browser type
   - IP address
   - Last activity
3. Click **Logout** to end session
4. **Logout All** to sign out everywhere

### Login History

Review recent login activity:

1. Click **Security** → **Login History**
2. See:
   - Date and time
   - IP address
   - Browser and OS
   - Success/failure

## Privacy Settings

### Data Collection

Control what data is collected:

1. Click **Privacy** → **Data Collection**
2. Toggle options:
   - Usage analytics
   - Error reporting
   - Feature suggestions
   - No personal data is collected

### Cookies

Manage browser cookies:

1. Click **Privacy** → **Cookies**
2. See what cookies are used:
   - Session management
   - User preferences
   - Analytics
3. Clear cookies if desired

### Third-Party Services

View integrations:

1. Click **Privacy** → **Integrations**
2. No third-party integrations by default
3. Enable if connecting external services

## Storage Settings

### View Storage

See storage usage breakdown:

1. Click **Storage** → **Usage**
2. See:
   - Total capacity
   - Used space
   - Available space
   - Breakdown by category

### Clean Up Storage

Free up disk space:

1. Click **Storage** → **Cleanup**
2. Options:
   - Delete old backups
   - Clear caches
   - Archive old files
   - Remove duplicates
3. Preview what will be deleted
4. Click **Cleanup**

### Storage Alerts

Get notified when storage runs low:

1. Click **Storage** → **Alerts**
2. Configure:
   - Alert at % full (e.g., 80%)
   - Notification method
3. Click **Save**

## Advanced Settings

### System Information

View system details:

1. Click **Advanced** → **System**
2. See:
   - Python version
   - Ollama version
   - Database info
   - Available RAM/CPU

### Import/Export

Backup and restore settings:

**Export Settings**

1. Click **Advanced** → **Import/Export**
2. Click **Export Settings**
3. JSON file downloads

**Import Settings**

1. Click **Import Settings**
2. Choose JSON file
3. Settings are restored

### Logs

Access application logs:

1. Click **Advanced** → **Logs**
2. Filter by level:
   - Debug
   - Info
   - Warning
   - Error
3. View recent logs
4. Download logs file

### Reset to Defaults

Reset all settings:

1. Click **Advanced** → **Reset**
2. Choose what to reset:
   - All settings
   - Workspace only
   - User preferences
3. **WARNING**: This cannot be undone
4. Click **Reset**

## Mobile Settings

### Responsive Mode

The web interface adapts to mobile:

1. Settings accessible on mobile
2. Same functionality as desktop
3. Touch-optimized interface
4. Reduced features on very small screens

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
2. Save JSON file
3. Keep in secure location
4. Can restore if needed

## Next Steps

- [File Management](file-management.md)
- [Organization](organization.md)
- [Analysis & Search](analysis-search.md)
