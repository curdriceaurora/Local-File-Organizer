# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Migrated PDF extraction from `PyPDF2` to `pypdf` (successor package) to resolve GHSA moderate vulnerability in `PyPDF2 3.0.1` (#848)
- Accepted risk for `ecdsa` (GHSA-wj6h-64fc-37mp, HIGH): transitive via `python-jose`; JWT algorithm is HS256 so `ecdsa` is never invoked
- Accepted risk for `diskcache` (GHSA-w8v5-vhqr-4h9v, MODERATE): transitive via `llama-cpp-python`; never imported by application code

## [2.0.0-alpha.3] - TBD

### Known Limitations

The following tests are currently skipped in the alpha.3 release:

| Category | Count | Reason | Status |
|----------|-------|--------|--------|
| Phase 3 Features | 12 | Audio/video metadata deferred to Phase 3 | Intentional |
| SSE Streaming | 2 | Server-Sent Events not yet implemented | Planned |

**Total skipped tests: 14**

#### Phase 3 Audio/Video Features (12 tests)

Deferred to Phase 3 roadmap:
- **Audio Metadata** (3 tests): MP3/WAV extraction, music tag parsing
- **Video Metadata** (3 tests): MP4 extraction, resolution detection, codec identification
- **Audio Transcription** (3 tests): MP3/WAV transcription, language detection
- **Video Processing** (3 tests): MP4 processing, scene detection, frame extraction

#### SSE Streaming (2 tests)

Server-Sent Events functionality for real-time progress updates:
- Organization stream cancellation
- File listing SSE endpoints

**Note:** Platform-specific conditional skips (22 skip conditions) are not included in this count as they represent expected behavior on different operating systems and environments.

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
