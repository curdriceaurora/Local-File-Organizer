#!/usr/bin/env bash
# Run mypy on changed files, but only those inside the gated scope.
# Scope matches CI gate: src/file_organizer/models/
# Extend this list as more modules reach type-clean status.
set -euo pipefail

GATED_PREFIX="src/file_organizer/models/"
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

# Convert newline-separated files to array and run mypy
set -f  # disable globbing
.venv/bin/mypy $(echo "$files" | sort -u)
