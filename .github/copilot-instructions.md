# GitHub Copilot Instructions

## Files and Directories to Ignore

Do NOT review or comment on these paths:

- Generated build, cache, and coverage artifacts.
- Vendored dependency output and binary assets unless the PR explicitly changes
  asset handling.

## Focus Areas for Code Review

**DO focus on:**
- `src/` - Main application code
- `tests/` - Test suite
- `.github/workflows/` - CI/CD configuration
- `pyproject.toml` - Project configuration
- `docs/` - Documentation

## Review Principles

### For Python Code
- Type hints and type safety
- Test coverage and meaningful assertions
- Performance and optimization opportunities
- Security best practices
- Code clarity and maintainability

### For Configuration Files
- Correctness of CI/CD workflows
- Security (no hardcoded secrets)
- Dependency updates and compatibility

### DO NOT
- Suggest changes to generated artifacts or dependency cache files.
- Review binary assets unless the PR explicitly changes asset handling.

## Suppression Syntax

If a PR should suppress automated review noise, use:

```text
<!-- copilot: skip_review -->
```

Or in inline comments:

```python
# copilot: wontfix
```
