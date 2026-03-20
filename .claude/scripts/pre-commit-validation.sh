#!/bin/bash
# Canonical pre-PR guardrail orchestrator.
# This script does not define blocking policy itself. It runs the enforced
# layers that own guardrail policy:
#   - .pre-commit-config.yaml for staged-file/mechanical checks
#   - tests/ci for semantic guardrail checks
#   - .github/workflows/ci.yml for runtime support required in PR CI

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

run_step() {
  local label="$1"
  shift

  echo "▶ $label"
  "$@"
  echo "✓ $label"
  echo ""
}

print_files() {
  local mode="$1"
  shift

  if [[ "$#" -eq 0 ]]; then
    echo "  (none)"
    return
  fi

  echo "  Source: $mode"
  printf '  %s\n' "$@"
}

collect_changed_files() {
  local tracked_files=()
  local untracked_files=()

  if git diff --cached --quiet; then
    mapfile -t tracked_files < <(git diff --name-only --diff-filter=ACMR HEAD 2>/dev/null || true)
    mapfile -t untracked_files < <(git ls-files --others --exclude-standard)
    changed_files=("${tracked_files[@]}" "${untracked_files[@]}")
    changed_mode="working tree vs HEAD + untracked"
  else
    mapfile -t changed_files < <(git diff --cached --name-only --diff-filter=ACMR)
    changed_mode="staged diff"
  fi
}

collect_changed_files

echo "Pre-PR Guardrail Validation"
echo "==========================="
echo "Branch: $(git branch --show-current)"
echo ""
print_files "$changed_mode" "${changed_files[@]}"
echo ""

run_step "Validate pre-commit configuration" pre-commit validate-config

run_step "Run pre-commit on all files" pre-commit run --all-files

run_step "Run semantic CI guardrails" pytest tests/ci -q --no-cov --override-ini="addopts="

# ---------------------------------------------------------------------------
# Docstring coverage gate (fast, no optional deps)
# ---------------------------------------------------------------------------

echo "▶ Docstring coverage gate (≥95%)"
interrogate -v src/ --fail-under 95 -q
echo "✓ Docstring coverage"
echo ""

# ---------------------------------------------------------------------------
# Coverage floor gates (unit ≥93% branch, integration ≥30% branch) are
# enforced by CI on main-branch pushes — NOT here.
#
# Rationale (issue #914): the unit gate ran `pytest tests/ -m "unit"` (~80 s)
# and included optional-dep tests (rank-bm25, scikit-learn) that fail for
# anyone without [search] extras, creating spurious noise on every commit.
# Coverage is authoritative in ci.yml; local pre-commit stays fast & clean.
# ---------------------------------------------------------------------------

if git diff --cached -- '*.py' '.github/workflows/*.yml' 2>/dev/null | grep -q 'GITHUB_'; then
  echo "ℹ Detected GitHub-environment branching in staged changes."
  echo "  Guardrail tests in tests/ci must cover both local and PR CI contexts."
  echo ""
fi

echo "Guardrail validation passed."
