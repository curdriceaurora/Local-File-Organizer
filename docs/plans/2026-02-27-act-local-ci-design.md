# Design: Add `act` for Local CI Simulation + Remove Frontend Placeholders

**Issue**: #369
**Date**: 2026-02-27
**Status**: Approved

## Summary

Add [`act`](https://github.com/nektos/act) configuration so developers can run GitHub Actions
workflows locally inside Docker containers that mirror `ubuntu-latest`. Also remove dead
`frontend-compat` and `frontend-e2e` placeholder jobs from `ci-full.yml` since Node.js
infrastructure was removed in #372 and E2E tests are deferred (#393).

## Deliverables

| File | Change |
|------|--------|
| `.actrc` | New — pins Docker image and container architecture |
| `CONTRIBUTING.md` | Add `act` section alongside existing `test-local-matrix.sh` docs |
| `.github/workflows/ci-full.yml` | Remove `frontend-compat` and `frontend-e2e` placeholder jobs |

## `.actrc` Configuration

```text
-P ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest
--container-architecture linux/amd64
```

This pins the Docker image to match GitHub's ubuntu-latest runner and forces x86_64 emulation
on Apple Silicon Macs.

## CONTRIBUTING.md Changes

Add a new section under "Pre-Push Checklist" documenting:

- `act` installation (brew/curl/choco)
- Common usage patterns (`act pull_request`, `act push`, per-job runs)
- Comparison table: `act` vs `test-local-matrix.sh`
- Prerequisites (Docker Desktop, ~2 GB disk)

## CI Cleanup

Remove from `ci-full.yml`:

- `frontend-compat` job — placeholder echoing "not yet implemented"
- `frontend-e2e` job — placeholder echoing "not yet implemented"

Both reference Node.js infrastructure that was removed in #372. E2E tests are tracked
separately in #393 (deferred).

## Out of Scope

- Per-job verification of `act` output (workflows change frequently)
- macOS/Windows `act` runners (Docker only supports Linux containers)
- Frontend test setup (deferred in #393)
- Changes to `ci.yml` (only `ci-full.yml` has the placeholder jobs)
