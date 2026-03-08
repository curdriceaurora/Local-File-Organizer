# PR #562 Triage Report

## Summary

- Total comments fetched: 110 inline (80 CodeRabbit, 25 Copilot, 5 GitHub Advanced Security)
- Total review-level summaries: 5 (2 Copilot, 2 CodeRabbit, 1 GHAS — not counted as findings)
- Trivial/duplicate filtered out: 10 (code suggestion fragments, Copilot example snippet lines)
- **Substantive findings classified: 113**
- **New pattern candidates: 8** (U1–U8)

## Pattern Tally

| Pattern ID | Name | Count | Example (truncated) |
|------------|------|-------|---------------------|
| D5 | WRONG_FORMAT | 18 | "Fix heading spacing to satisfy MD022 (epic task files)" |
| F4 | SECURITY_VULN | 14 | "CSP permits unsafe-inline in Tauri webview; AppleScript/shell injection via filename" |
| U6 | DYNAMIC_IMPORT_ANTIPATTERN | 11 | "Replace `__import__(...)` in default_factory with explicit module import" |
| F1 | MISSING_ERROR_HANDLING | 9 | "Health endpoint swallows all exceptions with no logging before returning 503" |
| F5 | HARDCODED_VALUE | 7 | "Splash screen hard-codes log path `~/.config/...` not portable across platforms" |
| U2 | DATA_MIGRATION_MISSING | 6 | "Migrate existing integration state before switching default root to platformdirs" |
| U4 | PACKAGING_DEFECT | 5 | "Inno Setup calls idpAddFile() without IDP plugin include — iscc will fail to compile" |
| C4 | COVERAGE_GATE | 4 | "Add required pytest markers to test module (CI gate compliance)" |
| F8 | WRONG_ABSTRACTION | 4 | "Daemon methods create ephemeral instances that cannot control a running daemon" |
| U5 | RUST_PANIC_RISK | 4 | "`app.default_window_icon().unwrap()` can panic if no icon configured" |
| F2 | TYPE_ANNOTATION | 3 | "Annotate untyped fixtures; normalize OLLAMA_HOST to URL before use" |
| U3 | SIDECAR_NAMING_MISMATCH | 3 | "ARCH-only name (x86_64) vs full Rust triple (x86_64-unknown-linux-gnu) causes startup failure" |
| G4 | UNUSED_CODE | 3 | "Remove unused imports; remove unused shell:default permission from capabilities" |
| T1 | WEAK_ASSERTION | 3 | "Test exercises new status/readiness fields but doesn't assert HTTP status contract (200/207/503)" |
| D6 | CONTRADICTION | 2 | "depends_on and conflicts_with both include task 544; SidecarStatePayload docs say 'running' but emits 'ready'" |
| F6 | API_CONTRACT_BROKEN | 2 | "Sidecar never transitions to Ready: start() emits only 'starting', splash/tray never observes readiness" |
| U7 | ENTITLEMENT_MISCONFIG | 2 | "Replace allow-unsigned-executable-memory with allow-jit in production entitlements" |
| U8 | PLATFORM_VERSION_COMPAT | 2 | "Dolphin service menu path targets KDE 5; needs update for KDE Plasma 6" |
| D1 | INACCURATE_CLAIM | 1 | "Splash path in task doc says desktop/src/splash.html; actual is desktop/src-tauri/src/splash.html" |
| D2 | STALE_REFERENCE | 1 | "Daemon task references incorrect Tauri source tree paths" |
| C1 | FLAKY_GATE | 1 | "Do not unconditionally disable package-build tests" |
| C2 | WRONG_TRIGGER | 1 | "`find dist -type f -perm +111` not portable on macOS BSD find; breaks CI matrix build" |
| C3 | CACHE_MISCONFIG | 1 | "Add --locked flag to cargo commands in CI for deterministic dependency resolution" |
| C6 | SLOW_WORKFLOW | 1 | "Do not unignore entire desktop/build tree in CI artifacts (bloats artifact storage)" |
| U1 | DEPRECATED_ACTION | 1 | "Prefer dtolnay/rust-toolchain over deprecated actions-rs/toolchain" |
| F7 | RESOURCE_NOT_CLOSED | 1 | "TrayIcon RAII handle dropped when create_tray() returns, removing tray icon immediately" |
| G5 | NAMING_CONVENTION | 1 | "Constructor docstring does not match new default path behavior after platformdirs migration" |
| T7 | BRITTLE_ASSERTION | 1 | "Test searches for substring 'idecar' (typo for 'sidecar') — false pass on wrong string" |
| T6 | PERMISSIVE_FILTER | 1 | "Repeated file reads in tests; should use pytest fixture for shared setup" |

**Total: 113 classified findings**

## UNKNOWN Findings (New Pattern Candidates)

### Candidate U1: DEPRECATED_ACTION
**Count**: 1 occurrence
**Description**: A CI GitHub Action step uses a deprecated third-party action (actions-rs/toolchain) that should be replaced with the canonical maintained alternative (dtolnay/rust-toolchain).
**Example**: "Prefer `dtolnay/rust-toolchain` over deprecated `actions-rs/toolchain`"

---

### Candidate U2: DATA_MIGRATION_MISSING
**Count**: 6 occurrences
**Description**: When a default storage path changes (e.g., to platformdirs), existing user data at the old location is silently abandoned rather than migrated or providing a legacy fallback — causing data loss on upgrade.
**Example**: "Migrate existing integration state before switching default root to platformdirs; use resolve_legacy_path() pattern so legacy non-empty directories are still preferred"

---

### Candidate U3: SIDECAR_NAMING_MISMATCH
**Count**: 3 occurrences
**Description**: A native desktop sidecar binary is named using only CPU architecture (`ARCH`) but the packaging/discovery system expects a full Rust target triple (`x86_64-unknown-linux-gnu`); the binary cannot be found at runtime on any platform.
**Example**: "Critical sidecar binary naming mismatch: `std::env::consts::ARCH` yields `x86_64` but Tauri externalBin expects `x86_64-unknown-linux-gnu`"

---

### Candidate U4: PACKAGING_DEFECT
**Count**: 5 occurrences
**Description**: Platform-specific installer/packaging scripts contain defects that prevent correct installation: missing plugin includes (Inno Setup IDP), build-time path checks used at install time (always false on end-user machine), non-idempotent file copies, and dangerous broad-match process kill in maintainer scripts.
**Example**: "Inno Setup script calls `idpAddFile(...)` but there's no IDP plugin include; `iscc` will fail to compile"

---

### Candidate U5: RUST_PANIC_RISK
**Count**: 4 occurrences
**Description**: Rust code uses `.unwrap()` on `Option`/`Result` values that can be `None`/`Err` in valid deployment configurations (e.g., missing bundle icon, failed lock acquisition, logical dead code branch), causing panic instead of graceful error handling.
**Example**: "`app.default_window_icon().unwrap()` can panic if no default window icon is available on platform-specific builds"

---

### Candidate U6: DYNAMIC_IMPORT_ANTIPATTERN
**Count**: 11 occurrences
**Description**: `__import__(...)` is used inline inside `default_factory` lambdas or search lists to lazily load config path helpers, making code harder to read, confusing type checkers, and inconsistent with normal Python import conventions. The fix is always a top-level or local explicit import.
**Example**: "This `__import__(...)` call inside the default-config search list is indirect and inconsistent with the rest of the module; a straightforward import of `get_config_dir()` would be clearer"

---

### Candidate U7: ENTITLEMENT_MISCONFIG
**Count**: 2 occurrences
**Description**: macOS app entitlements files use deprecated or incorrect entitlement keys (e.g., `allow-unsigned-executable-memory` instead of `allow-jit`) or are missing required assets (Retina `@2x` icon at 1024×1024), leading to App Store rejection or broken behavior on high-DPI displays.
**Example**: "Replace `allow-unsigned-executable-memory` with `allow-jit` in production entitlements.plist"

---

### Candidate U8: PLATFORM_VERSION_COMPAT
**Count**: 2 occurrences
**Description**: Installation paths or commands target an older version of a platform subsystem (KDE Plasma 5 service menu path, relative vs. absolute paths in Debian postinst) that are incompatible with the current version (KDE Plasma 6, guaranteed working directory).
**Example**: "Update Dolphin service menu installation path from KDE 5 location to KDE Plasma 6 compatible path"

## Notes on Cross-Cutting Distribution

**Dominant work type: FEATURE (40 findings, 35%)** — Driven by the breadth of new Tauri/sidecar code. Security vulnerabilities (F4, 14 findings) were the single largest pattern, spanning AppleScript injection, shell injection via desktop entry `%f`, JSON injection via unescaped paths, Tauri CSP `unsafe-inline`, and unvalidated WebView2 bootstrapper execution. Missing error handling (F1, 9 findings) was second, concentrated in the health endpoint and sidecar lifecycle.

**Second: DOCS (22 findings, 19%)** — Almost entirely MD022 heading-spacing violations (18 of 22) in the epic task markdown files created alongside the feature work. These are mechanical formatting failures, not substantive documentation errors, but they inflated the count significantly.

**Third: UNKNOWN/NEW patterns (34 findings, 30%)** — The highest proportion of new-pattern findings in any PR triaged so far. Eight new pattern candidates were identified, all driven by the desktop/native nature of the work: sidecar naming, Rust panics, macOS entitlements, KDE Plasma version compatibility, Windows packaging defects, data migration gaps when switching to platformdirs, and the `__import__()` antipattern used across 11+ call sites during the platformdirs migration. These are strong candidates for adding to the audit catalog.

**CI (8 findings, 7%)** — Mostly pytest marker compliance (4), plus one portability bug in CI shell (`perm +111`), one cache determinism issue (no `--locked` for cargo), one disabled test gate, and one artifact bloat issue.

**Test (5 findings, 4%)** — Relatively light; the new tests were mostly structurally correct but had weak HTTP status assertions and one typo in a substring match (`"idecar"` instead of `"sidecar"`).
