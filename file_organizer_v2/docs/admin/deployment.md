# Deployment Guide

## Overview

This guide covers deploying File Organizer to production environments using Docker and standard web server practices.

## Docker Deployment

### Docker Compose Setup

Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  web:
    image: file-organizer:latest
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/file_organizer
      - REDIS_URL=redis://redis:6379
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      - db
      - redis
      - ollama
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=file_organizer
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

volumes:
  postgres_data:
  redis_data:
  ollama_data:
```

### Environment Variables

Key environment variables:

- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `OLLAMA_HOST` - Ollama service URL
- `SECRET_KEY` - Application secret key
- `MAX_UPLOAD_SIZE` - Maximum upload file size
- `API_KEY_PREFIX` - Custom API key prefix

### Deployment Commands

```bash
# Start all services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Scale services
docker-compose up -d --scale web=3
```

## Reverse Proxy Setup

### Nginx Configuration

```nginx
upstream file_organizer {
    server web:8000;
}

server {
    listen 80;
    server_name example.com;

    client_max_body_size 500M;

    location / {
        proxy_pass http://file_organizer;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://file_organizer;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### SSL/TLS Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate /etc/ssl/certs/example.com.crt;
    ssl_certificate_key /etc/ssl/private/example.com.key;

    # ... rest of configuration
}

server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;
}
```

## Database Migrations

```bash
# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Add new column"
```

## Health Checks

```bash
# API health
curl http://localhost:8000/api/v1/health

# Database connectivity
curl http://localhost:8000/api/v1/health/db

# Cache connectivity
curl http://localhost:8000/api/v1/health/cache
```

## See Also

- [Configuration Guide](configuration.md)
- [Monitoring Guide](monitoring.md)
