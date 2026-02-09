# Deployment Guide

This document covers Docker-based deployment, development setup, environment
variables, volume mounts, and Redis configuration for File Organizer v2.

## Docker Deployment

### Production Build

The production Dockerfile uses a multi-stage build to produce a minimal image:

```
Stage 1 (builder)   Stage 2 (runtime)
python:3.11-slim     python:3.11-slim
  |                    |
  +-- build tools      +-- ffmpeg, libmagic, curl
  +-- pip install .    +-- opt/venv (from builder)
                       +-- non-root user "organizer"
                       +-- HEALTHCHECK on :8000/health
```

Build and run the production image:

```bash
# Build
docker build -t file-organizer:latest .

# Run standalone
docker run -d \
  --name file-organizer \
  -p 8000:8000 \
  -v organizer-data:data \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  file-organizer:latest
```

The container:
- Runs as non-root user `organizer` (UID/GID 1000).
- Exposes port 8000 for the web API.
- Declares `data` as a persistent volume.
- Includes a health check that pings `http://localhost:8000/health` every 30s.

### Docker Compose (Production)

The simplest way to run the full stack (app + Redis):

```bash
docker compose up -d
```

This starts two services:

| Service          | Image               | Ports | Purpose              |
|------------------|---------------------|-------|----------------------|
| `file-organizer` | Built from Dockerfile | 8000  | Web API server       |
| `redis`          | redis:7-alpine      | 6379  | Event stream backend |

Redis includes a health check (`redis-cli ping`), and the app service waits
for Redis to be healthy before starting.

To stop:

```bash
docker compose down
```

To stop and remove volumes:

```bash
docker compose down -v
```

### Development Setup with Docker

For development with live reload and debug tools:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

The development overlay (`docker-compose.dev.yml`):
- Uses `Dockerfile.dev` (full Python image with dev tools).
- Bind-mounts `./file_organizer_v2/src` into the container for live code
  changes.
- Sets `FILE_ORGANIZER_LOG_LEVEL=DEBUG`.
- Exposes port 5678 for `debugpy` remote debugging.
- Runs uvicorn with `--reload` for automatic restart on code changes.

#### Running Tests in Docker

```bash
# Start the test runner service
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  --profile test up test-runner

# Or run tests manually in the dev container
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  exec file-organizer python -m pytest tests/ -v
```

#### Remote Debugging

The development container exposes debugpy on port 5678. Configure your IDE:

**VS Code (`launch.json`):**

```json
{
  "name": "Docker: Remote Attach",
  "type": "debugpy",
  "request": "attach",
  "connect": { "host": "localhost", "port": 5678 },
  "pathMappings": [
    {
      "localRoot": "${workspaceFolder}/file_organizer_v2/src",
      "remoteRoot": "app/file_organizer_v2/src"
    }
  ]
}
```

## Environment Variables

| Variable                    | Default                   | Description                          |
|-----------------------------|---------------------------|--------------------------------------|
| `FILE_ORGANIZER_DATA_DIR`   | `data`                   | Base directory for persistent data   |
| `FILE_ORGANIZER_LOG_LEVEL`  | `INFO`                    | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `FILE_ORGANIZER_DEBUG`      | `0`                       | Enable debug mode (set to `1`)       |
| `REDIS_URL`                 | `redis://localhost:6379/0`| Redis connection URL                 |

These variables are read by the application at startup. In Docker Compose,
they are set in the `environment` section of each service.

### Setting Environment Variables

**Docker Compose:**

```yaml
services:
  file-organizer:
    environment:
      - FILE_ORGANIZER_DATA_DIR=data
      - FILE_ORGANIZER_LOG_LEVEL=INFO
      - REDIS_URL=redis://redis:6379/0
```

**Docker run:**

```bash
docker run -e REDIS_URL=redis://myredis:6379/0 file-organizer:latest
```

**Local development (without Docker):**

```bash
export REDIS_URL=redis://localhost:6379/0
export FILE_ORGANIZER_LOG_LEVEL=DEBUG
file-organizer --help
```

Or use a `.env` file (loaded by `python-dotenv`):

```
REDIS_URL=redis://localhost:6379/0
FILE_ORGANIZER_LOG_LEVEL=DEBUG
FILE_ORGANIZER_DATA_DIR=./data
```

## Volume Mounts

### Production Volumes

| Volume           | Mount Point | Purpose                              |
|------------------|-------------|--------------------------------------|
| `organizer-data` | `data`     | Persistent storage for organized files, database, and configuration |
| `redis-data`     | `data`     | Redis persistence (RDB/AOF)          |

Both volumes use the `local` driver by default. For cloud deployments, replace
with your storage driver (e.g., EFS, GCE PD).

### Development Volumes

| Bind Mount                       | Container Path                | Purpose              |
|----------------------------------|-------------------------------|----------------------|
| `./file_organizer_v2/src`        | `app/file_organizer_v2/src`  | Live code reload     |
| `./file_organizer_v2/tests`      | `app/file_organizer_v2/tests`| Test files (test-runner only) |

### Custom Watch Directories

To monitor host directories for file organization, bind-mount them:

```bash
docker run -d \
  -v path/to/incoming:data/incoming:ro \
  -v organizer-data:data/organized \
  -e FILE_ORGANIZER_DATA_DIR=data \
  file-organizer:latest
```

## Redis Configuration

### Connection

The event system connects to Redis using the URL from `EventConfig.redis_url`
(default: `redis://localhost:6379/0`). In Docker Compose, the service name
`redis` is used as the hostname.

### Stream Configuration

The `EventConfig` dataclass controls stream behavior:

```python
from file_organizer.events import EventConfig

config = EventConfig(
    redis_url="redis://localhost:6379/0",
    stream_prefix="fileorg",       # All streams prefixed: fileorg:file-events
    consumer_group="file-organizer",
    max_retries=3,
    retry_delay=1.0,
    block_ms=5000,                 # Block 5s when reading
    max_stream_length=10000,       # Approximate stream trim length
    batch_size=10,                 # Messages per read
)
```

### Redis Persistence

The default Redis image (`redis:7-alpine`) uses RDB snapshots. For production,
consider enabling AOF for better durability:

```yaml
# In docker-compose.yml, add command to redis service:
redis:
  image: redis:7-alpine
  command: ["redis-server", "--appendonly", "yes"]
  volumes:
    - redis-data:data
```

### Redis Memory Limits

For production, set a memory limit:

```yaml
redis:
  image: redis:7-alpine
  command: >
    redis-server
    --maxmemory 256mb
    --maxmemory-policy allkeys-lru
    --appendonly yes
```

### Monitoring Redis Streams

Check stream health from the host:

```bash
# Connect to Redis CLI
docker exec -it file-organizer-redis redis-cli

# List all streams
KEYS fileorg:*

# Check stream length
XLEN fileorg:file-events

# Check consumer group info
XINFO GROUPS fileorg:file-events

# Check pending messages
XPENDING fileorg:file-events file-organizer

# Monitor events in real-time
MONITOR
```

### Graceful Degradation

If Redis is unavailable:
- The event system operates in no-op mode.
- Events are silently dropped (logged at debug level).
- File processing continues without event emission.
- No data is lost -- files are still organized.

Redis is an optional enhancement for observability and inter-service
communication, not a hard requirement for core functionality.

## Local Development (Without Docker)

```bash
# 1. Install Python 3.9+
python3 --version

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install with dev extras
pip install -e "file_organizer_v2[dev]"

# 4. (Optional) Start Redis
brew install redis && brew services start redis
# Or: docker run -d -p 6379:6379 redis:7-alpine

# 5. Install Ollama for AI inference
# See: https://ollama.ai/download
ollama pull qwen2.5:3b-instruct-q4_K_M

# 6. Run
file-organizer --help
```

## Health Checks

### Docker Health Check

The production Dockerfile includes:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

### Redis Health Check

```yaml
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 5s
```

### Compose Service Dependencies

The `file-organizer` service uses `depends_on` with a health condition to
wait for Redis:

```yaml
depends_on:
  redis:
    condition: service_healthy
```
