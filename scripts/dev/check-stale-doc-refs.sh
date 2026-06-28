#!/usr/bin/env bash
# check-stale-doc-refs.sh — Detect documentation references to files/classes that no longer exist.
# Run: bash scripts/dev/check-stale-doc-refs.sh [--staged-only]
# Exit code 0 = clean, 1 = stale references found

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
STAGED_ONLY=false
ERRORS=0

if [[ "${1:-}" == "--staged-only" ]]; then
  STAGED_ONLY=true
fi

# Collect markdown files to check
if $STAGED_ONLY; then
  MD_FILES=$(git diff --cached --name-only --diff-filter=ACM -- '*.md' || true)
else
  MD_FILES=$(find "$REPO_ROOT" -name '*.md' \
    -not -path '*/node_modules/*' \
    -not -path '*/.git/*' \
    -not -path '*/docs/plans/*' \
    | sed "s|^$REPO_ROOT/||")
fi

if [[ -z "$MD_FILES" ]]; then
  echo "✓ No markdown files to check"
  exit 0
fi

echo "🔍 Checking documentation references..."
echo ""

# --- Check 1: Source file references ---
# Match patterns like src/file_organizer/foo/bar.py or interfaces/engine.py
while IFS= read -r md_file; do
  [[ -z "$md_file" ]] && continue
  full_path="$REPO_ROOT/$md_file"
  [[ -f "$full_path" ]] || continue

  # Extract Python file references (src/... paths ending in .py)
  # Skip lines inside code blocks (examples/templates) — they use placeholder paths
  while IFS=: read -r line_num line_content; do
    # Skip lines that look like examples (contain my_service, your_, example_, etc.)
    if echo "$line_content" | grep -qE 'my_service|your_|example_|placeholder'; then
      continue
    fi
    # Pull out src/...py references
    refs=$(echo "$line_content" | grep -oE 'src/file_organizer/[a-zA-Z0-9_/]+\.py' || true)
    for ref in $refs; do
      if [[ ! -f "$REPO_ROOT/$ref" ]]; then
        echo "  ❌ $md_file:$line_num → $ref (FILE MISSING)"
        ERRORS=$((ERRORS + 1))
      fi
    done
  done < <(grep -n 'src/file_organizer/[a-zA-Z0-9_/]*\.py' "$full_path" 2>/dev/null || true)
done <<< "$MD_FILES"

# --- Check 2: Class/Protocol references that were known-deleted ---
# Maintain a list of intentionally deleted symbols + their old locations
DELETED_SYMBOLS=(
  "EngineProtocol:interfaces/engine.py"
)

for entry in "${DELETED_SYMBOLS[@]}"; do
  symbol="${entry%%:*}"
  old_file="${entry##*:}"

  while IFS= read -r md_file; do
    [[ -z "$md_file" ]] && continue
    full_path="$REPO_ROOT/$md_file"
    [[ -f "$full_path" ]] || continue

    hits=$(grep -n "$symbol" "$full_path" 2>/dev/null | grep -v "deleted\|DELETED\|removed\|Removed\|zero implementors\|deferred\|Deferred" || true)
    if [[ -n "$hits" ]]; then
      while IFS= read -r hit; do
        line_num=$(echo "$hit" | cut -d: -f1)
        echo "  ⚠️  $md_file:$line_num → references deleted symbol '$symbol' (was in $old_file)"
        ERRORS=$((ERRORS + 1))
      done <<< "$hits"
    fi
  done <<< "$MD_FILES"
done

# --- Check 3: Method references that don't exist ---
# Known false method references (add as discovered)
FALSE_METHODS=(
  "ConfigManager.get_allowed_dirs"
)

for method in "${FALSE_METHODS[@]}"; do
  class_name="${method%%.*}"
  method_name="${method##*.}"

  while IFS= read -r md_file; do
    [[ -z "$md_file" ]] && continue
    full_path="$REPO_ROOT/$md_file"
    [[ -f "$full_path" ]] || continue

    hits=$(grep -n "$method" "$full_path" 2>/dev/null || true)
    if [[ -n "$hits" ]]; then
      # Verify method still doesn't exist
      if ! grep -rq "def $method_name" "$REPO_ROOT/src/" 2>/dev/null; then
        while IFS= read -r hit; do
          line_num=$(echo "$hit" | cut -d: -f1)
          echo "  ❌ $md_file:$line_num → references non-existent method '$method'"
          ERRORS=$((ERRORS + 1))
        done <<< "$hits"
      fi
    fi
  done <<< "$MD_FILES"
done

echo ""
if [[ $ERRORS -gt 0 ]]; then
  echo "❌ Found $ERRORS stale reference(s) in documentation"
  echo "   Fix these before committing, or add to DELETED_SYMBOLS/FALSE_METHODS if intentional."
  exit 1
else
  echo "✓ No stale documentation references found"
  exit 0
fi
