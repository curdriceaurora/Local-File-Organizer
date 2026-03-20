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
# Coverage ratchet gates (local enforcement — catches drift before CI sees it)
# Gates are set just below the actual baseline to prevent regression while
# the ratchet epic (#857) raises them to final targets.
# ---------------------------------------------------------------------------

echo "▶ Docstring coverage gate (≥95%)"
interrogate -v src/ --fail-under 95 -q
echo "✓ Docstring coverage"
echo ""

echo "▶ Unit test code coverage gate (≥93% branch)"
pytest tests/ -m "unit and not benchmark" \
  --cov=file_organizer --cov-fail-under=93 --no-cov-on-fail \
  -q -n=auto --timeout=30 --override-ini="addopts="
echo "✓ Unit test coverage"
echo ""

echo "▶ Integration test coverage gate (≥30% branch)"
rm -f coverage.xml
pytest tests/ -m "integration and not benchmark" \
  --cov=file_organizer --cov-fail-under=30 --no-cov-on-fail \
  --cov-report=xml:coverage.xml \
  -q --timeout=30 --override-ini="addopts="
echo "✓ Integration test coverage"
echo ""

# Diff coverage gate (only on branches with main for comparison)
# Detects if we're in a branch context (not detached HEAD)
current_branch=$(git branch --show-current 2>/dev/null)
if [[ -n "$current_branch" && "$current_branch" != "HEAD" && -f coverage.xml ]]; then
  echo "▶ Diff coverage gate (≥80% on changed lines)"

  # Ensure origin/main is available for comparison
  if ! git rev-parse origin/main >/dev/null 2>&1; then
    git fetch origin main 2>/dev/null || true
  fi

  # Run diff-cover if available
  if command -v diff-cover &>/dev/null; then
    diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
    echo "✓ Diff coverage gate"
    echo ""
  else
    echo "ℹ diff-cover not installed (optional; skipping local check)"
    echo "  Install: pip install diff-cover"
    echo ""
  fi
else
  echo "ℹ Skipping diff coverage gate (no branch context or no coverage.xml)"
  echo ""
fi

if git diff --cached -- '*.py' '.github/workflows/*.yml' 2>/dev/null | grep -q 'GITHUB_'; then
  echo "ℹ Detected GitHub-environment branching in staged changes."
  echo "  Guardrail tests in tests/ci must cover both local and PR CI contexts."
  echo ""
fi

echo "Guardrail validation passed."
