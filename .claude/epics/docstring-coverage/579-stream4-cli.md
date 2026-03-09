---
name: 579-stream4-cli
issue: 579
stream: 4
title: "CLI & User-Facing APIs"
status: completed
created: 2026-03-06T21:00:00Z
updated: 2026-03-09T05:58:01Z
---

# Task 579.4: CLI & User-Facing APIs

## Scope

Add docstrings to CLI and public API surfaces:

- `cli/*.py` - Command handlers and entry points
- `__init__.py` files - public exports
- Public API decorators and utilities
- Configuration and setup utilities

## Acceptance Criteria

- [ ] All CLI command functions have docstrings
- [ ] All public functions documented
- [ ] Module docstrings present
- [ ] No signatures changed
- [ ] Google-style formatting
- [ ] `interrogate -v src/file_organizer/cli` reports 90%+

## Implementation Notes

1. Start with main CLI entry points
2. Then command groups and subcommands
3. Document expected arguments and options in docstrings
4. Keep docstrings concise for CLI functions

## Definition of Done

- [ ] Baseline measured
- [ ] All CLI commands documented
- [ ] Coverage >= 90% for cli/
- [ ] Public `__init__.py` exports documented
- [ ] Commit: "docs: add docstrings to CLI and public APIs (#579.4)"

## Files to Touch

```
src/file_organizer/
├── __init__.py
├── cli/
│   ├── __init__.py
│   ├── main.py
│   └── [command files]
└── [root level public APIs]
```

## Verification Command

```bash
interrogate -v src/file_organizer/cli --quiet
```
