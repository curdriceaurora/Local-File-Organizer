#!/usr/bin/env bash
# Run mypy on changed files, but only those inside the gated scope.
# Scope matches CI gate: src/file_organizer/ (widened WP-6.4, #1243)
set -euo pipefail

GATED_PREFIX="src/file_organizer/"
files=""

for file in "$@"; do
  if [ "${file#"$GATED_PREFIX"}" != "$file" ]; then
    if [ -n "$files" ]; then
      files="$files"$'\n'"$file"
    else
      files="$file"
    fi
  fi
done

if [ -z "$files" ]; then
  exit 0
fi

files_sorted=()
while IFS= read -r line; do
  files_sorted+=("$line")
done < <(printf '%s\n' "$files" | sort -u)
MYPY=$(.venv/bin/mypy --version >/dev/null 2>&1 && echo .venv/bin/mypy || echo mypy)
$MYPY --follow-imports=silent -- "${files_sorted[@]}"
