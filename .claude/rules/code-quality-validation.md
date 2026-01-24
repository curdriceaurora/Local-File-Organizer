# Code Quality Validation Rule

**CRITICAL**: This rule prevents recurring errors caught by AI code reviewers.

## Core Principle

**Proactively validate code for known patterns BEFORE committing.**

Claude's purpose is to catch issues BEFORE they reach code review, not after. Aggressively verify code against patterns that reviewers consistently flag.

## Pre-Commit Validation Checklist

Before EVERY commit, execute these validation steps:

### 1. Branch Verification
```bash
# Verify you're on the correct branch
CURRENT_BRANCH=$(git branch --show-current)
EXPECTED_BRANCH="feature/issue-XXX-description"

if [[ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]]; then
  echo "❌ ERROR: Wrong branch!"
  echo "Current: $CURRENT_BRANCH"
  echo "Expected: $EXPECTED_BRANCH"
  exit 1
fi
```

### 2. Run Affected Tests
```bash
# Get modified files
MODIFIED_FILES=$(git diff --name-only HEAD)

# Run tests for modified modules
for file in $MODIFIED_FILES; do
  if [[ $file == *.py ]]; then
    # Convert file path to test path
    TEST_FILE=$(echo "$file" | sed 's|src/|tests/|' | sed 's|\.py$|_test.py|')
    if [[ -f "$TEST_FILE" ]]; then
      pytest "$TEST_FILE" --tb=short || exit 1
    fi
  fi
done
```

### 3. Static Analysis
```bash
# Run linting on changed files
git diff --name-only HEAD | grep '\.py$' | xargs ruff check --fix

# Run type checking
git diff --name-only HEAD | grep '\.py$' | xargs mypy --strict
```

### 4. Pattern Validation
Run pattern checks (see sections below)

### 5. Commit Only If All Pass
```bash
# Only if all checks pass:
git add <files>
git commit -m "message"
git push
```

## API Documentation Patterns

### Pattern 1: Dataclass Field Access

**Problem**: Treating dataclasses as dictionaries

**Wrong**:
```python
# ❌ Dictionary-style access
if "duration" in metadata:
    duration = metadata["duration"]

# ❌ Always-true condition
if "title" in metadata or metadata is not None:
    title = metadata["title"]
```

**Correct**:
```python
# ✅ Proper dataclass access
if hasattr(metadata, "duration") and metadata.duration is not None:
    duration = metadata.duration

# ✅ Proper None check
if metadata is not None and hasattr(metadata, "title") and metadata.title is not None:
    title = metadata.title
```

**Validation**:
```bash
# Check for dict-style access on known dataclasses
rg -n 'if\s+"[^"]+"\s+in\s+(metadata|result|config)' file_organizer_v2/
rg -n '\["[^"]+"\]' file_organizer_v2/ | grep -E '(metadata|result|config)'
```

### Pattern 2: Return Type Verification

**Problem**: Documenting wrong return types without checking implementation

**Wrong**:
```python
# ❌ Documentation assumes tuple without verification
content, metadata = read_epub_file("book.epub")
```

**Correct**:
```python
# ✅ FIRST: Read the actual implementation
# file_organizer/utils/file_readers.py:
# def read_ebook_file(file_path: Path) -> str:
#     """Returns single string of extracted text."""

# ✅ THEN: Document correctly
text = read_ebook_file("book.epub")
```

**Validation Process**:
```bash
# 1. Find the actual function
rg -n "def read_epub_file" file_organizer_v2/

# 2. Read the implementation
# Use Read tool to view the file

# 3. Check return type annotation
# Verify return type matches documentation

# 4. Update documentation to match
```

### Pattern 3: Constructor Signature Verification

**Problem**: Using wrong parameter names or missing required parameters

**Wrong**:
```python
# ❌ Wrong parameter names
config = PARAConfig(
    auto_categorize=True,
    auto_archive=True,
    archive_after_days=90  # Parameter doesn't exist!
)
```

**Correct**:
```python
# ✅ FIRST: Read actual class definition
# file_organizer/methodologies/para/config.py:
# @dataclass
# class PARAConfig:
#     auto_categorize: bool = True
#     temporal_thresholds: Optional[TemporalThresholds] = None

# ✅ THEN: Use correct parameters
from file_organizer.methodologies.para.detection.temporal import TemporalThresholds
temporal = TemporalThresholds(
    archive_min_age=90,
    archive_min_inactive=30
)
config = PARAConfig(
    auto_categorize=True,
    temporal_thresholds=temporal
)
```

**Validation**:
```bash
# Find class definition
rg -A 20 "^class PARAConfig" file_organizer_v2/

# Or use ast-grep for precise structure
ast-grep --pattern 'class PARAConfig:
    $$$' --lang python file_organizer_v2/
```

### Pattern 4: Module Import Verification

**Problem**: Importing from non-existent modules

**Wrong**:
```python
# ❌ Module doesn't exist
from file_organizer.methodologies.para import PARARule
```

**Correct**:
```python
# ✅ FIRST: Verify module exists
# ls file_organizer_v2/src/file_organizer/methodologies/para/

# ✅ THEN: Import from correct location
from file_organizer.methodologies.para.rules import Rule
```

**Validation**:
```bash
# Check if module exists
find file_organizer_v2/src -name "*.py" -path "*para*" -type f

# Verify import path
python3 -c "from file_organizer.methodologies.para.rules import Rule; print('✅ Import works')"
```

### Pattern 5: CLI Command Verification

**Problem**: Documenting commands that don't exist

**Wrong**:
```bash
# ❌ Command doesn't exist
file-organizer db migrate
file-organizer snapshot create
```

**Correct**:
```python
# ✅ FIRST: Check pyproject.toml for actual commands
# [project.scripts]
# file-organizer = "file_organizer.cli.main:app"

# ✅ THEN: Check CLI entrypoint for available commands
# Read file_organizer/cli/main.py or cli/__init__.py

# ✅ ONLY document commands that exist
file-organizer organize --input ~/Downloads
file-organizer dedupe --scan-dir ~/Documents
```

**Validation**:
```bash
# Check available commands
file-organizer --help

# Or inspect CLI code
rg -n "@app.command" file_organizer_v2/src/file_organizer/cli/
```

## Documentation Patterns

### Pattern 6: Broken Links

**Problem**: Linking to files that don't exist

**Wrong**:
```markdown
See [FAQ](faq.md) for more information.
```

**Correct**:
```bash
# ✅ FIRST: Check if file exists
ls file_organizer_v2/docs/phase-3/faq.md

# ✅ IF missing: Remove link or create file
# OPTION A: Remove reference
# OPTION B: Create the file
```

**Validation**:
```bash
# Find all markdown links
rg -n '\[.*\]\([^h][^t][^t][^p].*\)' file_organizer_v2/docs/

# Check each linked file exists
for link in $(rg -o '\]\(([^h][^t][^t][^p][^\)]+)\)' -r '$1' file_organizer_v2/docs/); do
  if [[ ! -f "file_organizer_v2/docs/$link" ]]; then
    echo "❌ Broken link: $link"
  fi
done
```

### Pattern 7: Code Example Testing

**Problem**: Code examples that don't work

**Validation**:
```python
# Extract code examples and test them
# Create temporary test file
cat > /tmp/test_example.py << 'EOF'
# Paste example code here
EOF

# Run it
python3 /tmp/test_example.py
```

## Test Patterns

### Pattern 8: Fixture Path Verification

**Problem**: Wrong fixture directory names in tests

**Wrong**:
```python
# ❌ Wrong fixture path
fixture_path = Path("tests/fixtures/audio")
fixture_path = Path("tests/fixtures/johnny")
```

**Correct**:
```bash
# ✅ FIRST: Check actual fixture directories
ls file_organizer_v2/tests/fixtures/

# ✅ THEN: Use correct names
fixture_path = Path("tests/fixtures/audio_samples")
fixture_path = Path("tests/fixtures/johnny_decimal")
```

**Validation**:
```bash
# List actual fixture directories
find file_organizer_v2/tests/fixtures -type d -maxdepth 1
```

### Pattern 9: Test API Compatibility

**Problem**: Tests using wrong API that doesn't match implementation

**Validation Workflow**:
1. Read the actual service/model implementation
2. Check method signatures and return types
3. Write test using correct API
4. Run test to verify

```python
# Example validation
# 1. Read implementation
from file_organizer.services.video.scene_detector import SceneDetector

# 2. Check what it actually returns
detector = SceneDetector()
result = detector.detect_scenes(Path("test.mp4"))
print(f"Return type: {type(result)}")

# 3. Write test with correct assertions
assert isinstance(result, SceneDetectionResult)
```

## Repository Patterns

### Pattern 10: Build Artifacts

**Problem**: Committing build artifacts and backups

**Validation**:
```bash
# Check for common artifacts
git status | grep -E '\.(coverage|bak|pyc|pyo)$'

# If found, add to .gitignore
echo ".coverage" >> .gitignore
echo "*.bak" >> .gitignore
echo "coverage.xml" >> .gitignore
echo "htmlcov/" >> .gitignore
```

## Automated Validation Script

Create this script and run before every commit:

```bash
#!/bin/bash
# .claude/scripts/pre-commit-validation.sh

echo "🔍 Pre-Commit Validation"
echo "======================="

# 1. Branch check
BRANCH=$(git branch --show-current)
echo "✓ Branch: $BRANCH"

# 2. Modified files
MODIFIED=$(git diff --name-only --cached)
echo "✓ Modified files:"
echo "$MODIFIED" | sed 's/^/  /'

# 3. Run tests on modified Python files
echo ""
echo "🧪 Running tests..."
for file in $MODIFIED; do
  if [[ $file == file_organizer_v2/src/*.py ]]; then
    TEST_FILE=$(echo "$file" | sed 's|src/file_organizer|tests|' | sed 's|\.py$|_test.py|')
    if [[ -f "$TEST_FILE" ]]; then
      pytest "$TEST_FILE" --tb=short -v || exit 1
    fi
  fi
done

# 4. Linting
echo ""
echo "🔧 Linting..."
echo "$MODIFIED" | grep '\.py$' | xargs ruff check || exit 1

# 5. Type checking
echo ""
echo "📋 Type checking..."
echo "$MODIFIED" | grep '\.py$' | xargs mypy --strict || exit 1

# 6. Pattern checks
echo ""
echo "🎯 Pattern validation..."

# Check for dict-style dataclass access
if git diff --cached | grep -q 'if.*".*".*in.*metadata\|if.*".*".*in.*result'; then
  echo "❌ Found dict-style access on dataclass"
  echo "Use: hasattr(obj, 'field') and obj.field is not None"
  exit 1
fi

# Check for build artifacts
if git diff --cached --name-only | grep -qE '\.(coverage|bak|pyc)$'; then
  echo "❌ Found build artifacts in commit"
  echo "Add to .gitignore and unstage"
  exit 1
fi

echo ""
echo "✅ All validations passed!"
echo "Safe to commit."
```

## Usage in Workflow

### When Writing Code
1. Read actual implementation FIRST
2. Verify method signatures and return types
3. Test code example before documenting
4. Use correct import paths

### Before Committing
```bash
# Run validation script
bash .claude/scripts/pre-commit-validation.sh

# If passes, commit
git commit -m "message"
```

### When Reviewing Own Code
Ask these questions:
- Did I read the actual implementation?
- Did I verify this import path exists?
- Did I test this code example?
- Did I check the return type annotation?
- Are there any dict-style accesses on dataclasses?
- Are there any build artifacts?

## Integration with PM Skills

When using `/pm:issue-start` or working on issues:
1. Run pre-commit validation before EVERY commit
2. Don't wait for CI to catch issues
3. Catch patterns locally before pushing
4. Maintain zero tolerance for known patterns

## Severity Levels

**P0 - Must Fix Before Commit**:
- Dict-style dataclass access
- Wrong return types in examples
- Non-existent imports
- Build artifacts

**P1 - Must Fix Before Push**:
- Broken links in docs
- Untested code examples
- Wrong CLI commands
- Missing type hints

**P2 - Must Fix Before PR**:
- Inconsistent formatting
- Missing docstrings
- Incomplete test coverage

**P3 - Nice to Have**:
- Markdown formatting
- Comment clarity
- Variable naming

## Remember

**The goal**: AI reviewers should find NOTHING to complain about.

**The method**: Aggressively validate against known patterns BEFORE committing.

**The outcome**: Clean PRs that pass review on first attempt.
