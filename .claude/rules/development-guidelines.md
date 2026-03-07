# Development Guidelines

Standards for code style, naming, commits, and pre-commit validation.

## Code Style

- **Black** for formatting (line length: 100)
- **isort** for import sorting
- **Ruff** for linting (strict)
- **mypy** strict mode for type checking

All rules are enforced via:
- Pre-commit hooks (`.pre-commit-config.yaml`)
- Pre-commit validation script (`.claude/scripts/pre-commit-validation.sh`)

---

## Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Files/modules | `snake_case.py` | `text_processor.py` |
| Classes | `PascalCase` | `TextProcessor` |
| Functions/variables | `snake_case` | `process_file()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES` |
| Private | `_single_underscore` | `_internal_method()` |

---

## Git Commit Messages

### Format

```text
<type>(<scope>): <subject>

[optional body]
```

### Types

- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Code style (formatting, etc.)
- `refactor` - Code refactoring
- `test` - Test additions/updates
- `chore` - Build, dependencies, tooling

### Examples

```text
feat(text_processor): add batch processing support

Allows processing multiple files in parallel using process pool.
Reduces processing time by 40% for bulk operations.

fix(api): prevent race condition in cache invalidation

Adds mutex lock around cache update operations to ensure
atomic read-modify-write of cache entries.

docs: add GraphQL query examples for PR comments API

Includes examples for fetching review threads and comments
with proper error handling.
```

---

## Pre-Commit Validation (MANDATORY)

**Before EVERY single commit, run:**

```bash
bash .claude/scripts/pre-commit-validation.sh
# Must PASS before committing
```

See: `.claude/rules/code-quality-validation.md` for detailed validation patterns

**Why this is non-negotiable:**
- Catches 80% of code review issues before they're published
- Prevents churn (validation now vs code review later)
- Maintains code quality standards
- Reduces feedback loops

**If validation fails:**
1. Fix violations locally
2. Re-run validation
3. Only commit after passing

---

## Git Pre-Commit Hook

A pre-commit configuration is defined in `.pre-commit-config.yaml`. After running `pre-commit install`, hooks run automatically on every commit.

**Configured hooks:**
- `ruff check` — lint the full project and `src/`
- `pytest` — websocket validations, CI guardrails, web UI, and non-regression tests
- `codespell` — spell check `src/` and `docs/`
- `absolute-path-check` — blocks absolute paths (e.g. `/Users/…`)
- `pymarkdown` — markdown lint using `.pymarkdown.json` rules

**If a hook fails:**
1. Fix the reported violations (e.g. `ruff check . --fix` for lint)
2. Stage fixed files: `git add <files>`
3. Try commit again

---

## Code Quality Patterns

**Mandatory patterns enforced in pre-commit validation:**

1. **Dict-style dataclass access** → use `hasattr()`
   ```python
   # ❌ Wrong
   if "field" in obj:
       value = obj["field"]

   # ✅ Right
   if hasattr(obj, "field"):
       value = obj.field
   ```

2. **Wrong return types** → read implementation first
   ```python
   # ❌ Wrong (assumes return type without verifying)
   result1, result2 = function()

   # ✅ Right (verify actual return type first)
   result = function()
   ```

3. **Non-existent imports** → verify module exists
   ```bash
   # Check import works
   python3 -c "from file_organizer.module import Class; print('OK')"
   ```

4. **Wrong constructor params** → check class definition
   ```python
   # ❌ Wrong (uses non-existent parameter)
   config = Config(param_that_doesnt_exist=True)

   # ✅ Right (verify __init__ signature first)
   config = Config(actual_param=True)
   ```

5. **Build artifacts** → add to `.gitignore`
   ```
   .coverage
   *.bak
   *.pyc
   ```

---

## Integration with Quality Gates

These guidelines are enforced through:

1. **Pre-commit validation** (this session): `bash .claude/scripts/pre-commit-validation.sh`
2. **Code review** (post-commit): `/code-reviewer` skill
3. **Git hooks** (automatic): `.pre-commit-config.yaml`

**Workflow order:**
1. Write code following guidelines above
2. Run pre-commit validation (catches local issues)
3. Run code review (validates design)
4. Commit (protected by git hooks)

---

## References

- `.claude/rules/code-quality-validation.md` - Detailed validation patterns
- `.claude/scripts/pre-commit-validation.sh` - Automation script
- `.pre-commit-config.yaml` - Hook configuration
- `pyproject.toml` - Ruff, mypy, pytest configuration
- `.pymarkdown.json` - Markdown linting rules

---

**Last Updated**: 2026-03-07
**Status**: Active enforcement
**Key Tools**: Ruff, Black, mypy, pre-commit
