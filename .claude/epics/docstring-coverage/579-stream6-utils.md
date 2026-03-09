---
name: 579-stream6-utils
issue: 579
stream: 6
title: "Utils & Data Models"
status: completed
created: 2026-03-06T21:00:00Z
updated: 2026-03-09T05:58:01Z
---

# Task 579.6: Utils & Data Models

## Scope

Add docstrings to utility and data model modules:

- `utils/**/*.py` - Utility functions and helpers
- `models/*.py` - Data model classes (dataclasses, Pydantic models)
- Common type definitions
- Enums and constants

## Acceptance Criteria

- [ ] All public utility functions have docstrings
- [ ] All data model classes documented
- [ ] Module docstrings present
- [ ] No signatures changed
- [ ] Google-style formatting
- [ ] `interrogate -v src/file_organizer/utils` reports 90%+

## Implementation Notes

1. Start with data models (foundational)
2. Then utility functions (highest reuse)
3. Document parameter types and return values
4. Keep utility docstrings concise but complete

## Definition of Done

- [ ] Baseline measured
- [ ] All public utilities documented
- [ ] Coverage >= 90% for utils/ and models/
- [ ] Commit: "docs: add docstrings to utils and models (#579.6)"

## Files to Touch

```
src/file_organizer/
├── utils/
│   ├── __init__.py
│   ├── file_*.py
│   └── [utility modules]
├── models/
│   ├── __init__.py
│   └── [data models]
└── [common modules]
```

## Verification Command

```bash
interrogate -v src/file_organizer/utils --quiet
```
