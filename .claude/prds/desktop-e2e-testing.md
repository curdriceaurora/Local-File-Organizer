---
name: desktop-e2e-testing
description: End-to-end UI testing for the Tauri desktop application across all platforms
status: backlog
created: 2026-03-02T14:25:52Z
updated: 2026-03-02T14:25:52Z
---

# PRD: Desktop E2E UI Testing

## Problem Statement

The Desktop UI has been merged with unit tests for individual Rust modules (47 tests) and Python backend services (70 tests), but no end-to-end testing validates the full user journey: app launch → splash screen → sidecar startup → web UI in webview → system tray interaction → clean shutdown. Without E2E tests, regressions in the integration layer will go undetected.

## Goals

1. Automated E2E tests covering the complete desktop app lifecycle
2. Test sidecar process management (start, health poll, shutdown)
3. Test system tray menu interactions
4. Test webview content loading and navigation
5. Test native notifications
6. Test daemon manager integration (launchd/systemd/Windows Service)
7. Cross-platform test matrix (macOS, Windows, Linux)

## Non-Goals

- Production builds and code signing (separate epic)
- Test coverage for Python backend modules (separate epic)
- Performance benchmarking

## Success Criteria

- [ ] E2E test suite covering 10+ user journeys
- [ ] Tests run in CI on all three platforms
- [ ] Sidecar lifecycle fully tested (start → ready → shutdown)
- [ ] System tray menu tested programmatically
- [ ] Average E2E suite runtime < 5 minutes per platform
- [ ] Zero flaky tests (retry tolerance < 2%)

## Technical Approach

### Phase 1: Test Infrastructure (1 week)

1. **Tauri test harness setup**
   - Configure `tauri-driver` or WebDriver-based testing
   - Set up test fixtures for sidecar binary (mock or real)
   - Create test helpers for common assertions (window state, tray state)

2. **CI integration**
   - GitHub Actions matrix for macOS, Windows, Linux
   - Screenshot capture on failure for debugging
   - Test artifact upload (logs, screenshots)

### Phase 2: Core Lifecycle Tests (2 weeks)

3. **App launch and splash screen**
   - App starts without errors
   - Splash screen displays with correct branding
   - Splash transitions to main window when sidecar reports "ready"
   - Error state shown when sidecar fails to start

4. **Sidecar process management**
   - Sidecar binary spawns on app start
   - Dynamic port assignment works (no port conflicts)
   - Health endpoint polling succeeds within timeout
   - Sidecar shuts down cleanly on app quit
   - Sidecar restart on unexpected crash

5. **Web UI in webview**
   - Web UI loads at correct URL (localhost:{dynamic_port}/ui/)
   - Navigation works (sidebar, pages)
   - CSP headers don't block legitimate resources
   - Window resize and fullscreen work

### Phase 3: Native Integration Tests (2 weeks)

6. **System tray**
   - Tray icon appears on all platforms
   - Menu items render correctly
   - "Organize Now" triggers API call
   - "Pause/Resume" toggles daemon state
   - "Settings" opens settings page
   - "Quit" shuts down app and sidecar

7. **Native notifications**
   - Notification shown on file organization complete
   - Notification click navigates to relevant view
   - Notification permissions handled correctly per platform

8. **Daemon manager**
   - launchd plist installation/removal (macOS)
   - systemd unit enable/disable (Linux)
   - Scheduled Task creation/deletion (Windows)
   - Auto-launch on login toggle works

### Phase 4: Error Handling & Edge Cases (1 week)

9. **Error scenarios**
   - Port already in use → app selects next available
   - Sidecar binary missing → error message shown
   - Network interface unavailable → graceful degradation
   - Multiple app instances → single instance enforcement

10. **Update flow**
    - Update check returns result
    - Update banner shown in webview
    - Download progress reported correctly

## Estimated Effort

- **Total**: 6-8 weeks
- **Test infrastructure**: 1 week
- **Core lifecycle**: 2 weeks
- **Native integration**: 2 weeks
- **Error handling**: 1 week
- **CI stabilization**: 1-2 weeks

## Dependencies

- Production builds working on all platforms (can use dev builds initially)
- Tauri test driver or WebDriver setup
- CI runners with GUI support (or headless mode)

## Risks

- Tauri E2E testing ecosystem is less mature than Electron's
- Cross-platform GUI testing may have flaky results
- CI runners may not support GUI interactions (headless limitations)
