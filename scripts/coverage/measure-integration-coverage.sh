#!/usr/bin/env bash
set -euo pipefail

# Install optional search extras so rank-bm25 / sklearn tests run (not skip).
# Uses --quiet to suppress pip noise; harmless if already installed.
uv pip install -e ".[search]" --quiet

coverage erase
# Conformance is integration-level: it drives the canonical service and every adapter end to end.
# It carries its own `conformance` marker for the required Conformance workflow, so counting it here
# keeps the integration coverage measurement honest for the new canonical modules it exercises.
pytest tests/ -m "integration or conformance" \
    --strict-markers \
    --cov=file_organizer \
    --cov-branch \
    --cov-report=term-missing \
    --override-ini="addopts=" \
    "$@"
