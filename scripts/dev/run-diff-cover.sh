#!/usr/bin/env bash
# scripts/dev/run-diff-cover.sh
#
# Pre-commit diff-coverage gate (mirrors CI "Diff coverage gate" step).
# Called by the diff-cover hook in .pre-commit-config.yaml.
#
# Behaviour:
#   1. Exits 0 immediately if no src/ or tests/ Python files are staged.
#   2. Exits 0 with a warning if origin/main merge base is unavailable
#      (shallow clone, offline, no remote).  Never blocks in that case.
#   3. Runs pytest with coverage — fails fast on any pytest error so that
#      diff-cover never runs against stale or incomplete coverage data.
#   4. Runs diff-cover; exits non-zero if changed lines are <80% covered.
#
# Prerequisites:
#   git fetch-depth: 0  (full history so origin/main is resolvable as a
#   merge base).  Shallow-clone users: run `git fetch --unshallow` once.
set -euo pipefail

# ----------------------------------------------------------------
# 1. Skip early when no src/ or tests/ Python files are staged
# ----------------------------------------------------------------
CHANGED=$(git diff --cached --name-only -- \
    'src/*.py' 'src/**/*.py' \
    'tests/*.py' 'tests/**/*.py' 2>/dev/null || true)

if [ -z "$CHANGED" ]; then
    exit 0
fi

# ----------------------------------------------------------------
# 2. Resolve merge base; skip gracefully if unavailable
# ----------------------------------------------------------------
if ! MERGE_BASE=$(git merge-base HEAD origin/main 2>/dev/null); then
    echo "diff-cover: skipping — origin/main merge base unavailable" \
         "(shallow clone or offline). Run 'git fetch --unshallow' to enable." >&2
    exit 0
fi

# ----------------------------------------------------------------
# 3. Generate coverage — fail fast; never suppress pytest output
# ----------------------------------------------------------------
pytest tests/ -q \
    --override-ini="addopts=" \
    --cov=file_organizer \
    --cov-report=xml:coverage.xml \
    --no-header \
    -m "not benchmark and not e2e and not integration"

# ----------------------------------------------------------------
# 4. Diff-cover gate
# ----------------------------------------------------------------
diff-cover coverage.xml \
    --compare-branch="$MERGE_BASE" \
    --fail-under=80 \
    --quiet
