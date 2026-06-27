#!/usr/bin/env bash
# Retry a pip install command up to 3 times with a 5s backoff, to absorb
# transient PyPI/network failures in CI (WP-6.3, #1242).
#
# Usage: bash scripts/pip_install_retry.sh <pip install args...>
# Example: bash scripts/pip_install_retry.sh -e ".[dev,search]"
set -euo pipefail

max_attempts=3
attempt=1

until pip install "$@"; do
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "pip install failed after $max_attempts attempts: pip install $*" >&2
    exit 1
  fi
  echo "pip install failed (attempt $attempt/$max_attempts), retrying in 5s..." >&2
  attempt=$((attempt + 1))
  sleep 5
done
