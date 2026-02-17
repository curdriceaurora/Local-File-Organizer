# Security Guide

## Authentication & Authorization

### API Key Management

#### Generate API Keys

```bash
# Via API endpoint
curl -X POST http://localhost:8000/api/v1/auth/keys \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "client-key"}'
```

#### API Key Format

File Organizer API keys follow the format: `fo_<id>_<token>`

Example: `fo_abc123_secret456key789`

#### Best Practices

- Rotate API keys regularly (every 90 days)
- Never commit API keys to version control
- Use environment variables or secret managers
- Revoke unused keys immediately
- Monitor key usage for suspicious activity

### JWT Tokens

#### Token Generation

```bash
# Login endpoint returns JWT token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'
```

#### Token Configuration

```bash
JWT_ALGORITHM=HS256
JWT_EXPIRATION=86400  # 24 hours
JWT_REFRESH_EXPIRATION=604800  # 7 days
```

## Network Security

### HTTPS/TLS

Always use HTTPS in production:

```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/example.com.crt;
    ssl_certificate_key /etc/ssl/private/example.com.key;

    # Strong ciphers
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_protocols TLSv1.2 TLSv1.3;
}
```

### CORS Configuration

```bash
# Allow specific origins only
CORS_ORIGINS=["https://example.com","https://app.example.com"]

# Never use CORS_ORIGINS=["*"] in production
```

### Rate Limiting

```bash
# Enable rate limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=1000
RATE_LIMIT_WINDOW=3600  # 1 hour

# Per-endpoint limits
/api/v1/auth/login: 10 requests per minute
/api/v1/files/upload: 100 requests per minute
```

## Data Security

### File Upload Security

#### Size Limits

```bash
MAX_UPLOAD_SIZE=500M
MAX_FILE_SIZE_INDIVIDUAL=1G
```

#### File Type Validation

```bash
ALLOWED_EXTENSIONS=pdf,doc,docx,xls,xlsx,ppt,pptx,jpg,png,gif,mp3,mp4,txt,md
```

#### Malware Scanning

```bash
# Enable virus scanning (optional)
ENABLE_VIRUS_SCANNING=true
VIRUS_SCAN_TIMEOUT=60
```

### Database Security

#### Encryption

```bash
# Enable database encryption at rest
DATABASE_ENCRYPTION=true
ENCRYPTION_KEY=your-encryption-key

# Use SSL for database connection
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require
```

#### Backups

```bash
# Encrypted backups
pg_dump -h localhost -U user file_organizer | \
  gpg --symmetric --cipher-algo aes256 > backup.sql.gpg

# Test restore before disaster
pg_restore -d test_db backup.sql
```

## Access Control

### User Roles

- **Admin**: Full system access
- **User**: Can organize personal files
- **Viewer**: Read-only access
- **API**: Limited API key access

### RBAC Configuration

```yaml
roles:
  admin:
    permissions:
      - '*'  # All permissions
  user:
    permissions:
      - file:read
      - file:upload
      - file:organize
      - file:delete_own
  viewer:
    permissions:
      - file:read
```

## Audit Logging

### Audit Trail

Log all security-relevant events:

```
2026-02-17 10:30:00 | USER_LOGIN | admin | 192.168.1.100 | SUCCESS
2026-02-17 10:31:00 | FILE_UPLOAD | user1 | 192.168.1.101 | document.pdf | SUCCESS
2026-02-17 10:32:00 | API_KEY_CREATE | admin | 192.168.1.100 | client-key | SUCCESS
2026-02-17 10:33:00 | AUTH_FAILURE | unknown | 192.168.1.102 | admin | 3_ATTEMPTS
```

### Log Retention

```bash
# Keep audit logs for at least 1 year
AUDIT_LOG_RETENTION=365
AUDIT_LOG_LOCATION=/var/log/file-organizer/audit.log
```

## Security Updates

### Dependency Scanning

```bash
# Check for vulnerabilities
pip audit

# Update dependencies
pip install --upgrade pip
pip install -r requirements.txt --upgrade
```

### Regular Updates

- Update OS and system packages monthly
- Update Python dependencies immediately for security fixes
- Monitor GitHub Security Advisories
- Test updates in staging before production

## Incident Response

### If Compromised

1. Immediately revoke all API keys
1. Reset all passwords
1. Review audit logs for unauthorized access
1. Rotate database credentials
1. Notify users if data was accessed
1. Enable enhanced logging

### Suspicious Activity

Monitor for:

- Multiple failed login attempts
- Unusual API usage patterns
- Large file downloads
- After-hours access
- Bulk data operations

## Compliance

### Data Privacy

- GDPR compliance for EU users
- Data retention policies
- User consent management
- Export user data on request

### Security Standards

- Follow OWASP Top 10 guidelines
- Regular security audits
- Penetration testing (quarterly)
- Security headers configuration

## See Also

- [Configuration Guide](configuration.md)
- [Deployment Guide](deployment.md)
