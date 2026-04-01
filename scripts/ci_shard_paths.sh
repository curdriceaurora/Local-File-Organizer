#!/usr/bin/env bash
# ci_shard_paths.sh — single source of truth for the 4-shard test-directory split.
#
# Usage: bash scripts/ci_shard_paths.sh <shard_number>
# Prints a space-separated list of pytest path arguments to stdout.
#
# Both ci.yml (push) and ci-full.yml (daily) import this script so the mapping
# stays in sync.  When test directories are added or moved, update ONLY this
# file; both pipelines will pick up the change automatically.
#
# Shard sizing goal: ~4 000 test functions per shard, keeping per-xdist-worker
# RAM below the threshold that triggers Python GC-finaliser hangs (~1.3 GB/worker).

set -euo pipefail

SHARD="${1:-}"
if [[ -z "$SHARD" ]]; then
    echo "Usage: $0 <shard_number>" >&2
    exit 1
fi

case "$SHARD" in
    1) PATHS="tests/integration" ;;
    2) PATHS="tests/services tests/models tests/events tests/optimization" ;;
    3) PATHS="tests/api tests/cli tests/methodologies tests/web tests/ci tests/unit" ;;
    4) PATHS="tests/plugins tests/tui tests/parallel tests/pipeline tests/utils tests/undo tests/history tests/daemon tests/deploy tests/watcher tests/updater tests/core tests/config tests/client tests/docs tests/desktop tests/integrations tests/test_*.py" ;;
    *)
        echo "Unknown shard: $SHARD (valid: 1-4)" >&2
        exit 1
        ;;
esac

export PATHS
echo "$PATHS"
