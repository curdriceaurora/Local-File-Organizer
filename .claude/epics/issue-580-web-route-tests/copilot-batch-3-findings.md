---
name: copilot-batch-3-findings
title: Copilot Review Batch 3 - Deeper Test Issues (6 Comments)
pr: 635
reviewed_at: 2026-03-07T00:00:00Z
total_comments: 6
status: in_progress
---

# Copilot Code Review Batch 3 - Web Route Tests (PR #635)

## Overview

This is the **3rd batch of Copilot findings** on PR #635. These are more sophisticated issues that go beyond basic assertions - they involve:
- Mock depth (mocking too broadly breaks happy path testing)
- Response validation in error-handling routes
- Test isolation (non-hermetic tests pollute the environment)
- Assertion precision (permissive assertions hide regressions)

## Comment 1: Mock is Too Shallow

**File**: `tests/test_web_organize_routes.py`

**Issue**: `mock_file_organizer` replaces `FileOrganizer` class entirely with a bare `MagicMock`, which removes class attributes like `TEXT_EXTENSIONS` used by route helpers like `_counts_by_type()`. The mock returns a dict from `.organize()` but the route expects an `OrganizationResult` object, forcing the request into the error path instead of the success path.

**Impact**: Tests pass without exercising the actual success code path.

**Status**: ⏳ IN PROGRESS
**Applied**: ✅ Patched only `FileOrganizer.organize()` method (not entire class)
**Remaining**: Need to verify that mock result properly implements `OrganizationResult` interface for `_result_to_response()` conversion

---

## Comment 2: Scan Tests Lack Success Validation

**File**: `tests/test_web_organize_routes.py`

**Issue**: The `test_organize_scan_*` tests only assert `status_code == 200`, but `/ui/organize/scan` returns 200 even when validation fails or an exception occurs - it just renders an error banner in the HTML instead of using HTTP 400. As written, tests can pass even when the scan did NOT generate a plan.

**Impact**: Tests don't catch regressions where the route enters the error path.

**Status**: ⏳ IN PROGRESS
**Applied**: ✅ Added assertions for plan markers:
```python
assert "plan" in response.text or "data-plan" in response.text
```

**Remaining**: Tests need to verify actual plan was generated (not just error message rendered)

---

## Comment 3: Non-Hermetic Marketplace Tests

**File**: `tests/test_web_marketplace_routes.py`

**Issue**: `_build_client()` instantiates `MarketplaceService()` on requests, which defaults its home dir to the user's config directory (`get_config_dir()/marketplace`) and creates real directories/files there. This makes tests non-hermetic and can pollute the developer/CI environment.

**Impact**: Tests have side effects; running tests creates files on the user's machine.

**Status**: ⏳ IN PROGRESS
**Applied**: ✅ Updated `_build_client()` to set `FO_MARKETPLACE_HOME` environment variable:
```python
os.environ["FO_MARKETPLACE_HOME"] = str(tmp_path / "marketplace")
```

**Remaining**: Need to ensure cleanup happens (consider using pytest fixture for env cleanup)

---

## Comment 4: Overly Permissive Assertions in Marketplace Tests

**File**: `tests/test_web_marketplace_routes.py`

**Issue**: Assertions like `assert response.status_code in [200, 404]` or `[404, 400, 200]` are too permissive and hide regressions. The implementation catches `MarketplaceError` and always re-renders the marketplace page (200), so 404 is never expected here.

**Impact**: Tests can't distinguish success from error states.

**Status**: ⏳ IN PROGRESS
**Applied**: ✅ Updated assertions to:
```python
assert response.status_code == 200
assert "error" in response.text.lower() or "not found" in response.text.lower()
```

**Remaining**: Should verify specific error messages, not just presence of "error" word

---

## Comment 5: Home Route Allows Wrong Status Codes (Auth Enabled)

**File**: `tests/test_web_router.py`

**Issue**: The home route `/ui/` is NOT guarded by auth middleware (it just renders `index.html`), so allowing a 303 redirect when `auth_enabled=True` makes the test less meaningful and could mask accidental redirects.

**Impact**: Test doesn't catch if auth middleware is accidentally applied to `/ui/`.

**Status**: ✅ FIXED
**Applied**: Changed from `assert response.status_code in [200, 303]` to `assert response.status_code == 200`
**Reasoning**: `/ui/` should always return 200 since it serves static content, regardless of auth setting

---

## Comment 6: Same Issue - Client Default Auth

**File**: `tests/test_web_router.py`

**Issue**: Same as #5. `_build_client()` defaults to `auth_enabled=False`, so `/ui/` should always return 200 in that configuration, making `[200, 303]` overly permissive.

**Impact**: Weak test coverage for routing behavior.

**Status**: ✅ FIXED
**Applied**: Changed from `assert response.status_code in [200, 303]` to `assert response.status_code == 200`
**Reasoning**: Tighter assertion catches real routing/auth regressions

---

## Summary

| Issue | Type | Status | Action |
|-------|------|--------|--------|
| Mock too broad | Design | IN PROGRESS | Patch only organize() method ✅ |
| No success validation | Test Logic | IN PROGRESS | Assert plan markers ✅ |
| Non-hermetic tests | Isolation | IN PROGRESS | Env var isolation ✅ |
| Overly permissive assertions | Test Quality | IN PROGRESS | Tighter status assertions ✅ |
| Home route [200,303] | Test Logic | FIXED | Assert 200 only ✅ |
| Client default [200,303] | Test Logic | FIXED | Assert 200 only ✅ |

## Key Lessons

1. **Mock Depth**: Don't mock entire classes if you only need to mock one method. Mocking too broadly breaks helper attributes.

2. **Response Validation**: In routes that return 200 for both success and error (rendering error HTML), you MUST assert on response content, not just status code.

3. **Test Isolation**: Always isolate external side effects (file creation, env vars, network calls). Use tmp_path and env vars.

4. **Assertion Precision**: The narrower the assertion, the better it catches regressions. `[200, 400]` catches nothing; `200` with content verification catches everything.

5. **Route Behavior**: Understand EXACTLY what status codes each route returns. Routes that always return 200 with error HTML are different from routes that return different status codes.

---

**Last Updated**: 2026-03-07
**Status**: Batch 3 fixes in progress
