# Authentication

Secure your API requests with authentication.

## API Key Authentication

### Generating an API Key

API keys are personal access tokens for API requests.

1. Log in to web interface
1. Click **Settings** (gear icon)
1. Go to **API Keys**
1. Click **Generate New Key**
1. Configure:
   - **Name**: Identify the key (e.g., "Python Script")
   - **Expiration**: When key expires (30 days, 90 days, 1 year, never)
   - **Permissions**: Select what key can do
1. Click **Generate**
1. Copy the token (shown only once)

### API Key Format

API keys are personal access tokens:

```
fo_abc123_token456
```

- Prefix: `fo_` (File Organizer)
- ID: unique identifier
- Token: secret portion
- Unique per key

### Using Your API Key

Include API key in the `X-API-Key` header:

```bash
curl http://localhost:8000/api/v1/files \
  -H "X-API-Key: YOUR_API_KEY"
```

> **Security Note:** Do not pass API keys in URL query parameters. Always use the `X-API-Key` header.

## API Key Permissions

Control what each API key can do:

### Permission Levels

| Permission | Allows |
|-----------|--------|
| `read:files` | List and view files |
| `write:files` | Upload files |
| `write:files:delete` | Delete files |
| `read:organize` | View organization jobs |
| `write:organize` | Create organization jobs |
| `read:analyze` | Run analysis |
| `read:search` | Search files |
| `read:admin` | View system info |
| `write:admin` | Modify system settings |

### Recommended Permissions

**For Scripts**:

- `read:files`
- `read:search`
- `read:organize`

**For Applications**:

- `read:files`
- `write:files`
- `read:search`
- `read:organize`

**For Admin Tools**:

- All permissions (use with caution!)

## Managing API Keys

### View Your Keys

1. Go to **Settings** → **API Keys**
1. See all active keys:
   - Name and creation date
   - Expiration date
   - Last used
   - Permissions
   - Actions

### Revoke a Key

1. Find key in API Keys list
1. Click **Revoke**
1. Confirm deletion
1. Key is disabled immediately
1. Any requests with this key fail

### Rotate a Key

Generate a new key and revoke the old:

1. **Generate New Key** with new permissions
1. Update scripts/applications
1. **Revoke** old key
1. Verify everything works

## Rate Limiting

API requests are rate-limited to prevent abuse.

Rate limits are configured in the application settings (`ApiSettings`).

- **Default Limit**: 1000 requests/minute
- **Configurable**: Administrators can adjust `rate_limit_default_requests` and `rate_limit_rules`.

### Checking Rate Limits

Rate limits appear in response headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1645026000
```

- **Limit**: Total requests per minute
- **Remaining**: Requests left in current window
- **Reset**: Unix timestamp when window resets

### Handling Rate Limits

If you exceed the limit:

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests",
    "retryAfter": 60
  }
}
```

**Response**:

- HTTP Status: 429 Too Many Requests
- `Retry-After` header indicates seconds to wait

**Best Practices**:

- Wait before retrying
- Use exponential backoff
- Batch requests when possible
- Consider upgrading tier

## Error Responses

### Unauthorized (401)

```json
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing API key"
  }
}
```

**Causes**:

- Missing API key
- Invalid API key
- Expired API key
- Revoked API key

**Solutions**:

- Check key is included
- Verify key format
- Generate new key if expired
- Check if key was revoked

### Forbidden (403)

```json
{
  "success": false,
  "error": {
    "code": "FORBIDDEN",
    "message": "Permission denied",
    "details": {
      "required": "write:files",
      "granted": "read:files"
    }
  }
}
```

**Causes**:

- Key lacks required permission
- User lacks access to resource

**Solutions**:

- Regenerate key with needed permissions
- Use different key
- Contact administrator

## Security Best Practices

### Key Management

1. **Keep Keys Secret**

   - Don't commit to version control
   - Don't share in messages
   - Store securely (environment variables)

1. **Use Environment Variables**

   ```bash
   export FILE_ORGANIZER_API_KEY="fo_abc123_token456"
   ```

1. **Rotate Regularly**

   - Generate new keys periodically
   - Revoke old keys
   - Update applications

1. **Use Minimal Permissions**

   - Only request needed permissions
   - Create separate keys for different apps
   - Review permissions regularly

### Secure Storage

**Python**:

```python
import os
api_key = os.getenv('FILE_ORGANIZER_API_KEY')
```

**Node.js**:

```javascript
const apiKey = process.env.FILE_ORGANIZER_API_KEY;
```

**.env File**:

```
FILE_ORGANIZER_API_KEY=fo_abc123_token456
```

## API Key Expiration

### Setting Expiration

When creating/regenerating key:

1. Choose expiration time
1. Options: 30 days, 90 days, 1 year, never
1. Key expires automatically

### Before Expiration

Receive notification:

- Email reminder (7 days before)
- Web interface warning
- API requests continue working

### After Expiration

- Key becomes invalid
- API requests return 401
- Must generate new key
- Update applications

## Scopes

Fine-grained permission scopes for advanced use:

### Read Scopes

- `read:files` - List files, view properties
- `read:search` - Search files
- `read:organize` - View organization jobs
- `read:analyze` - Run analysis

### Write Scopes

- `write:files` - Upload files
- `write:files:delete` - Delete files
- `write:organize` - Create organization jobs
- `write:analyze` - Create analysis jobs

### Admin Scopes

- `read:admin` - View system information
- `write:admin` - Modify system settings

## Next Steps

- [File Management API](file-endpoints.md)
- [Organization API](organization-endpoints.md)
- [API Clients](../developer/api-clients.md)
