---
name: desktop-e2e-testing
status: backlog
created: 2026-03-02T14:30:36Z
updated: 2026-03-02T14:30:36Z
progress: 0%
prd: .claude/prds/desktop-e2e-testing.md
github: Will be updated when synced to GitHub
---

# Epic: Desktop E2E UI Testing

## Overview

Create an automated end-to-end test suite for the Tauri desktop application. Unit tests exist for individual Rust modules (47 tests) and Python backend services (70 tests), but no tests validate the full user journey: app launch → splash screen → sidecar startup → web UI in webview → system tray interaction → clean shutdown. This epic fills that gap.

## Architecture Decisions

- **Tauri's built-in `tauri-driver`** (WebDriver protocol) for E2E automation — native Tauri support, no Selenium overhead
- **`cargo test` integration tests** in `desktop/src-tauri/tests/` for Rust-side E2E (sidecar lifecycle, tray)
- **Mock sidecar** for fast CI tests — a minimal HTTP server that responds to `/health` and key endpoints, avoiding PyInstaller dependency in E2E test CI
- **Screenshot-on-failure** via WebDriver for debugging CI failures
- **Platform-specific test subsets** — daemon manager tests only run on their target OS

## Technical Approach

### Test Infrastructure

- `tauri-driver` installed as dev dependency for WebDriver-based webview testing
- Mock sidecar binary (small Rust binary or Python script) for test isolation
- Test fixtures for common scenarios (healthy sidecar, crashed sidecar, port conflict)
- CI matrix: macOS, Windows, Linux with GUI support (or headless via `xvfb` on Linux)

### Core Lifecycle Tests

- App start → splash screen visible → sidecar spawns → health poll succeeds → main window loads
- Sidecar crash → error state displayed → restart attempted
- Multiple instance prevention (single-instance lock)
- Clean shutdown: quit → sidecar process terminated → no orphan processes

### Native Integration Tests

- System tray: icon appears, menu items render, clicks trigger correct actions
- Notifications: shown on events, click navigates correctly
- Daemon manager: plist/systemd unit/scheduled task CRUD operations (platform-specific)

### Error & Edge Case Tests

- Port conflict → dynamic port reassignment
- Missing sidecar binary → user-facing error message
- Webview CSP enforcement (no external resource loading)

## Task Breakdown Preview

- [ ] Task 1: E2E test infrastructure (tauri-driver, mock sidecar, CI setup)
- [ ] Task 2: App lifecycle tests (launch, splash, sidecar ready, shutdown)
- [ ] Task 3: Sidecar process management tests (spawn, health poll, crash recovery)
- [ ] Task 4: Webview content tests (UI loads, navigation, CSP)
- [ ] Task 5: System tray and notification tests
- [ ] Task 6: Daemon manager integration tests (platform-specific)
- [ ] Task 7: Error handling and edge case tests
- [ ] Task 8: CI stabilization and screenshot-on-failure

## Dependencies

- Tauri project compiles successfully (completed in Desktop UI epic)
- `tauri-driver` or equivalent WebDriver tooling
- CI runners with GUI support (macOS/Windows native, Linux via xvfb)
- Mock sidecar binary for test isolation

## Success Criteria (Technical)

- 10+ E2E test scenarios covering all user journeys
- Tests pass on all three platforms in CI
- Average suite runtime < 5 minutes per platform
- Flaky test rate < 2% (measured over 20 CI runs)
- Screenshot artifacts captured on every failure
- Sidecar lifecycle fully validated (start → ready → shutdown → no orphans)

## Estimated Effort

- **Total**: 6-8 weeks
- **Test infrastructure + mock sidecar**: 1 week
- **Core lifecycle tests**: 2 weeks
- **Native integration tests**: 2 weeks
- **Error handling + edge cases**: 1 week
- **CI stabilization**: 1-2 weeks
