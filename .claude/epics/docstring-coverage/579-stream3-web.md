---
name: 579-stream3-web
issue: 579
stream: 3
title: "Web Layer Docstrings"
status: open
created: 2026-03-06T21:00:00Z
updated: 2026-03-06T21:00:00Z
---

# Task 579.3: Web Layer Docstrings

## Scope

Add docstrings to web layer in `src/file_organizer/web/`:

- Route handlers and blueprints
- Request/response handlers
- WebSocket handlers
- Utility functions
- Middleware

## Acceptance Criteria

- [ ] All public route handlers have docstrings
- [ ] All handler functions documented
- [ ] Module docstrings present
- [ ] No signatures changed
- [ ] Google-style formatting
- [ ] `interrogate -v src/file_organizer/web` reports 90%+

## Implementation Notes

1. Start with main route files (files_routes, organize_routes, etc.)
2. Then WebSocket handlers
3. Then utility functions
4. Document expected request/response formats in docstrings

## Definition of Done

- [ ] Baseline measured
- [ ] All route handlers documented
- [ ] Coverage >= 90% for web/
- [ ] Commit: "docs: add docstrings to web layer (#579.3)"

## Files to Touch

```
src/file_organizer/web/
├── *_routes.py
├── handlers/
├── ws/
└── [other web files]
```

## Verification Command

```bash
interrogate -v src/file_organizer/web --quiet
```
