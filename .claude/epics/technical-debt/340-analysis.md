---
issue: 340
title: "Security: Insecure Default JWT Secret (Auth-1)"
epic: technical-debt
analyzed: 2026-02-18T07:35:00Z
estimated_hours: 3
parallelization_factor: 1.0
status: closed
updated: 2026-03-09T06:09:18Z
---

# Work Analysis: Issue #340

## Overview

`auth_jwt_secret` defaults to `"change-me"` in `ApiSettings`. The existing validation in `load_settings_from_env()` already raises in non-dev/test environments, but the field still has a default — meaning:

1. A misconfigured app that skips `load_settings_from_env()` (e.g. direct `ApiSettings()` in tests) silently uses the weak secret
2. The warning in dev/test is easily missed

**Fix strategy**:

- Remove the `= "change-me"` default, making the field required (no default)
- Provide a test-only override via `ApiSettings(auth_jwt_secret="test-secret")` in test fixtures
- Ensure startup validation still raises clearly in production

## Single Stream (Sequential — small change)

**Files**:

- `src/file_organizer/api/config.py` — remove default, update validation comment
- `src/file_organizer/api/test_utils.py` — provide explicit test secret in any test factory
- `tests/api/test_config.py` (or nearest config test) — add test: `ApiSettings()` without secret raises, `ApiSettings(auth_jwt_secret="x")` succeeds

**Estimated Hours**: 3
**No parallelization needed** — all changes are in one tight area.

## Key Decision

Use `pydantic.SecretStr` type for `auth_jwt_secret` so the value is redacted in logs/repr. This is a small additive improvement worth doing at the same time.
