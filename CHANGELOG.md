# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Accepted risk for `ecdsa` (GHSA-wj6h-64fc-37mp, HIGH): transitive via `python-jose`; JWT algorithm is HS256 so `ecdsa` is never invoked
- Accepted risk for `diskcache` (GHSA-w8v5-vhqr-4h9v, MODERATE): transitive via `llama-cpp-python`; never imported by application code

## [2.0.0-alpha.3] - 2026-03-26

### Quality & Stability Summary

This release contains **zero new user-facing features**—it is a pure quality and stability release covering 50 commits between March 9-26, 2026. The focus is on test infrastructure hardening, bug fixes, dependency updates, and security improvements that raise the project's reliability floor.

### Changed

- **Core Module Complexity Reduction** (#977): Refactored core modules to reduce cognitive complexity and improve maintainability
- **Test Parametrization** (#965, #966): Converted repetitive test cases to parametrized tests, reducing code duplication and improving coverage
- **Test Organization** (#964): Moved private helper tests to dedicated unit module for better test suite organization

### Fixed

- **Test Failures** (#969): Addressed 7 test failures across main test suite
- **pytest-timeout Compatibility** (#970): Pinned `pytest-timeout<2.4.0` to fix Windows CI crash
- **Path Keyword Matching** (f9ff398): Fixed feature extractor to match path keywords as exact components, not substrings
- **File Count Accuracy** (#937): Fixed deduplicated file counting in `OrganizationResult`
- **Threading Synchronization** (507cb35): Replaced busy-wait loop with `threading.Event().wait()` in test_warmup
- **Integration Test Stability** (#945): Fixed 5 failing integration tests on main branch
- **Flaky Assertions** (5b25653): Widened caplog scope to fix flaky cache-hit log assertion on Python 3.12

### Added

#### Testing & CI Improvements

- **Coverage Expansion**: Increased test coverage from 30% to 60% with ~4,500 new tests across integration, branch-coverage, and unit test suites
- **Branch Coverage** (#915): Enabled branch coverage tracking and established ratcheting coverage floors
- **Diff-Cover Gate** (#940): Added diff-cover gate to pre-commit validation to enforce coverage on changed lines
- **CI Guardrails**: Added 5 new guardrail categories:
  - T10 predicate negative-case guardrail (#939, #942)
  - MECE-hardened correctness, memory-lifecycle, and security guardrails (#935)
  - Search S1/S2 AST matching for corpus safety (#928, #929)
  - Phase 4 pre-commit hooks for threshold drift detection (#927)
  - isinstance assertion detection and enforcement (#926)
- **Integration Test Infrastructure** (#954): Added AsyncClient, CliRunner, and FakeTextModel fixtures
- **Integration Test Suites**:
  - 211 tests for methodologies, events, parallel processing (#963)
  - 4,112 integration tests ratcheting coverage 45%→60% (#961)
  - Web + plugins integration tests (#960)
  - API + web integration tests (#958)
  - CLI + models integration tests (#957)
  - 212 branch-coverage tests (#953, #949)
  - Branch-coverage tests for low-coverage modules (#947)

### Security

- **PyPDF2 Migration** (#848): Migrated PDF extraction from `PyPDF2` to `pypdf` (successor package) to resolve GHSA moderate vulnerability in `PyPDF2 3.0.1`
- **GitHub Actions Updates**: Bumped 6 GitHub Actions to latest versions:
  - `actions/upload-artifact` from 4 to 7 (#974)
  - `codecov/codecov-action` from 4.6.0 to 5.5.3 (#973)
  - `docker/metadata-action` from 5 to 6 (#975)
  - `docker/login-action` from 3 to 4 (#972)
  - `github/codeql-action` from 3 to 4 (#971)
  - `actions/checkout` from 5 to 6 (#875)
- **Rust Dependencies**: Updated 2 Rust dependencies:
  - `rustls-webpki` (#932)
  - `tar` (#923)
- **Risk Acceptance**:
  - Accepted risk for `ecdsa` (GHSA-wj6h-64fc-37mp, HIGH): transitive via `python-jose`; JWT algorithm is HS256 so `ecdsa` is never invoked
  - Accepted risk for `diskcache` (GHSA-w8v5-vhqr-4h9v, MODERATE): transitive via `llama-cpp-python`; never imported by application code

## [2.0.0-alpha.2] - 2026-03-09

### Added

- **Copilot Chat Interface** (#26): Natural-language AI assistant for file organisation
  - Interactive REPL and single-shot CLI modes
  - Intent parsing with 11 intent types (organize, move, rename, find, undo, redo, preview, suggest, status, help, chat)
  - Multi-turn conversation management with sliding-window context
  - TUI panel accessible via key `8`
- **Copilot Rules System** (#29): Automated file organisation rules
  - CRUD operations with YAML persistence
  - 8 condition types (extension, name pattern, size, content, date, path)
  - 7 action types (move, copy, rename, tag, categorize, archive, delete)
  - Preview engine for dry-run evaluation
  - CLI commands: list, sets, add, remove, toggle, preview, export, import
- **Auto-Update Mechanism** (#23): Self-updating from GitHub Releases
  - Version checking against GitHub Releases API
  - SHA256-verified downloads
  - Atomic binary replacement with backup/rollback
  - CLI commands: check, install, rollback
- **PyInstaller Build Pipeline** (#28): Cross-platform executable packaging
  - Build script with platform detection and spec generation
  - GitHub Actions CI for macOS (arm64/x86_64), Windows, Linux
- **macOS Packaging** (#14): DMG installer with optional code signing/notarization
- **Windows Packaging** (#16): Inno Setup installer with PATH integration
- **Linux Packaging** (#20): AppImage and tarball distribution
- **Integration Tests** (#12): 192 new tests across copilot, rules, updater, TUI, CLI, config, and build
- **User Documentation** (#13): User guide, CLI reference, configuration guide, troubleshooting

### Phase 2 Completion Summary

- Phase 2 (Enhanced UX) is now 100% complete: 24/24 tasks done
- TUI with 8 navigable views (Files, Organized, Analytics, Methodology, Audio, History, Settings, Copilot)
- Full CLI with 30+ sub-commands across 8 command groups
- 3,146 tests passing across Python 3.11-3.12
- ~54,000 LOC across 184 modules

## [2.0.0-alpha.1] - 2026-01-15

### Added

- Phase 1: Core text and image processing with Ollama
- Phase 3: Audio processing, PARA/JD methodologies, CAD/archive/scientific formats
- Phase 4: Deduplication, user preference learning, undo/redo, analytics
- Phase 5: Event system, daemon, Docker, CI/CD pipeline
