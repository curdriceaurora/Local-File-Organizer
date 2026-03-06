# GitHub Copilot Instructions

## Files and Directories to Ignore

Do NOT review or comment on these paths:

- `.claude/` - Internal Claude Code configuration and project management
- `.claude/**` - All Claude Code files (skills, plans, rules, settings)
- `CLAUDE.md` - Project-internal Claude Code instructions

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
- Comment on .claude/ directory files
- Suggest changes to internal Claude Code configuration
- Review Claude Code project management files
- Comment on skill files (.claude/skills/)
- Review CLAUDE.md instructions

## Suppression Syntax

If a PR touches .claude/ files, use:
```text
<!-- copilot: skip_review -->
```

Or in inline comments:
```python
# copilot: wontfix
```
