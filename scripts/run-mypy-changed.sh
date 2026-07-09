#!/usr/bin/env bash
# Run mypy on changed files, but only those inside the gated scope.
# Scope matches CI gate: src/file_organizer/ (widened WP-6.4, #1243)
set -euo pipefail

GATED_PREFIX="src/file_organizer/"
# mypy 1.20.x INTERNAL ERRORs (crashes on exit, after a clean "no issues
# found") when files under src/file_organizer/models/ are passed as explicit
# analysis targets in this --follow-imports=silent invocation. The version cap
# is documented in pyproject.toml. These modules are still fully type-checked
# by the `type-check` CI job (`mypy src/file_organizer/`, follow_imports=normal),
# which does not trip the crash. Remove this skip once the upstream mypy bug is
# fixed and the cap is lifted.
MODELS_PREFIX="src/file_organizer/models/"
files=""

for file in "$@"; do
  if [ "${file#"$GATED_PREFIX"}" != "$file" ]; then
    if [ "${file#"$MODELS_PREFIX"}" != "$file" ]; then
      continue
    fi
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
