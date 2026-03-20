#!/usr/bin/env bash
set -euo pipefail

coverage erase
pytest tests/ -m "integration" \
    --strict-markers \
    --cov=file_organizer \
    --cov-branch \
    --cov-report=term-missing \
    --override-ini="addopts=" \
    "$@"
