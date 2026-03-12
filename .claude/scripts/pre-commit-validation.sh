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

# 1.5. CCPM tracking awareness (soft warning, non-blocking)
if [[ "$BRANCH" != "main" && "$BRANCH" != "master" ]]; then
  # Extract issue number from branch name (e.g., "feature/issue-580-name" -> "580")
  ISSUE_NUM=$(echo "$BRANCH" | grep -oE 'issue-[0-9]+|#[0-9]+' | grep -oE '[0-9]+' | head -1)

  if [[ -n "$ISSUE_NUM" ]]; then
    # Check if CCPM tracking exists for this issue
    if ! find .claude/epics -name "*${ISSUE_NUM}*" -type f 2>/dev/null | grep -q . ; then
      echo "⚠️  CCPM tracking not found for issue #${ISSUE_NUM}"
      echo "   Consider running: /pm:issue-start ${ISSUE_NUM}"
      echo ""
    fi
  fi
fi

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

# 3.6. Check for stale documentation references (staged .md files only)
MD_FILES=$(git diff --cached --name-only --diff-filter=ACM -- '*.md' || true)
if [[ -n "$MD_FILES" ]]; then
  echo "📄 Checking documentation references..."
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "$SCRIPT_DIR/check-stale-doc-refs.sh" ]]; then
    if ! bash "$SCRIPT_DIR/check-stale-doc-refs.sh" --staged-only; then
      echo "❌ Stale documentation references found (see above)"
      echo "   Fix references or update .claude/scripts/check-stale-doc-refs.sh exclusions"
      exit 1
    fi
  else
    echo "⚠️  check-stale-doc-refs.sh not found, skipping"
  fi
  echo ""
fi

# 4. Pattern checks on Python files
PY_FILES=$(git diff --name-only --cached --diff-filter=ACM -- '*.py' || true)
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
  # Note: excludes .metadata["..."] and .analysis["..."] — these are dict fields on StageContext
  BRACKET_ACCESS=$(echo "$PY_DIFF" | grep -n '+.*\(result\|config\)\["' | grep -v '\.metadata\["' | grep -v '\.analysis\["' | grep -v '\.extra\["' || true)
  if [[ -n "$BRACKET_ACCESS" ]]; then
    echo "❌ Found bracket-style access on dataclass:"
    echo "$BRACKET_ACCESS"
    echo ""
    echo "Fix: Use obj.field instead of obj['field']"
    exit 1
  fi

  echo "✓ No dict-style dataclass access found"
  echo ""

  # 4b. Anti-pattern mechanical guards (from feature-generation & test-generation rules)
  echo "🔍 Anti-pattern guards..."

  # F1 guard: Flag narrow exception handling in graceful-degradation contexts
  # Detect `except OSError` or `except ConnectionError` in new code near fallback/init patterns
  NARROW_EXCEPT=$(echo "$PY_DIFF" | grep -n '^+.*except \(OSError\|ConnectionError\|ConnectionRefusedError\)\b' | grep -v 'test_' || true)
  if [[ -n "$NARROW_EXCEPT" ]]; then
    echo "⚠️  F1 warning: Narrow exception handler in new code (may miss non-network failures):"
    echo "$NARROW_EXCEPT" | sed 's/^/  /'
    echo "   Consider: Should this be 'except Exception' for graceful degradation?"
    echo ""
  fi

  # Test anti-pattern guard: Flag weak call_count assertions without payload verification
  TEST_DIFF=$(git diff --cached -- 'tests/**/*.py')
  WEAK_CALL_COUNT=$(echo "$TEST_DIFF" | grep -n '^+.*assert.*\.call_count\s*[><=]' || true)
  if [[ -n "$WEAK_CALL_COUNT" ]]; then
    # Check if there's a corresponding assert_called_with nearby
    HAS_PAYLOAD_CHECK=$(echo "$TEST_DIFF" | grep -c 'assert_called.*with\|call_args' || true)
    if [[ "$HAS_PAYLOAD_CHECK" -eq 0 ]]; then
      echo "⚠️  Test anti-pattern: call_count assertion without payload verification:"
      echo "$WEAK_CALL_COUNT" | sed 's/^/  /'
      echo "   Consider: Add assert_called_once_with() or check .call_args for payload"
      echo ""
    fi
  fi

  # Test anti-pattern guard: Flag assert X is None without mock context
  BARE_NONE_ASSERT=$(echo "$TEST_DIFF" | grep -n '^+.*assert.*is None$' || true)
  if [[ -n "$BARE_NONE_ASSERT" ]]; then
    echo "  ℹ️  Test pattern: 'assert X is None' found — verify it checks causality, not just state:"
    echo "$BARE_NONE_ASSERT" | head -5 | sed 's/^/  /'
    echo ""
  fi

  # Test anti-pattern guard: Flag mock patches that are never asserted
  # Look for @patch decorators in new lines, then check if the mock variable is asserted
  PATCHED_MOCKS=$(echo "$TEST_DIFF" | grep -oE '^\+.*\) as (mock_\w+)' | sed 's/.*as //' || true)
  for mock_var in $PATCHED_MOCKS; do
    ASSERT_COUNT=$(echo "$TEST_DIFF" | grep -c "^\+.*${mock_var}\.assert_\|^\+.*assert.*${mock_var}\." || true)
    if [[ "$ASSERT_COUNT" -eq 0 ]]; then
      echo "⚠️  Test anti-pattern: Mock '$mock_var' captured but never asserted"
      echo "   Consider: Add ${mock_var}.assert_called_once_with() or ${mock_var}.assert_not_called()"
      echo ""
    fi
  done

  # Cross-file validated-setter bypass check (PR #749 lesson)
  # When a dataclass defines __setattr__ or __post_init__ to validate specific fields,
  # direct object.__setattr__() calls in OTHER files bypass that guard entirely.
  # This check fires whenever a file with such validation is staged.
  if echo "$PY_DIFF" | grep -qE 'def __setattr__|def __post_init__'; then
    # Scan all src/ files for object.__setattr__ patterns on context/dataclass instances
    BYPASS_VIOLATIONS=$(grep -rn "object\.__setattr__" src/ 2>/dev/null | grep -v "def __setattr__" || true)
    if [[ -n "$BYPASS_VIOLATIONS" ]]; then
      echo "❌ object.__setattr__ bypass detected — violates validated-setter contract:"
      echo "$BYPASS_VIOLATIONS" | sed 's/^/  /'
      echo ""
      echo "Fix: Use direct attribute assignment (ctx.field = value) so __setattr__ validation runs."
      exit 1
    fi
    echo "✓ No validated-setter bypasses found"
    echo ""
  fi

  # Mixed-type dict semantic check (PR #749 lesson)
  # dict[str, object] storing a str/int instead of a model instance is type-safe but semantically wrong.
  # Flag any new code that stores a plain string into a dict annotated for model instances.
  MIXED_DICT=$(echo "$PY_DIFF" | grep -nE '^\+.*_active_models\[.*\]\s*=\s*(new_model_id|[a-z_]+_id|"[^"]+")' | grep -v 'test_' || true)
  if [[ -n "$MIXED_DICT" ]]; then
    echo "⚠️  Semantic dict type warning: storing a model ID string in a dict meant for model instances:"
    echo "$MIXED_DICT" | sed 's/^/  /'
    echo "   Fix: Use a separate _active_model_ids dict for IDs, keep _active_models for live instances."
    echo ""
  fi

  # Loguru guard: Flag logger.warning("...: {}", e) where logger.opt(exception=e) preserves traceback
  LOGURU_NO_TRACEBACK=$(echo "$PY_DIFF" | grep -n '^+.*logger\.\(warning\|error\|critical\).*{.*,\s*e\s*)' | grep -v 'test_' || true)
  if [[ -n "$LOGURU_NO_TRACEBACK" ]]; then
    echo "⚠️  Loguru pattern: logger.warning(\"...: {}\", e) loses traceback. Use logger.opt(exception=e).warning(\"...\"):"
    echo "$LOGURU_NO_TRACEBACK" | sed 's/^/  /'
    echo ""
  fi

  # CI marker guard: Flag test files that lack @pytest.mark.ci (CI runs pytest -m "ci")
  CHANGED_TEST_FILES=$(git diff --cached --name-only -- 'tests/**/*.py' | grep -v 'conftest.py' | grep -v '__init__' || true)
  for test_file in $CHANGED_TEST_FILES; do
    if [[ -f "$test_file" ]]; then
      HAS_CI_MARKER=$(grep -c 'pytest\.mark\.ci\|pytestmark.*ci' "$test_file" || true)
      if [[ "$HAS_CI_MARKER" -eq 0 ]]; then
        echo "⚠️  CI marker missing: $test_file has no @pytest.mark.ci — tests won't run in PR CI"
        echo "   Add: @pytest.mark.ci to the test class or pytestmark = [pytest.mark.ci] at module level"
        echo ""
      fi
    fi
  done

  echo "✓ Anti-pattern guards passed"
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
    echo "🔧 Checking ruff format..."
    if ! ruff format . --check; then
      echo "❌ Format check failed"
      echo "Run: ruff format . --fix"
      exit 1
    fi
    echo "✓ Format check passed"
    echo ""
    echo "🔧 Running type annotation lint on src/..."
    PY_SRC_FILES=$(echo "$PY_FILES" | grep '^src/' || true)
    if [[ -n "$PY_SRC_FILES" ]]; then
      if ! echo "$PY_SRC_FILES" | xargs ruff check --select ANN --ignore ANN401; then
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
    if ! echo "$PY_FILES" | xargs mypy --config-file=pyproject.toml --follow-imports=silent; then
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

# 6b. Code Quality & Design Review (MANDATORY for significant changes)
#     These must be done before running pre-commit-validation
echo "📊 Checking code quality and design requirements..."

# Detect if major code changes are staged
SIGNIFICANT_PY_CHANGES=0
if [[ -n "$PY_FILES" ]]; then
  # Count lines of changes in src/ files
  ADDED_LINES=$(git diff --cached -- 'src/file_organizer/**/*.py' | grep '^+' | wc -l || echo 0)
  MODIFIED_TESTS=$(echo "$PY_FILES" | grep '^tests/' | wc -l || echo 0)

  if [[ $ADDED_LINES -gt 50 ]] || [[ $MODIFIED_TESTS -gt 0 ]]; then
    SIGNIFICANT_PY_CHANGES=1
  fi
fi

if [[ $SIGNIFICANT_PY_CHANGES -eq 1 ]]; then
  echo "⚠️  Significant code changes detected. Running quality gates..."
  echo ""
  echo "You MUST run these quality gates before committing:"
  echo ""
  echo "  1. Code Simplification Review:"
  echo "     /simplify"
  echo ""
  echo "  2. Code Design Review:"
  echo "     /code-reviewer"
  echo ""
  echo "These validate code quality, design patterns, and test logic that"
  echo "automation cannot catch (assertions, test design, API contracts)."
  echo ""
  echo "After running these skills, stage any fixes and try again:"
  echo "  git add <files>"
  echo "  bash .claude/scripts/pre-commit-validation.sh"
  echo ""
  exit 1
fi

echo "✓ Code quality gates not required (no significant changes)"
echo ""

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

# 7a-1. Full Markdown Linting using pymarkdown
if [[ -n "$MD_FILES" ]]; then
  echo "📝 Running full markdown linting with pymarkdown..."

  if command -v pymarkdown &> /dev/null; then
    # Use pymarkdown with .pymarkdown.json config.
    # Pass files one-by-one: MD_FILES is newline-separated and pymarkdown
    # does not accept a single argument with embedded newlines.
    MARKDOWN_FAILED=0
    while IFS= read -r md_file; do
      if [[ -n "$md_file" ]] && ! pymarkdown -c .pymarkdown.json scan "$md_file"; then
        MARKDOWN_FAILED=1
      fi
    done <<< "$MD_FILES"
    if [[ "$MARKDOWN_FAILED" -eq 1 ]]; then
      echo ""
      echo "❌ Markdown linting failed"
      echo "Fix markdown issues above and try again"
      exit 1
    fi
    echo "✓ Markdown linting passed"
  else
    echo "⚠️  pymarkdown not found, skipping full markdown linting"
    echo "   Install with: pip install -e '.[dev]'"
  fi
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
  done

  if [[ $DOCS_ISSUES -eq 1 ]]; then
    echo ""
    echo "❌ Docs format conformity checks failed"
    exit 1
  fi
  echo "✓ Docs format conformity checks passed"
  echo ""
fi

# 7a-3. Documentation Content Verification (Claims, Examples, Consistency)
#        Ensures docs match reality and contain valid, tested examples
if [[ -n "$DOCS_FILES" ]]; then
  echo "📚 Running documentation content verification..."
  DOC_VERIFICATION_FAILED=0

  for doc_file in $DOCS_FILES; do
    if [[ ! -f "$doc_file" ]]; then
      continue
    fi

    # Check 1: Verify percentage claims match actual config/code
    # Pattern: Looks for "XX%" references and validates against known sources
    PERCENTAGE_CLAIMS=$(grep -n '[0-9]\+%' "$doc_file" | grep -iE 'coverage|gate|threshold' || true)
    if [[ -n "$PERCENTAGE_CLAIMS" ]]; then
      # Check for outdated 74% CI gate claims (should be 95%)
      if grep -q '74%' "$doc_file"; then
        echo "❌ $doc_file: Found outdated 74% CI gate reference (should be 95%)"
        echo "   Fix: Update coverage gate claims to match actual CI enforcement"
        DOC_VERIFICATION_FAILED=1
      fi

      # Check for 95% coverage gate accuracy
      if grep -q '95%.*code.*coverage\|95%.*CI.*gate' "$doc_file"; then
        # Verify this matches pyproject.toml
        if ! grep -q 'cov-fail-under.*95\|--cov-fail-under=95' pyproject.toml 2>/dev/null; then
          echo "❌ $doc_file: Claims 95% coverage gate but pyproject.toml doesn't enforce it"
          DOC_VERIFICATION_FAILED=1
        fi
      fi
    fi

    # Check 2: Verify method/function examples exist in codebase
    # Pattern: Looks for method calls like "ClassName.method_name(" and validates
    METHOD_CALLS=$(grep -oE '[A-Z][a-zA-Z0-9_]*\.[a-z_][a-zA-Z0-9_]*\(' "$doc_file" | sort -u || true)
    for method_call in $METHOD_CALLS; do
      METHOD_NAME=$(echo "$method_call" | sed 's/($//')
      CLASS_NAME=$(echo "$method_call" | cut -d. -f1)

      # Search for this method in src/ (skip test files)
      if ! grep -r "def ${METHOD_NAME#*.}" src/ 2>/dev/null | grep -q .; then
        # Could be a private method or legitimately not in codebase
        # Only warn if it looks like a public API method
        if [[ "$METHOD_NAME" != *"_"* ]]; then
          echo "⚠️  $doc_file: Method $METHOD_NAME may not exist in codebase (verify manually)"
        fi
      fi
    done

    # Check 3: Detect contradictions (same doc claims completion AND "not implemented")
    if grep -qi 'complete\|✅.*done' "$doc_file" && grep -qi '0%.*coverage\|not.*implement' "$doc_file"; then
      # Verify if this is a contradiction
      COMPLETE_LINES=$(grep -n -i 'complete\|✅.*done' "$doc_file" | head -2 | cut -d: -f1)
      NOT_IMPL_LINES=$(grep -n -i '0%.*coverage\|not.*implement' "$doc_file" | head -2 | cut -d: -f1)

      if [[ -n "$COMPLETE_LINES" ]] && [[ -n "$NOT_IMPL_LINES" ]]; then
        echo "⚠️  $doc_file: Found potential contradiction:"
        echo "   - Line $(echo $COMPLETE_LINES | head -1): Claims completion"
        echo "   - Line $(echo $NOT_IMPL_LINES | head -1): Claims 0% / not implemented"
        echo "   Verify these statements are consistent (same module/feature)"
      fi
    fi

    # Check 4: Verify coverage percentages are realistic
    # Only flag percentages > 100 on lines that mention "coverage" (avoids
    # false-positives from benchmark thresholds like "p95 exceeds 120%").
    while IFS= read -r line; do
      if echo "$line" | grep -qi 'coverage'; then
        while IFS= read -r pct; do
          if [[ $pct -gt 100 ]]; then
            echo "❌ $doc_file: Found unrealistic coverage percentage: $pct%"
            DOC_VERIFICATION_FAILED=1
          fi
        done < <(echo "$line" | grep -oE '[0-9]{1,3}%' | sed 's/%//')
      fi
    done < "$doc_file"

    # Check 5: Verify section categorization consistency
    # E.g., "Medium Coverage (70-89%)" should only contain 70-89 values
    if grep -q '(.*%.*%)' "$doc_file"; then
      # Extract section headers with ranges like "(70-89%)"
      SECTIONS=$(grep -oE '[A-Za-z ]*\([0-9]+%-[0-9]+%\)' "$doc_file" | sort -u || true)

      for section in $SECTIONS; do
        # Extract the range
        RANGE=$(echo "$section" | grep -oE '[0-9]+-[0-9]+')
        MIN=$(echo "$RANGE" | cut -d- -f1)
        MAX=$(echo "$RANGE" | cut -d- -f2)

        # Find all percentage values under this section until next heading
        # This is a simplified check (full check would require more parsing)
        SECTION_NAME=$(echo "$section" | sed "s/ ($RANGE%)//")
        if [[ -n "$SECTION_NAME" ]]; then
          # Warning only - detailed check requires more context
          echo "  ℹ️  Section '$SECTION_NAME': verify all entries are $MIN%-$MAX%"
        fi
      done
    fi

    # Check 6: Verify claimed features in README actually exist
    if echo "$doc_file" | grep -qi 'coverage.*badge\|README'; then
      if grep -q 'badge.*README\|README.*badge' "$doc_file"; then
        if ! grep -q 'coverage' README.md 2>/dev/null; then
          echo "⚠️  $doc_file: Claims coverage badge in README, but not found"
          echo "   Either add badge to README.md or remove claim from docs"
        fi
      fi
    fi

    # Check 7: Verify links to CI config are correct
    if grep -qi 'github.*workflow\|\.github.*ci\.yml' "$doc_file"; then
      if [[ ! -f '.github/workflows/ci.yml' ]]; then
        echo "❌ $doc_file: References CI workflow, but .github/workflows/ci.yml not found"
        DOC_VERIFICATION_FAILED=1
      fi
    fi

  done

  if [[ $DOC_VERIFICATION_FAILED -eq 1 ]]; then
    echo ""
    echo "❌ Documentation verification failed"
    echo ""
    echo "Common issues to fix:"
    echo "  - Verify all percentages match actual code/config files"
    echo "  - Verify all method examples exist in src/ files"
    echo "  - Resolve contradictions between sections"
    echo "  - Ensure section ranges match their content"
    echo "  - Verify claims about features (badges, etc.)"
    echo ""
    exit 1
  fi

  echo "✓ Documentation content verification passed"
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
        # --override-ini="addopts=": suppress coverage gate on single-module runs (gate only
        # applies on full-suite main-push runs, not per-file pre-commit checks)
        if ! pytest "$TEST_FILE" --tb=line -q --override-ini="addopts="; then
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
          if ! pytest "$ALT_TEST" --tb=line -q --override-ini="addopts="; then
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

# ── 8c. Datetime Timezone Safety ──────────────────────────────────────────
# These checks prevent naive datetime patterns from reaching main.

STAGED_PY_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)

if [ -n "$STAGED_PY_FILES" ]; then
  echo "🕐 Datetime timezone safety checks..."

  # Check 1: Naive datetime.now() detection
  NAIVE_NOW=$(echo "$STAGED_PY_FILES" | while IFS= read -r f; do [ -n "$f" ] && grep -Hn 'datetime\.now()' "$f" 2>/dev/null; done | grep -Ev 'now\((UTC|timezone|tz=)' || true)
  if [ -n "$NAIVE_NOW" ]; then
    echo "  ❌ Found naive datetime.now() — use datetime.now(UTC) instead:"
    echo "$NAIVE_NOW" | sed 's/^/    /'
    exit 1
  else
    echo "  ✓ No naive datetime.now() found"
  fi

  # Check 2: Deprecated utcnow() detection
  UTCNOW=$(echo "$STAGED_PY_FILES" | while IFS= read -r f; do [ -n "$f" ] && grep -Hn 'datetime\.utcnow()' "$f" 2>/dev/null; done || true)
  if [ -n "$UTCNOW" ]; then
    echo "  ❌ Found deprecated datetime.utcnow() — use datetime.now(UTC) instead:"
    echo "$UTCNOW" | sed 's/^/    /'
    exit 1
  else
    echo "  ✓ No deprecated utcnow() found"
  fi

  # Check 3: Bare fromtimestamp() detection (warning only)
  BARE_TS=$(echo "$STAGED_PY_FILES" | while IFS= read -r f; do [ -n "$f" ] && grep -Hn 'fromtimestamp(' "$f" 2>/dev/null; done | grep -v 'tz=' || true)
  if [ -n "$BARE_TS" ]; then
    echo "  ⚠️  Found fromtimestamp() without tz= — consider adding tz=UTC:"
    echo "$BARE_TS" | sed 's/^/    /'
    # Warning only — don't exit
  else
    echo "  ✓ No bare fromtimestamp() found"
  fi

  # Check 4: isoformat()+"Z" trap detection
  # Only match literal concatenation like isoformat() + "Z", NOT safe .replace("+00:00", "Z")
  ISO_TRAP=$(echo "$STAGED_PY_FILES" | while IFS= read -r f; do [ -n "$f" ] && grep -HnE 'isoformat\(\)\s*\+\s*['\''"]Z['\''"]' "$f" 2>/dev/null; done | grep -v '\.replace(' || true)
  if [ -n "$ISO_TRAP" ]; then
    echo "  ❌ Found isoformat()+\"Z\" trap — use .isoformat().replace('+00:00', 'Z') instead:"
    echo "$ISO_TRAP" | sed 's/^/    /'
    exit 1
  else
    echo "  ✓ No isoformat()+\"Z\" trap found"
  fi

  echo "✓ Datetime timezone safety checks passed"
  echo ""
fi

# 9. Summary
echo "✅ All validations passed!"
echo ""
echo "Safe to commit with:"
echo "  git commit -m 'your message'"
echo ""
