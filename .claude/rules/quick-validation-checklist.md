# Quick Validation Checklist

**Use this before every commit to catch issues that AI reviewers flag.**

## 🚨 Critical Patterns (P0)

### 1. Dataclass Field Access

```python

# ❌ WRONG
if "field" in obj:
    value = obj["field"]

# ✅ CORRECT
if hasattr(obj, "field") and obj.field is not None:
    value = obj.field

```

### 2. Verify Return Types

```python

# ❌ WRONG: Assuming without checking
result1, result2 = function()

# ✅ CORRECT: Read implementation first, then document

# 1. Read: file_organizer/utils/file_readers.py

# 2. Check return type annotation

# 3. Use correct return handling
result = function()  # Returns single value, not tuple

```

### 3. Check Imports Exist

```bash

# Before using any import:
find file_organizer_v2/src -name "*.py" -path "*path/to/module*"

# Test import works:
python3 -c "from file_organizer.module import Class; print('✅')"

```

### 4. Verify Constructor Parameters

```python

# ❌ WRONG: Using parameters that don't exist
config = Config(param_that_doesnt_exist=True)

# ✅ CORRECT: Read class definition first

# 1. Find class: rg "^class Config" file_organizer_v2/

# 2. Read __init__ or @dataclass fields

# 3. Use correct parameters

```

## 🔧 Before Every Commit

```bash

# Run automated validation
bash .claude/scripts/pre-commit-validation.sh

# If passes, commit safely:
git commit -m "message"

```

## 📝 Documentation Checklist

- [ ] Read actual implementation code
- [ ] Verify method signatures match
- [ ] Test all code examples work
- [ ] Check all links point to existing files
- [ ] Verify CLI commands exist (`file-organizer --help`)
- [ ] Use correct import paths

## 🧪 Testing Checklist

- [ ] Fixture paths match actual directories (`ls tests/fixtures/`)
- [ ] Test API matches implementation
- [ ] No dict-style access on dataclasses
- [ ] Tests actually run and pass locally

## 🗑️ Repository Checklist

- [ ] No build artifacts (`.coverage`, `*.bak`, `*.pyc`)
- [ ] All artifacts in `.gitignore`
- [ ] Correct branch (`git branch --show-current`)
- [ ] No backup files committed

## 🎯 Pattern Quick Checks

```bash

# Check for dict-style dataclass access
git diff --cached | grep 'if.*".*".*in.*metadata'

# Check for bracket access on dataclasses
git diff --cached | grep 'metadata\["'

# Check for build artifacts
git diff --cached --name-only | grep -E '\.(coverage|bak|pyc)$'

# If any match: FIX BEFORE COMMITTING

```

## 💡 Quick Fixes

### Fix: Dict-style dataclass access

```python

# Find this pattern:
if "field" in metadata:
    x = metadata["field"]

# Replace with:
if hasattr(metadata, "field") and metadata.field is not None:
    x = metadata.field

```

### Fix: Wrong return type

```python

# Find the implementation:
rg -A 5 "def function_name" file_organizer_v2/src/

# Read the return type annotation

# Update your code to match

```

### Fix: Non-existent import

```bash

# Find correct module:
find file_organizer_v2/src -name "*.py" | grep -i "keyword"

# Update import path to match actual location

```

### Fix: Build artifacts

```bash

# Add to .gitignore:
echo ".coverage" >> .gitignore
echo "*.bak" >> .gitignore
echo "coverage.xml" >> .gitignore

# Unstage from commit:
git reset HEAD .coverage *.bak

```

## 📊 Validation Priority

**P0 (Block commit)**:
- Dict-style dataclass access
- Build artifacts

**P1 (Fix before push)**:
- Wrong return types
- Non-existent imports
- Broken links

**P2 (Fix before PR)**:
- Untested examples
- Missing fixtures

**P3 (Nice to have)**:
- Formatting
- Comments

## Remember

✅ **Validate BEFORE committing, not after**
✅ **Read implementation BEFORE documenting**
✅ **Test examples BEFORE writing docs**
✅ **Run script BEFORE every commit**

The goal: **Zero review comments on code quality issues.**
