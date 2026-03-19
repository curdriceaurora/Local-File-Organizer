#!/usr/bin/env bash
# tdd-gate: PreToolUse hook — enforce test-first for new src/file_organizer modules.
#
# Behaviour:
#   Write  (new file) — DENY if no test file exists for the target module.
#   Edit   (existing) — ALLOW but print an advisory if no test file is found.
#   All other paths   — pass through silently.
#
# Test discovery: looks for tests/<subdir>/test_<stem>.py OR tests/test_<stem>.py,
# falling back to a recursive find across tests/ so relocated test files still match.
#
# Exit 0 + empty stdout  → allow (Claude Code default).
# Exit 0 + JSON stdout   → allow or deny based on permissionDecision field.

set -euo pipefail

if ! command -v jq &>/dev/null; then
  echo "[tdd-gate] WARNING: jq not installed — hook disabled." >&2
  exit 0
fi

INPUT=$(cat)
read -r TOOL_NAME FILE_PATH < <(echo "$INPUT" | jq -r '[.tool_name // "", .tool_input.file_path // ""] | @tsv')

# Only care about Write and Edit on Python source files.
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
  exit 0
fi

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Normalise to absolute path if relative.
if [[ "$FILE_PATH" != /* ]]; then
  FILE_PATH="$(pwd)/$FILE_PATH"
fi

# Only gate files under src/file_organizer/.
if [[ "$FILE_PATH" != */src/file_organizer/*.py ]]; then
  exit 0
fi

# Never gate __init__.py — no test needed.
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" == "__init__.py" ]]; then
  exit 0
fi

# Derive project root — consistent with other project scripts.
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { exit 0; }
TESTS_DIR="$PROJECT_ROOT/tests"

# Stem of the source file, e.g. "text_processor".
STEM="${BASENAME%.py}"

# Relative sub-path under file_organizer, e.g. "services/text_processor.py".
REL="${FILE_PATH#"$PROJECT_ROOT/src/file_organizer/"}"
REL_DIR=$(dirname "$REL")
# Normalise "." (top-level module) to empty string so path joins are clean.
[[ "$REL_DIR" == "." ]] && REL_DIR=""

# Candidate test paths (order: mirrored subdir first, then flat, then recursive).
# Recursive fallback handles tests/ layouts that add a prefix layer (e.g. tests/unit/services/).
CANDIDATE_MIRRORED="$TESTS_DIR/${REL_DIR:+$REL_DIR/}test_${STEM}.py"
CANDIDATE_FLAT="$TESTS_DIR/test_${STEM}.py"

find_test() {
  # 2>/dev/null suppresses "No such file or directory" if TESTS_DIR doesn't exist yet.
  find "$TESTS_DIR" -name "test_${STEM}.py" 2>/dev/null | head -1
}

TEST_EXISTS=false
if [[ -f "$CANDIDATE_MIRRORED" ]] || [[ -f "$CANDIDATE_FLAT" ]]; then
  TEST_EXISTS=true
elif [[ -n "$(find_test)" ]]; then
  # Fallback: test exists but under a non-mirrored prefix (e.g. tests/unit/services/).
  TEST_EXISTS=true
fi

if $TEST_EXISTS; then
  exit 0
fi

# Determine if this is a new file (Write creating it) or editing an existing one.
IS_NEW=false
if [[ "$TOOL_NAME" == "Write" && ! -f "$FILE_PATH" ]]; then
  IS_NEW=true
fi

if $IS_NEW; then
  # Hard deny: must write test before implementation.
  REASON="[tdd-gate] No test file found for ${STEM}.py. Write the test in tests/ first, then create the implementation. Expected: $CANDIDATE_MIRRORED"
  jq -n \
    --arg reason "$REASON" \
    '{
      "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": $reason
      }
    }'
else
  # Advisory only: editing legacy code without tests.
  echo "[tdd-gate] ADVISORY: No test file found for ${STEM}.py. Consider adding tests in $CANDIDATE_MIRRORED before or alongside this change." >&2
  exit 0
fi
