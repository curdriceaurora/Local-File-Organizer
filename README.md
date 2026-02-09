# File Organizer v2.0

[![CI](https://github.com/curdriceaurora/Local-File-Organizer/actions/workflows/ci.yml/badge.svg)](https://github.com/curdriceaurora/Local-File-Organizer/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-local%20report-blue)](htmlcov/index.html)

> AI-powered local file management. Privacy-first — runs 100% on your device.

## Highlights

- **Copilot Chat**: Natural-language assistant for organize/find/undo.
- **Terminal UI**: 8-view Textual TUI (Files, Analytics, Audio, History, Copilot, and more).
- **Full CLI**: Organize, rules, suggestions, dedupe, daemon, analytics, update.
- **Audio Intelligence**: Metadata extraction + classification (Phase 3).
- **Deduplication**: Hash and semantic detection (Phase 4).
- **Undo/Redo**: Operation history with reversible actions.
- **Methodologies**: PARA + Johnny Decimal.
- **Auto-Update**: GitHub Releases with rollback support.
- **Cross-Platform Builds**: macOS DMG (Intel + Apple Silicon), Windows installer, Linux AppImage.

## Screenshots

![TUI overview](file_organizer_v2/docs/assets/tui-overview.svg)

![TUI demo](file_organizer_v2/docs/assets/tui-demo.gif)

## Quick Start

```bash
cd file_organizer_v2
pip install -e .

# Pull models
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M

# Organize files (dry run first)
file-organizer organize ./Downloads ./Organized --dry-run

# Launch the TUI
file-organizer tui
```

## Documentation

- [User Guide](file_organizer_v2/docs/USER_GUIDE.md)
- [CLI Reference](file_organizer_v2/docs/CLI_REFERENCE.md)
- [Configuration Guide](file_organizer_v2/docs/CONFIGURATION.md)
- [Troubleshooting](file_organizer_v2/docs/TROUBLESHOOTING.md)
- [Tutorials](file_organizer_v2/docs/tutorials/README.md)

## Installation

### Prerequisites

- Python 3.9+
- Ollama

### Optional Feature Packs

```bash
pip install -e ".[audio]"
pip install -e ".[dedup]"
pip install -e ".[build]"
```

### Pre-built Binaries

Pre-built releases are available for macOS, Windows, and Linux via GitHub Releases.

## Development

```bash
# Run tests
pytest

# Lint
ruff check src/
```

## Configuration

Config lives in `config/file-organizer/config.yaml` relative to your config home. Override with `FILE_ORGANIZER_CONFIG`.

## Support

- [Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues)
- [Discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)

---

**Status**: Alpha | **Version**: 2.0.0-alpha.1 | **Last Updated**: 2026-02-09
