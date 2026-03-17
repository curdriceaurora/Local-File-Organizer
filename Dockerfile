# =============================================================================
# File Organizer v2 - Production Dockerfile
# Multi-stage build optimized for Python 3.11 deployment
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies into isolated virtual environment
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies required for compiling Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for clean dependency isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (copy requirements first for layer caching)
COPY pyproject.toml /build/pyproject.toml
COPY src/ /build/src/

WORKDIR /build

# Install the package and its dependencies into the virtual environment
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

# ---------------------------------------------------------------------------
# Stage 2: Runtime - Minimal image with only runtime dependencies
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

# OCI Image Labels (https://github.com/opencontainers/image-spec/blob/main/annotations.md)
LABEL org.opencontainers.image.title="File Organizer v2" \
      org.opencontainers.image.description="AI-powered local file management system with privacy-first architecture" \
      org.opencontainers.image.version="2.0.0-alpha.1" \
      org.opencontainers.image.authors="Local File Organizer Team <noreply@example.com>" \
      org.opencontainers.image.url="https://github.com/yourusername/file-organizer-v2" \
      org.opencontainers.image.source="https://github.com/yourusername/file-organizer-v2" \
      org.opencontainers.image.licenses="MIT OR Apache-2.0" \
      org.opencontainers.image.base.name="python:3.11-slim"

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN groupadd --gid 1000 organizer \
    && useradd --uid 1000 --gid organizer --shell /bin/bash --create-home organizer

# Create data directory and set permissions
RUN mkdir -p /data && chown organizer:organizer /data

# Set working directory
WORKDIR /app

# Copy application source
COPY src/ /app/src/
COPY pyproject.toml /app/pyproject.toml

# Ensure the application user owns the app directory
RUN chown -R organizer:organizer /app

# Declare persistent data volume
VOLUME /data

# Expose the web API port
EXPOSE 8000

# Switch to non-root user
USER organizer

# Healthcheck using the API endpoint (respects FO_API_PORT override)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${FO_API_PORT:-8000}/api/v1/health || exit 1

# Default command: run the web API server (override port via FO_API_PORT env var)
# Shell-form for env-var expansion; `exec` replaces sh so uvicorn is PID 1 (clean SIGTERM)
CMD exec python -m uvicorn file_organizer.api:app --host 0.0.0.0 --port ${FO_API_PORT:-8000}
