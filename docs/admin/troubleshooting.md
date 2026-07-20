# Admin Troubleshooting Guide

> For everyday user-facing issues (optional dependencies, AI providers, TUI/desktop, audio/video, search), see the [User Troubleshooting Guide](../troubleshooting.md).

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

# Gracefully stop the process
kill <PID>
# If the process does not stop after a few seconds, force-kill it:
kill -9 <PID>

# Or start File Organizer on a different port
file-organizer serve --port 8001

# When using Docker Compose, edit the ports mapping in docker-compose.yml:
#   ports:
#     - "8001:8001"   # change both sides to match your chosen port
# Then set FO_PORT so the app binds to the same port inside the container:
echo "FO_PORT=8001" >> .env
docker-compose up -d
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

## Redis Issues

### Redis Connection Failed

**Problem**: `ConnectionError: Error connecting to Redis` or session/cache features not working

**Solution**:

```bash
# Check the configured Redis URL
echo $FO_REDIS_URL

# Verify the Redis container is running
docker-compose ps redis

# Restart the Redis container if it is stopped/unhealthy
docker-compose restart redis

# Test the connection directly from the Redis container.
# REDISCLI_AUTH is already set in the container environment (docker-compose.yml),
# so redis-cli authenticates automatically — no password argument needed.
docker-compose exec redis redis-cli ping
# Expected output: PONG
```

### Redis Memory Pressure / Eviction

**Problem**: Cache misses increase, or Redis logs `maxmemory policy: allkeys-lru` evictions

**Solution**:

```bash
# Check Redis memory usage
docker-compose exec redis redis-cli info memory | grep used_memory_human

# Check current eviction policy
docker-compose exec redis redis-cli config get maxmemory-policy

# If eviction is too aggressive, increase the memory limit in docker-compose.yml
# or in your Redis configuration:
#   maxmemory 512mb
#   maxmemory-policy allkeys-lru

docker-compose restart redis
```

### Clearing the Redis Cache (Safe)

Only do this when debugging stale cache data. Flushing removes all cached sessions and data.

```bash
# Flush only the File Organizer database (default: db 0)
docker-compose exec redis redis-cli -n 0 FLUSHDB

# Restart the app after clearing
docker-compose restart file-organizer
```

### Redis Auth / TLS Errors

**Problem**: `NOAUTH Authentication required` or TLS handshake failure

**Solution**:

The Compose stack reads `REDIS_PASSWORD` from `.env` and injects it into both the Redis service and the app's `FO_REDIS_URL`. Exporting a shell variable will not reach the container — set it in `.env` instead:

```bash
# Edit .env (copy from .env.example if it doesn't exist yet)
# Set a strong password — avoid special URI characters (@ : / # %)
echo "REDIS_PASSWORD=your_strong_password" >> .env

docker-compose up -d
```

For an external TLS-enabled Redis (e.g., Redis Cloud, Azure Cache for Redis), update `FO_REDIS_URL` in `docker-compose.yml` directly to use the `rediss://` scheme and external hostname:

```yaml
# docker-compose.yml — under the file-organizer service's environment:
- FO_REDIS_URL=rediss://:your_password@hostname.redis.cloud:6380/0
```

Then redeploy:

```bash
docker-compose up -d
```

## Deployment Rollback

> **Note**: This section covers rolling back the *application version* in a Docker deployment. To undo individual file organization operations, see [Operation Undo / Rollback](../troubleshooting.md#operation-undo-rollback-issues) in the User Troubleshooting Guide.

### Roll Back to a Previous Source Version

The default `docker-compose.yml` builds the image from source (`build: context: .`). To roll back to a previous release, check out the target git tag and rebuild:

```bash
# Identify the release tag to roll back to
git tag --sort=-version:refname | head -10

# Check out the previous release
git checkout v2.0.0-alpha.3    # replace with the target tag

# Rebuild and redeploy
docker-compose build
docker-compose up -d
```

If your deployment uses a pre-built registry image instead of a local build, edit the `image:` field directly in `docker-compose.yml`:

```yaml
# docker-compose.yml
services:
  file-organizer:
    image: ghcr.io/curdriceaurora/local-file-organizer:2.0.0-alpha.3
    # Remove or comment out the 'build:' block when pinning an image tag
```

Then redeploy:

```bash
docker-compose pull
docker-compose up -d
```

### Database Migration Rollback

If a new version ran Alembic migrations and you need to revert:

```bash
# Identify the previous migration revision
docker-compose exec file-organizer alembic history --indicate-current

# Downgrade one step
docker-compose exec file-organizer alembic downgrade -1

# Or downgrade to a specific revision ID
docker-compose exec file-organizer alembic downgrade <revision_id>
```

Always take a database backup before rolling back migrations in production.

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
