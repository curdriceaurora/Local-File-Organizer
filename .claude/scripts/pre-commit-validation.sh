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

# 3. Check for build artifacts (only for added/modified files, not deletions)
echo "🗑️  Checking for build artifacts..."
BUILD_ARTIFACTS=$(git diff --cached --name-status | grep -E '^[AM]' | awk '{print $2}' | grep -E '\.(coverage|bak|pyc|pyo)$' || true)
if [[ -n "$BUILD_ARTIFACTS" ]]; then
  echo "❌ Found build artifacts in commit:"
  echo "$BUILD_ARTIFACTS" | sed 's/^/  /'
  echo ""
  echo "Add to .gitignore and unstage these files:"
  echo "$BUILD_ARTIFACTS" | while read -r file; do
    echo "  git reset HEAD $file"
  done
  exit 1
fi
echo "✓ No build artifacts found"
echo ""

# 3.5. Check for absolute paths in all file types
echo "🔍 Checking for absolute paths..."
ABSOLUTE_PATHS=$(git diff --cached | grep -E '^\+.*(/Users/|/home/|C:\\Users\\)' | grep -v '.claude/rules/' | grep -v '.claude/scripts/' || true)
if [[ -n "$ABSOLUTE_PATHS" ]]; then
  echo "❌ Found hardcoded absolute paths:"
  echo "$ABSOLUTE_PATHS" | sed 's/^/  /'
  echo ""
  echo "Fix: Use relative paths (e.g., ../project-name/file.py or ./path/to/file)"
  echo "     instead of absolute paths like /Users/username/..."
  exit 1
fi
echo "✓ No absolute paths found"
echo ""

# 4. Pattern checks on Python files
PY_FILES=$(git diff --name-only --cached -- '*.py' || true)
if [[ -n "$PY_FILES" ]]; then
  echo "🎯 Pattern validation on Python files..."
  PY_DIFF=$(git diff --cached -- '*.py')

  # Check for dict-style dataclass access
  DICT_ACCESS=$(echo "$PY_DIFF" | grep -n '+.*if.*".*".*in.*\(metadata\|result\|config\)' || true)
  if [[ -n "$DICT_ACCESS" ]]; then
    echo "❌ Found dict-style access on dataclass:"
    echo "$DICT_ACCESS"
    echo ""
    echo "Fix: Use hasattr(obj, 'field') and obj.field is not None"
    exit 1
  fi

  # Check for bracket-style access on known dataclasses
  BRACKET_ACCESS=$(echo "$PY_DIFF" | grep -n '+.*\(metadata\|result\|config\)\["' || true)
  if [[ -n "$BRACKET_ACCESS" ]]; then
    echo "❌ Found bracket-style access on dataclass:"
    echo "$BRACKET_ACCESS"
    echo ""
    echo "Fix: Use obj.field instead of obj['field']"
    exit 1
  fi

  echo "✓ No dict-style dataclass access found"
  echo ""

  # 5. Run linting on Python files (without --fix to avoid untracked changes)
  echo "🔧 Linting Python files..."
  if command -v ruff &> /dev/null; then
    if ! echo "$PY_FILES" | xargs ruff check; then
      echo "❌ Linting failed"
      echo "Fix errors above, then re-stage files"
      exit 1
    fi
    echo "✓ Linting passed"
    echo ""
    echo "🔧 Running full ruff check..."
    if ! ruff check .; then
      echo "❌ Full ruff check failed"
      echo "Fix errors above, then re-stage files"
      exit 1
    fi
    echo "✓ Full ruff check passed"
    echo ""
    echo "🔧 Running type annotation lint on src/..."
    PY_SRC_FILES=$(echo "$PY_FILES" | grep '^src/' || true)
    if [[ -n "$PY_SRC_FILES" ]]; then
      if ! echo "$PY_SRC_FILES" | xargs ruff check --select ANN; then
        echo "❌ Type annotation lint failed"
        echo "Add missing type annotations in src/ files"
        exit 1
      fi
      echo "✓ Type annotation lint passed"
    else
      echo "✓ No src/ Python files staged for type annotation lint"
    fi
  else
    echo "⚠️  ruff not found, skipping linting"
  fi
  echo ""

  # 6. Type checking
  echo "📋 Type checking Python files..."
  if command -v mypy &> /dev/null; then
    if ! echo "$PY_FILES" | xargs mypy --config-file=pyproject.toml; then
      echo "❌ Type checking failed (blocking)"
      echo "Fix type errors above, then re-stage files"
      exit 1
    fi
    echo "✓ Type checking passed"
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
    # Remove code blocks first, then extract links
    # Match ]( followed by anything except http, excluding anchor links
    LINKS=$(sed '/```/,/```/d' "$md_file" | grep -oE '\]\([^)]+\)' | grep -v 'http' | sed 's/^\](//' | sed 's/)$//' || true)

    for link in $LINKS; do
      # Skip anchor links (start with #)
      if [[ "$link" == \#* ]]; then
        continue
      fi

      # Skip empty links
      if [[ -z "$link" ]]; then
        continue
      fi

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

# 7a-2. Docs format conformity checks (admin docs conventions)
DOCS_FILES=$(echo "$MODIFIED" | grep '^docs/.*\.md$' || true)
if [[ -n "$DOCS_FILES" ]]; then
  echo "Checking docs format conformity..."
  DOCS_ISSUES=0

  for doc_file in $DOCS_FILES; do
    if [[ ! -f "$doc_file" ]]; then
      continue
    fi

    # Must start with "# Title" (no YAML frontmatter)
    FIRST_LINE=$(head -1 "$doc_file")
    if [[ "$FIRST_LINE" == "---" ]]; then
      echo "❌ $doc_file: Has YAML frontmatter (docs/ files must start with # Title)"
      DOCS_ISSUES=1
    elif [[ "$FIRST_LINE" != "# "* ]]; then
      echo "❌ $doc_file: First line must be a # heading, got: $FIRST_LINE"
      DOCS_ISSUES=1
    fi

    # Opening code fences must have language annotation
    # Track fence state: odd occurrences are openers, even are closers
    BARE_OPENERS=$(awk '/^```/{count++; if(count%2==1 && $0=="```") print NR": "$0}' "$doc_file")
    if [[ -n "$BARE_OPENERS" ]]; then
      echo "❌ $doc_file: Opening code fences without language annotation found"
      echo "$BARE_OPENERS" | sed 's/^/    /'
      DOCS_ISSUES=1
    fi
  done

  if [[ $DOCS_ISSUES -eq 1 ]]; then
    echo ""
    echo "❌ Docs format conformity checks failed"
    exit 1
  fi
  echo "✓ Docs format conformity checks passed"
  echo ""
fi

# 7b. Run ALL staged test files directly (catches new/modified tests even
#     when no src/ file is staged — the blind spot that caused PR #415 failures)
STAGED_TEST_FILES=$(git diff --name-only --cached -- 'tests/**/*.py' | grep -E '^tests/.*test_.*\.py$' || true)
if [[ -n "$STAGED_TEST_FILES" ]]; then
  echo "🧪 Running staged test files directly..."
  STAGED_TEST_FAILED=0
  for test_file in $STAGED_TEST_FILES; do
    if [[ -f "$test_file" ]]; then
      echo "  Testing $test_file..."
      if ! pytest "$test_file" --tb=short -q --override-ini="addopts="; then
        echo "❌ Test file $test_file has failures"
        STAGED_TEST_FAILED=1
      fi
    fi
  done
  if [[ $STAGED_TEST_FAILED -eq 1 ]]; then
    echo ""
    echo "❌ Some staged test files have failures"
    echo "Fix failing tests before committing"
    exit 1
  fi
  echo "✓ All staged test files passed"
  echo ""
fi

# 7c. Validate mock @patch targets in staged test files resolve to real attributes
#     Uses the Python that has the project installed (same one pytest uses).
if [[ -n "$STAGED_TEST_FILES" ]]; then
  # Find a Python that can import the project (try python3, then the one pytest uses)
  PROJ_PYTHON=""
  if python3 -c "import file_organizer" 2>/dev/null; then
    PROJ_PYTHON="python3"
  elif command -v pytest &>/dev/null; then
    PYTEST_PYTHON=$(head -1 "$(command -v pytest)" | sed 's/^#!//')
    if [[ -n "$PYTEST_PYTHON" ]] && $PYTEST_PYTHON -c "import file_organizer" 2>/dev/null; then
      PROJ_PYTHON="$PYTEST_PYTHON"
    fi
  fi

  if [[ -z "$PROJ_PYTHON" ]]; then
    echo "⚠️  Skipping mock target validation (project not installed in any Python)"
  else
    echo "🎯 Validating mock patch targets..."
    PATCH_ISSUES=0
    for test_file in $STAGED_TEST_FILES; do
      # Extract patch targets from newly-added lines (portable: uses Python, not grep -oP)
      PATCH_TARGETS=$($PROJ_PYTHON -c "
import re, sys
text = sys.stdin.read()
for m in re.finditer(r'^\+.*@patch\(\"([^\"]+)\"', text, re.MULTILINE):
    print(m.group(1))
" < <(git diff --cached -- "$test_file") 2>/dev/null || true)
      for target in $PATCH_TARGETS; do
        # Resolve target: import longest module prefix, then walk remaining attributes
        if ! $PROJ_PYTHON - "$target" <<'VALIDATE_EOF'
import importlib, sys
target = sys.argv[1]
parts = target.split(".")
for i in range(len(parts), 0, -1):
    try:
        module = importlib.import_module(".".join(parts[:i]))
    except ImportError:
        continue
    obj = module
    for attr in parts[i:]:
        try:
            obj = getattr(obj, attr)
        except AttributeError:
            sys.exit(1)
    sys.exit(0)
sys.exit(1)
VALIDATE_EOF
        then
          echo "❌ Invalid mock target in $test_file: $target"
          echo "   Target could not be resolved to an importable object"
          echo "   If the function uses a local import, patch at the source module instead"
          PATCH_ISSUES=1
        fi
      done
    done
    if [[ $PATCH_ISSUES -eq 1 ]]; then
      echo ""
      echo "Fix: Patch where the name is DEFINED, not where it's IMPORTED locally"
      echo "See: https://docs.python.org/3/library/unittest.mock.html#where-to-patch"
      exit 1
    fi
    echo "✓ All mock patch targets are valid"
    echo ""
  fi
fi

# 8. Run tests on modified Python modules (if tests exist)
if [[ -n "$PY_FILES" ]]; then
  echo "🧪 Running tests for modified modules..."

  TEST_FAILED=0
  for file in $PY_FILES; do
    # Only test files in src/ (match any depth with glob)
    if [[ $file == src/file_organizer/* ]] && [[ $file == *.py ]]; then
      # Convert src path to test path
      TEST_FILE=${file/src\/file_organizer/tests}
      TEST_FILE=${TEST_FILE/.py/_test.py}

      if [[ -f "$TEST_FILE" ]]; then
        echo "  Testing $TEST_FILE..."
        # Capture pytest output and exit code separately
        if ! pytest "$TEST_FILE" --tb=line -q; then
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
          if ! pytest "$ALT_TEST" --tb=line -q; then
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

  # 8b. Run focused security tests when related modules change
  echo "🔐 Checking if security-focused tests are needed..."
  SECURITY_FILES_REGEX="src/file_organizer/api/(middleware|rate_limit|api_keys|config)\\.py|tests/test_api_security\\.py"
  if echo "$MODIFIED" | grep -Eq "$SECURITY_FILES_REGEX"; then
    echo "🧪 Running API security tests..."
    if ! pytest tests/test_api_security.py -q --override-ini="addopts="; then
      echo "❌ API security tests failed"
      exit 1
    fi
    echo "✓ API security tests passed"
    echo ""
  else
    echo "✓ No security-related changes detected"
    echo ""
  fi

  echo "🧪 Checking if marketplace security tests are needed..."
  MARKETPLACE_FILES_REGEX="src/file_organizer/plugins/marketplace/|tests/plugins/test_marketplace_core\\.py"
  if echo "$MODIFIED" | grep -Eq "$MARKETPLACE_FILES_REGEX"; then
    echo "🧪 Running marketplace safety and integrity tests..."
    if ! pytest tests/plugins/test_marketplace_core.py -q --override-ini="addopts="; then
      echo "❌ Marketplace tests failed"
      exit 1
    fi
    echo "✓ Marketplace tests passed"
    echo ""
  else
    echo "✓ No marketplace-related changes detected"
    echo ""
  fi

  echo "🧪 Checking if CLI docs accuracy tests are needed..."
  CLI_FILES_REGEX="src/file_organizer/cli/.*\\.py"
  if echo "$MODIFIED" | grep -Eq "$CLI_FILES_REGEX"; then
    echo "🧪 Running CLI docs accuracy tests..."
    if ! pytest tests/docs/test_cli_docs_accuracy.py -q --override-ini="addopts="; then
      echo "❌ CLI docs accuracy tests failed"
      exit 1
    fi
    echo "✓ CLI docs accuracy tests passed"
    echo ""
  else
    echo "✓ No CLI changes detected"
    echo ""
  fi

  echo "🧪 Running CI-focused test suite..."
  if ! pytest tests/ci -q --override-ini="addopts="; then
    echo "❌ CI-focused tests failed"
    exit 1
  fi
  if ! pytest tests -m "not regression" --override-ini="addopts="; then
    echo "❌ Non-regression test suite failed"
    exit 1
  fi
  echo "✓ CI-focused tests passed"
  echo ""
fi

# 9. Summary
echo "✅ All validations passed!"
echo ""
echo "Safe to commit with:"
echo "  git commit -m 'your message'"
echo ""
