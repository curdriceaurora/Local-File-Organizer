#!/usr/bin/env bash
# scripts/dev/run-diff-cover.sh
#
# Pre-push diff-coverage gate (mirrors CI's 3.11-leg "Diff coverage gate" step).
# Called by the diff-cover hook in .pre-commit-config.yaml.
#
# Behaviour (issue #1767 item 3 — moved from pre-commit to pre-push, and
# scoped to the diff instead of re-running the near-full suite):
#   1. Exits 0 immediately if no src/ or tests/ Python files changed since
#      origin/main.
#   2. Exits 0 with a warning if origin/main merge base is unavailable
#      (shallow clone, offline, no remote).  Never blocks in that case.
#   3. Maps each changed src/ file to related test files: same-named test
#      directory (e.g. src/file_organizer/services/deduplication/extractor.py
#      -> tests/services/deduplication/) filtered by substring match on stem
#      (test_dedup_extractor*.py), plus any test files changed directly --
#      and runs pytest scoped to just those, instead of the whole suite.
#   4. Fails OPEN, not closed: if no related tests are found for any changed
#      file, this hook warns and skips rather than blocking the push. CI's
#      3.11-leg diff-cover step (running the full suite) is the actual
#      enforced gate; this hook is a fast local approximation of it.
#   5. Runs diff-cover; exits non-zero if changed lines are <80% covered.
#
# Prerequisites:
#   git fetch-depth: 0  (full history so origin/main is resolvable as a
#   merge base).  Shallow-clone users: run `git fetch --unshallow` once.
set -euo pipefail

# ----------------------------------------------------------------
# 1. Resolve merge base; skip gracefully if unavailable
# ----------------------------------------------------------------
if ! MERGE_BASE=$(git merge-base HEAD origin/main 2>/dev/null); then
    echo "diff-cover: skipping — origin/main merge base unavailable" \
         "(shallow clone or offline). Run 'git fetch --unshallow' to enable." >&2
    exit 0
fi

# ----------------------------------------------------------------
# 2. Skip early when no src/ or tests/ Python files changed vs. origin/main
# ----------------------------------------------------------------
CHANGED=$(git diff --name-only "$MERGE_BASE"...HEAD -- \
    'src/*.py' 'src/**/*.py' \
    'tests/*.py' 'tests/**/*.py' 2>/dev/null || true)

if [ -z "$CHANGED" ]; then
    exit 0
fi

# ----------------------------------------------------------------
# 3. Map changed files to related test paths: same-named test directory
#    (e.g. src/file_organizer/services/deduplication/extractor.py ->
#    tests/services/deduplication/) filtered by substring match on stem
#    (test_dedup_extractor*.py, not an exact-stem match). Directory-scoping
#    first matters: a bare whole-tree substring search on a common stem like
#    "extractor" or "compat" pulls in dozens of unrelated test files across
#    the whole suite, which defeats the point of scoping down at all.
# ----------------------------------------------------------------
TEST_PATHS=()
UNMAPPED=()

while IFS= read -r file; do
    [ -z "$file" ] && continue
    case "$file" in
        tests/*test_*.py)
            # A changed test file is directly in scope.
            TEST_PATHS+=("$file")
            continue
            ;;
    esac
    case "$file" in
        src/*.py)
            stem=$(basename "$file" .py)
            [ "$stem" = "__init__" ] && continue
            parent=$(basename "$(dirname "$file")")
            candidate_dirs=$(find tests -type d -name "$parent" 2>/dev/null)
            matches=""
            if [ -n "$candidate_dirs" ]; then
                matches=$(while IFS= read -r d; do
                    find "$d" -maxdepth 1 -name 'test_*.py' 2>/dev/null
                done <<< "$candidate_dirs" | while IFS= read -r t; do
                    tstem=$(basename "$t" .py)
                    case "$tstem" in
                        *"$stem"*) echo "$t" ;;
                    esac
                done)
            fi
            if [ -n "$matches" ]; then
                while IFS= read -r m; do
                    TEST_PATHS+=("$m")
                done <<< "$matches"
            else
                UNMAPPED+=("$file")
            fi
            ;;
    esac
done <<< "$CHANGED"

if [ ${#TEST_PATHS[@]} -eq 0 ]; then
    echo "diff-cover: skipping — no related test files found for the changed" \
         "diff (checked: $CHANGED). CI's diff-cover step on the 3.11 leg" \
         "remains the enforced gate." >&2
    exit 0
fi

if [ ${#UNMAPPED[@]} -gt 0 ]; then
    echo "diff-cover: no test-file match found by naming convention for:" \
         "${UNMAPPED[*]} — running the tests found for the rest of the diff;" \
         "these files' coverage will only be checked by CI." >&2
fi

# De-duplicate TEST_PATHS
mapfile -t TEST_PATHS < <(printf '%s\n' "${TEST_PATHS[@]}" | sort -u)

# ----------------------------------------------------------------
# 4. Generate coverage over just the scoped tests — fail fast; never
#    suppress pytest output
# ----------------------------------------------------------------
pytest "${TEST_PATHS[@]}" -q \
    --override-ini="addopts=" \
    --cov=file_organizer \
    --cov-report=xml:coverage.xml \
    --no-header \
    -m "not benchmark and not e2e and not integration"

# ----------------------------------------------------------------
# 5. Diff-cover gate
# ----------------------------------------------------------------
diff-cover coverage.xml \
    --compare-branch="$MERGE_BASE" \
    --fail-under=80 \
    --quiet
