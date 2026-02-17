# Configuration Guide

## Environment Configuration

### Core Settings

```bash
# Application
APP_ENV=production
DEBUG=false
SECRET_KEY=your-secret-key-here

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4

# Database
DATABASE_URL=postgresql://user:password@localhost/file_organizer
DATABASE_POOL_SIZE=20
DATABASE_ECHO=false

# Cache/Redis
REDIS_URL=redis://localhost:6379/0
CACHE_TTL=3600

# File Storage
UPLOAD_DIR=/data/uploads
MAX_UPLOAD_SIZE=500M  # 500 megabytes
ALLOWED_EXTENSIONS=pdf,doc,docx,xls,xlsx,ppt,pptx,jpg,png,gif,mp3,mp4,txt,md
```

### AI Models Configuration

```bash
# Ollama Settings
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL_TEXT=qwen2.5:3b-instruct-q4_K_M
OLLAMA_MODEL_VISION=qwen2.5vl:7b-q4_K_M

# Model Parameters
MODEL_TEMPERATURE=0.5
MODEL_MAX_TOKENS=3000
MODEL_TIMEOUT=300
```

### Security Settings

```bash
# API Authentication
API_KEY_PREFIX=fo_
API_KEY_HEADER=X-API-Key
JWT_SECRET=your-jwt-secret-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION=86400  # 24 hours

# CORS
CORS_ORIGINS=["http://localhost:3000","https://example.com"]

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=1000
RATE_LIMIT_WINDOW=3600  # 1 hour
```

### Logging Configuration

```bash
# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/var/log/file-organizer/app.log
LOG_ROTATION=daily
LOG_RETENTION=30  # days
```

## Configuration File

Create `.env.production`:

```env
APP_ENV=production
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://user:pass@db:5432/db
REDIS_URL=redis://redis:6379
OLLAMA_HOST=http://ollama:11434
MAX_UPLOAD_SIZE=500M
LOG_LEVEL=INFO
```

## Configuration Methods

### 1. Environment Variables

```bash
export DATABASE_URL="postgresql://user:pass@localhost/db"
export OLLAMA_HOST="http://localhost:11434"
./start_server.sh
```

### 2. .env File

Place `.env` in project root:

```bash
DATABASE_URL=postgresql://user:pass@localhost/db
OLLAMA_HOST=http://localhost:11434
```

### 3. Configuration File

Create `config/production.yml`:

```yaml
database:
  url: postgresql://user:pass@localhost/db
  pool_size: 20

ollama:
  host: http://localhost:11434
  models:
    text: qwen2.5:3b-instruct
    vision: qwen2.5vl:7b

server:
  workers: 4
  timeout: 300
```

## Advanced Configuration

### Custom Methodologies

Configure PARA and Johnny Decimal:

```yaml
methodologies:
  para:
    projects_folder: Projects
    areas_folder: Areas
    resources_folder: Resources
    archives_folder: Archives
  johnny_decimal:
    enabled: true
    system_name: "File Organizer"
```

### Plugin Configuration

```yaml
plugins:
  enabled: true
  directory: /app/plugins
  auto_load: true
  hooks:
    - on_file_upload
    - on_organize_complete
    - on_duplicate_detected
```

## See Also

- [Installation Guide](installation.md)
- [Deployment Guide](deployment.md)
- [Monitoring Guide](monitoring.md)
