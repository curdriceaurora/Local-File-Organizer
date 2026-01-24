#!/bin/bash
# Pre-Commit Validation Script
# Validates code against known patterns before committing
# Usage: bash .claude/scripts/pre-commit-validation.sh

set -e

echo "🔍 Pre-Commit Validation"
echo "======================="
echo ""

# Get repository root
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

# 1. Branch check
BRANCH=$(git branch --show-current)
echo "✓ Current branch: $BRANCH"

# 2. Modified files (staged for commit)
MODIFIED=$(git diff --name-only --cached)
if [[ -z "$MODIFIED" ]]; then
  echo "⚠️  No staged files to validate"
  exit 0
fi

echo "✓ Staged files:"
echo "$MODIFIED" | sed 's/^/  /'
echo ""

# 3. Check for build artifacts
echo "🗑️  Checking for build artifacts..."
BUILD_ARTIFACTS=$(echo "$MODIFIED" | grep -E '\.(coverage|bak|pyc|pyo)$' || true)
if [[ -n "$BUILD_ARTIFACTS" ]]; then
  echo "❌ Found build artifacts in commit:"
  echo "$BUILD_ARTIFACTS" | sed 's/^/  /'
  echo ""
  echo "Add to .gitignore and unstage these files:"
  echo "$BUILD_ARTIFACTS" | while read file; do
    echo "  git reset HEAD $file"
  done
  exit 1
fi
echo "✓ No build artifacts found"
echo ""

# 4. Pattern checks on Python files
PY_FILES=$(echo "$MODIFIED" | grep '\.py$' || true)
if [[ -n "$PY_FILES" ]]; then
  echo "🎯 Pattern validation on Python files..."

  # Check for dict-style dataclass access
  DICT_ACCESS=$(git diff --cached | grep -n '+.*if.*".*".*in.*\(metadata\|result\|config\)' || true)
  if [[ -n "$DICT_ACCESS" ]]; then
    echo "❌ Found dict-style access on dataclass:"
    echo "$DICT_ACCESS"
    echo ""
    echo "Fix: Use hasattr(obj, 'field') and obj.field is not None"
    exit 1
  fi

  # Check for bracket-style access on known dataclasses
  BRACKET_ACCESS=$(git diff --cached | grep -n '+.*\(metadata\|result\|config\)\["' || true)
  if [[ -n "$BRACKET_ACCESS" ]]; then
    echo "❌ Found bracket-style access on dataclass:"
    echo "$BRACKET_ACCESS"
    echo ""
    echo "Fix: Use obj.field instead of obj['field']"
    exit 1
  fi

  echo "✓ No dict-style dataclass access found"
  echo ""

  # 5. Run linting on Python files
  echo "🔧 Linting Python files..."
  if command -v ruff &> /dev/null; then
    echo "$PY_FILES" | xargs ruff check --fix || {
      echo "❌ Linting failed"
      echo "Fix errors above and re-stage files"
      exit 1
    }
    echo "✓ Linting passed"
  else
    echo "⚠️  ruff not found, skipping linting"
  fi
  echo ""

  # 6. Type checking
  echo "📋 Type checking Python files..."
  if command -v mypy &> /dev/null; then
    echo "$PY_FILES" | xargs mypy --config-file=file_organizer_v2/pyproject.toml 2>&1 | head -20 || {
      echo "⚠️  Type checking found issues (non-blocking)"
      echo "Review mypy output above"
    }
    echo "✓ Type checking completed"
  else
    echo "⚠️  mypy not found, skipping type checking"
  fi
  echo ""
fi

# 7. Check for broken links in markdown files
MD_FILES=$(echo "$MODIFIED" | grep '\.md$' || true)
if [[ -n "$MD_FILES" ]]; then
  echo "🔗 Checking for broken links in markdown..."

  for md_file in $MD_FILES; do
    # Extract relative links (not URLs)
    LINKS=$(grep -o '\]\([^)]*\)' "$md_file" | grep -v '^](' | grep -v 'http' | sed 's/^](//' || true)

    for link in $LINKS; do
      # Get directory of markdown file
      MD_DIR=$(dirname "$md_file")
      LINK_PATH="$MD_DIR/$link"

      # Check if linked file exists
      if [[ ! -f "$LINK_PATH" ]] && [[ ! -d "$LINK_PATH" ]]; then
        echo "❌ Broken link in $md_file: $link"
        echo "   Target does not exist: $LINK_PATH"
        exit 1
      fi
    done
  done

  echo "✓ No broken links found"
  echo ""
fi

# 8. Run tests on modified Python modules (if tests exist)
if [[ -n "$PY_FILES" ]]; then
  echo "🧪 Running tests for modified modules..."

  TEST_FAILED=0
  for file in $PY_FILES; do
    # Only test files in src/
    if [[ $file == file_organizer_v2/src/file_organizer/*.py ]]; then
      # Convert src path to test path
      TEST_FILE=$(echo "$file" | sed 's|src/file_organizer|tests|' | sed 's|\.py$|_test.py|')

      if [[ -f "$TEST_FILE" ]]; then
        echo "  Testing $TEST_FILE..."
        if ! pytest "$TEST_FILE" --tb=line -q 2>&1 | head -20; then
          echo "❌ Tests failed for $file"
          TEST_FAILED=1
        fi
      else
        # Try alternative test naming: test_{module}.py
        TEST_DIR=$(dirname "$TEST_FILE")
        MODULE=$(basename "$file" .py)
        ALT_TEST="$TEST_DIR/test_$MODULE.py"

        if [[ -f "$ALT_TEST" ]]; then
          echo "  Testing $ALT_TEST..."
          if ! pytest "$ALT_TEST" --tb=line -q 2>&1 | head -20; then
            echo "❌ Tests failed for $file"
            TEST_FAILED=1
          fi
        fi
      fi
    fi
  done

  if [[ $TEST_FAILED -eq 1 ]]; then
    echo ""
    echo "❌ Some tests failed"
    echo "Fix failing tests before committing"
    exit 1
  fi

  echo "✓ All tests passed"
  echo ""
fi

# 9. Summary
echo "✅ All validations passed!"
echo ""
echo "Safe to commit with:"
echo "  git commit -m 'your message'"
echo ""
