# Quick Fix Guide - PR #90 Review

**TL;DR:** 154 issues found, 128 auto-fixable, 26 require manual fixes.

---

## 🚨 CRITICAL (Fix First - 2-3 hours)

### 1. Mutable Class Defaults (9 issues)
**Files:** `organizer.py`, `heuristics.py`

```python
# Add this import
from typing import ClassVar

# Change this:
class MyClass:
    items: list[str] = []  # ❌ DANGEROUS

# To this:
class MyClass:
    items: ClassVar[list[str]] = []  # ✅ SAFE
```

### 2. Bare Except (1 issue)
**File:** `scripts/create_sample_images.py:50`

```python
# Change this:
try:
    font = ImageFont.truetype(path, 60)
except:  # ❌ BAD
    font = ImageFont.load_default()

# To this:
try:
    font = ImageFont.truetype(path, 60)
except (OSError, IOError) as e:  # ✅ GOOD
    logger.warning(f"Font load failed: {e}")
    font = ImageFont.load_default()
```

### 3. Silent Error (1 issue)
**File:** `utils/text_processing.py:47`

```python
# Change this:
try:
    result = risky_op()
except:
    pass  # ❌ SILENT FAILURE

# To this:
try:
    result = risky_op()
except Exception as e:
    logger.warning(f"Operation failed: {e}")  # ✅ LOGGED
```

---

## ⚡ HIGH PRIORITY (Auto-fixable - 30 mins)

### One Command to Fix Most Issues

```bash
cd file_organizer_v2

# Fix 110+ type annotation issues automatically
ruff check . --select UP006,UP007,UP045 --fix

# Verify it worked
python -m py_compile src/**/*.py
pytest tests/ -v
```

### Manual: Update pyproject.toml

```toml
# Move this:
[tool.ruff]
ignore = [...]
select = [...]

# To this:
[tool.ruff.lint]
ignore = [...]
select = [...]
```

---

## 📋 MEDIUM PRIORITY (Optional - 1 hour)

```bash
# Auto-fix unused imports
ruff check . --select F401 --fix

# Manual: Fix hardcoded /tmp path
# File: scripts/debug_single_file.py:19
# Replace with: tempfile.gettempdir()
```

---

## 🎨 LOW PRIORITY (Polish - 15 mins)

```bash
# Sort exports, fix EOF newlines
ruff check . --select W292,UP015,RUF022 --fix
```

---

## ✅ Verification Checklist

After fixes, run:

```bash
# 1. Check for remaining issues
ruff check . --statistics

# 2. Run tests
pytest tests/ -v

# 3. Type check
mypy src/

# 4. Test demo
python demo.py --sample --dry-run
```

---

## 📊 Before/After

**Before:**
- 154 issues
- Type annotations: 110 outdated
- Critical bugs: 11

**After (all fixes):**
- 0 critical issues
- Modern Python 3.10+ syntax
- Clean ruff check

---

## 🎯 Minimum Required Before Merge

1. ✅ All 11 critical issues fixed (RUF012, E722, S110)
2. ✅ Type annotations modernized (UP006, UP007, UP045)
3. ✅ Tests passing
4. ✅ No ruff errors

Everything else can be done in follow-up PRs if needed.

---

## 🆘 Need Help?

**Issue tracking where?**
- Commit history: `git log --grep "Fix P"`
- This is continuation of P1.1-P2.8 series

**Something broke?**
```bash
# Revert auto-fixes
git checkout -- .

# Fix one category at a time
ruff check . --select UP045 --fix  # Just Optional → | None
pytest tests/ -v                   # Test before continuing
```

**More details?**
See full action plan: `PR_90_REVIEW_ACTION_PLAN.md`
