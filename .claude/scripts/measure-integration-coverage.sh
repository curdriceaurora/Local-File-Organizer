#!/usr/bin/env bash
set -euo pipefail

# Install optional search extras so rank-bm25 / sklearn tests run (not skip).
# Uses --quiet to suppress pip noise; harmless if already installed.
pip install -e ".[search]" --quiet

coverage erase
pytest tests/ -m "integration" \
    --strict-markers \
    --cov=file_organizer \
    --cov-branch \
    --cov-report=term-missing \
    --override-ini="addopts=" \
    "$@"
