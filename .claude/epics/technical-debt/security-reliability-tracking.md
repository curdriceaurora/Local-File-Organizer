---
name: security-reliability-tracking
title: Security & Reliability Issues Tracking
epic: technical-debt
github_epic: 266
created: 2026-02-18T06:59:33Z
updated: 2026-02-18T19:28:08Z
status: completed
---

# Security & Reliability Issues

Identified from codebase audit (PR #344, merged 2026-02-18).

## High Priority 🔴

**Issue #338: Security: Plugin Sandbox Bypass Risk (Plug-1)**

- **Priority**: High
- **Status**: Closed ✅
- **Effort**: 10h (actual)
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/338
- **Description**: Plugin execution environment may allow sandbox escape
- **Completed**: 2026-02-18 — subprocess isolation via `executor.py` + `ipc.py`; 15 tests passing

**Issue #339: Reliability: File Reading Denial of Service Risk (DoS-1)**

- **Priority**: High
- **Status**: Closed ✅
- **Effort**: 6h (actual)
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/339
- **Description**: File reading operations lack size/resource limits, enabling DoS
- **Completed**: 2026-02-18 — `FileTooLargeError` + `_check_file_size()` gate on 5 readers; 12 tests passing

**Issue #340: Security: Insecure Default JWT Secret (Auth-1)**

- **Priority**: High
- **Status**: Closed ✅
- **Effort**: 3h (actual)
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/340
- **Description**: Default JWT secret is weak/hardcoded, allowing token forgery
- **Completed**: 2026-02-18 — `SecretStr` type for `auth_jwt_secret`; 5 tests passing

## Medium Priority 🟡

**Issue #341: Security: SQL Injection Vector in DatabaseOptimization (DB-1)**

- **Priority**: Medium
- **Status**: Closed ✅
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/341
- **Description**: Raw SQL in DatabaseOptimization class not parameterized
- **Completed**: 2026-02-18 — regex allowlists for identifiers and pragma values; 76 tests passing

**Issue #342: Security: Weak Password Policy (Auth-2)**

- **Priority**: Medium
- **Status**: Closed ✅
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/342
- **Description**: No minimum password strength enforcement
- **Completed**: 2026-02-18 — 12-char min, uppercase + special char + blocklist; 44 tests passing

**Issue #343: Privacy: Potential Data Leak in Logs (Priv-1)**

- **Priority**: Medium
- **Status**: Closed ✅
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/343
- **Description**: Sensitive data (file paths, metadata) may appear in log output
- **Completed**: 2026-02-18 — log lengths only (no AI-generated content at INFO/WARNING); 11 tests passing

## Summary

- **Total**: 6 issues
- **High Priority**: 3 (#338, #339, #340)
- **Medium Priority**: 3 (#341, #342, #343)
- **Source**: PR #344 codebase audit (merged 2026-02-18)

## Tracking Updates

- **2026-02-18**: Issues identified and added to technical-debt CCPM tracking
- **2026-02-18**: #339 closed (file size gate), #340 closed (SecretStr JWT)
- **2026-02-18**: PR #346 squash-merged — all 6 issues (#338–#343) closed; 163 tests across 6 subsystems. Style nits deferred to #354.
