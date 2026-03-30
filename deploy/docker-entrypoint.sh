#!/bin/bash
# Docker entrypoint for File Organizer v2
#
# Performs startup checks and initializes the application:
# 1. Validates required environment variables
# 2. Waits for Redis (if configured)
# 3. Runs database migrations
# 4. Starts the application
set -euo pipefail

# ---- Configuration ----
RESOLVED_REDIS_URL="${FO_REDIS_URL:-${REDIS_URL:-redis://localhost:6379/0}}"
DATA_DIR="${FO_DATA_DIR:-/data}"
LOG_LEVEL="${FO_LOG_LEVEL:-INFO}"
MAX_WORKERS="${FO_MAX_WORKERS:-4}"
HOST="${FO_HOST:-0.0.0.0}"
PORT="${FO_PORT:-8000}"
ENVIRONMENT="${FO_ENVIRONMENT:-prod}"
REDIS_WAIT_TIMEOUT="${REDIS_WAIT_TIMEOUT:-30}"

echo "=== File Organizer v2 ==="
echo "Environment: ${ENVIRONMENT}"
echo "Log Level:   ${LOG_LEVEL}"
echo "Workers:     ${MAX_WORKERS}"
echo "Bind:        ${HOST}:${PORT}"
echo "Data Dir:    ${DATA_DIR}"

# ---- Check Environment Variables ----
check_environment() {
    local errors=0

    if [ -z "${FO_ENVIRONMENT:-}" ]; then
        echo "WARNING: FO_ENVIRONMENT not set, defaulting to 'prod'"
    fi

    if [ -z "${FO_DATA_DIR:-}" ]; then
        echo "WARNING: FO_DATA_DIR not set, defaulting to '/data'"
    fi

    # Ensure data directory exists and is writable
    if [ ! -d "${DATA_DIR}" ]; then
        echo "Creating data directory: ${DATA_DIR}"
        mkdir -p "${DATA_DIR}" || {
            echo "ERROR: Cannot create data directory: ${DATA_DIR}"
            errors=$((errors + 1))
        }
    fi

    if [ ! -w "${DATA_DIR}" ]; then
        echo "ERROR: Data directory is not writable: ${DATA_DIR}"
        errors=$((errors + 1))
    fi

    if [ "${errors}" -gt 0 ]; then
        echo "ERROR: ${errors} environment check(s) failed"
        return 1
    fi

    echo "Environment checks passed"
    return 0
}

# ---- Wait for Redis ----
wait_for_redis() {
    # Extract host and port from Redis URL
    local redis_url="${RESOLVED_REDIS_URL}"

    # Remove redis:// prefix
    local redis_addr="${redis_url#redis://}"
    # Strip userinfo (user:password@) if present
    redis_addr="${redis_addr#*@}"
    # Remove database number suffix
    redis_addr="${redis_addr%%/*}"
    # Split host and port
    local redis_host="${redis_addr%%:*}"
    local redis_port="${redis_addr##*:}"

    # Default port if not specified
    if [ "${redis_host}" = "${redis_port}" ]; then
        redis_port="6379"
    fi

    echo "Waiting for Redis at ${redis_host}:${redis_port}..."

    local elapsed=0
    while [ "${elapsed}" -lt "${REDIS_WAIT_TIMEOUT}" ]; do
        if nc -z "${redis_host}" "${redis_port}" 2>/dev/null; then
            echo "Redis is ready (took ${elapsed}s)"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    echo "ERROR: Redis not available after ${REDIS_WAIT_TIMEOUT}s"
    return 1
}

# ---- Run Database Migrations ----
run_migrations() {
    echo "Running database migrations..."
    if command -v alembic >/dev/null 2>&1; then
        alembic upgrade head || {
            echo "WARNING: Migration failed or no migrations to run"
            return 0
        }
        echo "Migrations complete"
    else
        echo "Alembic not found, skipping migrations"
    fi
    return 0
}

# ---- Start Application ----
start_application() {
    echo "Starting File Organizer v2..."
    exec uvicorn \
        "file_organizer.cli:app" \
        --host "${HOST}" \
        --port "${PORT}" \
        --workers "${MAX_WORKERS}" \
        --log-level "${LOG_LEVEL,,}" \
        --proxy-headers \
        --forwarded-allow-ips="*"
}

# ---- Main ----
main() {
    check_environment || exit 1

    # Wait for Redis if URL is configured and not localhost in prod
    if [ "${ENVIRONMENT}" != "dev" ] || [ "${RESOLVED_REDIS_URL}" != "redis://localhost:6379/0" ]; then
        wait_for_redis || exit 1
    fi

    run_migrations || exit 1

    # Execute any additional command if passed as arguments
    if [ "$#" -gt 0 ]; then
        echo "Executing custom command: $*"
        exec "$@"
    else
        start_application
    fi
}

main "$@"
