# B4: Marketplace Plugin Lifecycle E2E — Design

**Issue**: [#1157](https://github.com/curdriceaurora/Local-File-Organizer/issues/1157)
**Epic**: [#1150](https://github.com/curdriceaurora/Local-File-Organizer/issues/1150)
**Date**: 2026-04-08
**Status**: Approved

---

## Context

`tests/playwright/` currently covers organize workflow (B1), auth lifecycle (B2), and settings
persistence (B3). B4 adds coverage for the plugin marketplace UI: navigating to `/ui/marketplace`,
asserting plugin listings, installing a plugin ("enable"), and uninstalling it ("disable").

The issue uses "enable/disable" to mean install/uninstall — there is no separate enable/disable
control in the `/ui/marketplace` UI. The actual controls are **Install** and **Uninstall** buttons.

---

## Architecture

### HTMX swap model

The base template sets:

```html
<body hx-boost="true" hx-target="#main" hx-select="#main" hx-swap="innerHTML">
```

Every HTMX action (install, uninstall, update) POSTs to the server and swaps the `#main`
element with the corresponding fragment from the response. After install, the full plugin table
re-renders with the plugin now showing an **Uninstall** button. After uninstall, it re-renders
with the **Install** button.

### Flash message

`_render_marketplace_page` passes `message` and `message_kind` to the template. The template
renders:

```html
<section class="panel">
    <p class="organize-hint">{{ message }}</p>
</section>
```

Tests wait for `p.organize-hint` to confirm the server accepted the action.

### Auth

The live server in `conftest.py` runs with `auth_enabled=True`. The marketplace web routes carry
no explicit auth guard, but `authed_page` is used to ensure a valid session cookie is present
(the issue specifies reusing the B2 fixture, and future auth hardening may add a guard).

---

## Plugin Seeding Strategy

The `MarketplaceService` reads from a local file-based repository (a directory containing
`index.json` and plugin zip archives). The web route creates a fresh service instance per
request via `_service()`.

**Fixture approach**: Seed a real local stub plugin, patch the `_service()` factory function at
`file_organizer.web.marketplace_routes._service` so it returns the pre-configured service
instance for the duration of each test. This is the established seam — every existing integration
test in `tests/integration/test_marketplace_routes.py` patches `_service()` directly
(`patch("file_organizer.web.marketplace_routes._service")`). Patching the factory rather than the
class is simpler (one indirection level) and consistent with the rest of the test suite.

The stub plugin uses the archive format established in `tests/plugins/test_marketplace_core.py`
(`_write_plugin_archive`, lines 28–73). The zip must contain `plugin.py` with a minimal `Plugin`
subclass; `index.json` must include every field that `MarketplaceService` and `PluginInstaller`
require. The full known-good metadata shape (all fields required):

```python
{
    "name": "fo-test-echo",
    "version": "1.0.0",
    "author": "tests",
    "description": "fo-test-echo plugin",
    "homepage": "https://example.invalid",
    "download_url": "fo-test-echo-1.0.0.zip",   # relative to repo_dir
    "checksum_sha256": "<sha256-of-archive>",
    "size_bytes": <archive-stat.st_size>,
    "dependencies": [],
    "tags": ["utility"],
    "category": "utility",
    "license": "MIT",
    "min_organizer_version": "2.0.0",
    "max_organizer_version": None,
    "downloads": 0,
    "rating": 0.0,
    "reviews_count": 0,
}
```

`checksum_sha256` and `size_bytes` must be computed from the actual archive on disk
(`compute_sha256` is exported from `file_organizer.plugins.marketplace`). The index payload
wraps the list: `{"plugins": [<metadata-dict>]}`.

**Plugin name**: `fo-test-echo` (documented in the module docstring so it is easy to locate).

---

## File

```text
tests/playwright/test_marketplace_lifecycle.py
```

---

## Fixtures

### `_marketplace_service` (function-scoped, autouse=False)

1. Create `tmp_path / "home"` → `home` (function-scoped `tmp_path`)
2. Create `home / "repository"` → `repo_dir`
3. Write `fo-test-echo-1.0.0.zip` into `repo_dir` (minimal `Plugin` subclass matching the shape in `_write_plugin_archive`)
4. Compute `checksum_sha256` via `compute_sha256(archive_path)` and read `size_bytes` from `archive_path.stat().st_size`
5. Write `repo_dir / "index.json"` as `{"plugins": [<full-metadata-dict>]}`
6. Instantiate `MarketplaceService(home_dir=home, repo_url=str(repo_dir))`
7. `patch("file_organizer.web.marketplace_routes._service", return_value=<instance>)`
8. Yield plugin name `"fo-test-echo"`

Because `tmp_path_factory` is session-scoped but the fixture is function-scoped, each test gets
a fresh `home` directory. Installed-state side effects (writes to `home/installed.json`) are
automatically discarded when the next test creates a new `home`.

---

## Tests

### `test_marketplace_page_lists_stub_plugin`

**Purpose**: Verify the page loads and the seeded plugin appears.

1. Navigate to `/ui/marketplace` (via `authed_page`)
2. Wait for `#plugins-tbody` to be visible
3. Assert a table row containing `"fo-test-echo"` is present
4. Assert an **Install** button is visible within that row (plugin is not yet installed)

### `test_install_uninstall_round_trip`

**Purpose**: Full install → uninstall lifecycle — the B4 "enable → disable" round-trip.

1. Navigate to `/ui/marketplace`
2. Wait for the `fo-test-echo` row to be visible
3. **Install phase**:
   - Click the **Install** button within the row
   - Wait for `p.organize-hint` to become visible (flash confirms server wrote `installed.json`)
   - Assert the row now shows an **Uninstall** button (Install button gone)
4. **Uninstall phase**:
   - Click the **Uninstall** button within the row
   - Wait for `p.organize-hint` to become visible again
   - Assert the row now shows an **Install** button (Uninstall button gone)

---

## State Isolation

- Function-scoped `_marketplace_service` fixture gives each test a clean `home` directory.
- No shared mutable state between tests.
- `authed_page` is already function-scoped; no additional session cleanup needed.

---

## Marks and Configuration

```python
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.playwright,
    pytest.mark.timeout(60),
]
```

Consistent with B1, B2, B3.

---

## Out of Scope

- Plugin installation from an external URL (non-goal per issue)
- Plugin configuration UI beyond install/uninstall
- Marketplace API tests (already at API level)
- Update button flow (separate from the enable/disable round-trip goal)

---

## Definition of Done

- [ ] `test_marketplace_page_lists_stub_plugin` passes
- [ ] `test_install_uninstall_round_trip` passes (install → uninstall round-trip)
- [ ] Module docstring documents `fo-test-echo` as the stable test target
- [ ] Each test is state-isolated via function-scoped fixture
- [ ] All quality gates pass (pre-commit → code-reviewer)
- [ ] `#1157` closed; `#1150` child checklist updated

### Verification commands

```bash
# 1. New marketplace lifecycle tests — both pass on chromium
pytest tests/playwright/test_marketplace_lifecycle.py \
    --browser chromium --override-ini='addopts='

# 2. Regression: rest of playwright suite still passes on chromium
pytest tests/playwright/ -k "not test_marketplace_lifecycle" \
    --browser chromium --override-ini='addopts='

# 3. Full cross-browser matrix (matches CI playwright job — deferred to CI)
pytest tests/playwright/ --browser chromium --override-ini='addopts='
pytest tests/playwright/ --browser firefox  --override-ini='addopts='
pytest tests/playwright/ --browser webkit   --override-ini='addopts='
```

Cross-browser coverage (firefox, webkit) is not required locally before merging; CI runs the
full matrix on every PR.
