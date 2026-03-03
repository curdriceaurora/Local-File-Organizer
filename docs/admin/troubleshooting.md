# Admin Troubleshooting Guide

## Common Issues

### Application Won't Start

#### Problem: Port Already in Use

```text
ERROR: Failed to bind to port 8000
```

**Solution**:

```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
PORT=8001 python app.py
```

#### Problem: Database Connection Failed

```text
ERROR: Unable to connect to database
```

**Solution**:

```bash
# Verify database URL
echo $DATABASE_URL

# Test connection
psql $DATABASE_URL -c "SELECT 1;"

# Check if PostgreSQL is running
docker-compose ps db

# Restart database
docker-compose restart db
```

### High Memory Usage

**Problem**: Application consuming excessive memory

**Solution**:

```bash
# Monitor memory usage
docker stats

# Check for memory leaks
docker logs web | grep -i memory

# Restart Ollama
docker-compose restart ollama

# Clear Redis cache
redis-cli FLUSHDB
```

### High CPU Usage

**Problem**: Application consuming excessive CPU

**Solution**:

```bash
# Monitor CPU usage
docker stats

# Find slow queries
docker-compose exec db psql -U user -d file_organizer \
  -c "SELECT * FROM pg_stat_statements WHERE mean_time > 1000;"

# Kill slow queries
docker-compose exec db psql -U user -d file_organizer \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'active' AND query_start < NOW() - interval '5 min';"
```

### Disk Space Issues

**Problem**: Disk full or running low

**Solution**:

```bash
# Check disk usage
df -h

# Check Ollama models size
du -sh ~/.ollama/

# Check upload directory
du -sh /data/uploads/

# Clean old files
find /data/uploads/ -mtime +30 -delete
```

## API Issues

### 401 Unauthorized

**Problem**: API requests returning 401

**Solution**:

API keys follow the format `fo_<id>_<token>` and must be sent via the `X-API-Key` header.

```bash
# Verify API key is accepted
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/api/v1/files
```

!!! warning "Auth header"
    Use `X-API-Key: YOUR_API_KEY`, **not** `Authorization: Bearer YOUR_API_KEY`.
    Bearer tokens are not supported for API key authentication.

### 403 Forbidden

**Problem**: API requests returning 403

**Solution**:

```bash
# Check user permissions
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "X-API-Key: YOUR_API_KEY"

# Verify role and permissions
# User may lack required permissions
```

### 500 Internal Server Error

**Problem**: API returning 500 errors

**Solution**:

```bash
# Check application logs
docker-compose logs web

# Check for specific errors
docker-compose logs web | grep ERROR

# Restart application
docker-compose restart web

# Check database connectivity
docker-compose exec web python -c \
  "from app.db import SessionLocal; SessionLocal()"
```

## File Processing Issues

### Upload Fails

**Problem**: File upload failing

**Solution**:

```bash
# Test file access endpoint to verify authentication
curl -i "http://localhost:8000/api/v1/files?path=/" \
  -H "X-API-Key: YOUR_API_KEY"

# Increase MAX_UPLOAD_SIZE if needed
MAX_UPLOAD_SIZE=1G docker-compose up -d

# Check disk space
df -h /data/uploads/
```

### Organization Job Hangs

**Problem**: Organization job stuck or not progressing

**Solution**:

```bash
# Check job status
curl http://localhost:8000/api/v1/organize/status/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"

# Kill stuck job
docker-compose exec web python -c \
  "from app.jobs import cancel_job; cancel_job('JOB_ID')"

# Restart worker
docker-compose restart worker
```

## Database Issues

### Slow Queries

**Problem**: Database queries running slow

**Solution**:

```bash
# Enable query logging
docker-compose exec db psql -U user -d file_organizer \
  -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"

# Reload configuration
docker-compose exec db psql -U user -c "SELECT pg_reload_conf();"

# Analyze slow queries
docker-compose exec db psql -U user -d file_organizer \
  -c "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"
```

### Connection Pool Exhausted

**Problem**: "Too many connections" error

**Solution**:

```bash
# Check active connections
docker-compose exec db psql -U user -d file_organizer \
  -c "SELECT count(*) FROM pg_stat_activity;"

# Increase pool size
DATABASE_POOL_SIZE=30 docker-compose up -d

# Kill idle connections
docker-compose exec db psql -U user -d file_organizer \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle';"
```

## WebSocket Issues

### Connection Fails

**Problem**: WebSocket connections failing

**Solution**:

```bash
# Check WebSocket endpoint
# Correct: /api/v1/ws/{client_id}

# Check headers
curl -i -N -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  http://localhost:8000/api/v1/ws/client123

# Verify proxy configuration
# WebSocket requires HTTP/1.1 and upgrade headers
```

## Networking Issues

### Reverse Proxy Issues

**Problem**: Behind Nginx/Apache, requests fail

**Solution**:

```nginx
# Ensure proper headers
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;

# WebSocket support
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### CORS Issues

**Problem**: Cross-origin requests failing

**Solution**:

```bash
# Check CORS configuration
CORS_ORIGINS="https://example.com,https://app.example.com"

# Verify in response headers
curl -i http://localhost:8000/api/v1/files

# Look for:
# Access-Control-Allow-Origin: <your-domain>
```

## Model Issues

### Ollama Model Not Available

**Problem**: "Model not found" error

**Solution**:

```bash
# Check available models
ollama ls

# Pull required models
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M

# Verify Ollama is running
ollama ps
```

### Model Inference Timeout

**Problem**: Model requests timing out

**Solution**:

```bash
# Increase timeout
MODEL_TIMEOUT=600  # 10 minutes

# Check Ollama memory usage
docker stats ollama

# Reduce concurrent requests
# Check load on Ollama service
```

## Getting Help

### Collect Diagnostic Information

```bash
# System info
uname -a
docker --version
docker-compose --version

# Application logs
docker-compose logs web > web.log
docker-compose logs db > db.log

# Configuration (without secrets)
env | grep -v PASSWORD | grep -v SECRET | grep -v KEY > env.log

# Resource usage
docker stats --no-stream > stats.log
df -h > disk.log
```

### Report an Issue

Include:

1. Error message and logs
1. Steps to reproduce
1. System information (OS, Docker version)
1. Recent configuration changes
1. Diagnostic information collected above
