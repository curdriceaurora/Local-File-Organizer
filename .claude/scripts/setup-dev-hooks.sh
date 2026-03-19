#!/usr/bin/env bash
# setup-dev-hooks.sh — activate project Claude Code hooks in .claude/settings.json.
#
# Run once after cloning (or when .claude/hooks/ changes):
#   bash .claude/scripts/setup-dev-hooks.sh
#
# What it does:
#   Merges the project's PreToolUse hook registration into .claude/settings.json,
#   preserving any existing settings (model, permissions, etc.) already in the file.
#
# Safe to re-run — idempotent (won't add duplicate hook entries).

set -euo pipefail

SETTINGS=".claude/settings.json"
HOOK_CMD="bash .claude/hooks/tdd-gate.sh"

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required. Install: brew install jq" >&2
  exit 1
fi

# Read settings, defaulting to empty object if file doesn't exist yet.
if [[ -f "$SETTINGS" ]]; then
  CURRENT=$(cat "$SETTINGS")
else
  CURRENT='{}'
fi

# Check if the hook is already registered (idempotency).
ALREADY=$(echo "$CURRENT" | jq --arg cmd "$HOOK_CMD" '
  .hooks.PreToolUse // [] |
  map(.hooks // []) |
  flatten |
  map(select(.command == $cmd)) |
  length
')

if [[ "$ALREADY" -gt 0 ]]; then
  echo "tdd-gate hook already registered in $SETTINGS — nothing to do."
  exit 0
fi

# Merge the hook entry into existing settings.
# "matcher" is a regex alternation matching Claude Code tool names (Write|Edit).
UPDATED=$(echo "$CURRENT" | jq --arg cmd "$HOOK_CMD" '
  .hooks.PreToolUse = ((.hooks.PreToolUse // []) + [{
    "matcher": "Write|Edit",
    "hooks": [{
      "type": "command",
      "command": $cmd,
      "timeout": 10
    }]
  }])
')

TMP=$(mktemp "${SETTINGS}.XXXXXX")
echo "$UPDATED" > "$TMP" || { rm -f "$TMP"; echo "ERROR: failed to write $SETTINGS" >&2; exit 1; }
mv "$TMP" "$SETTINGS"
echo "✅ tdd-gate hook registered in $SETTINGS"
echo "   Fires on Write/Edit to src/file_organizer/**/*.py"
echo "   New files without tests will be blocked. Edits get advisory warnings."
