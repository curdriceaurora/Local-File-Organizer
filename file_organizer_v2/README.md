# File Organizer v2.0

[![CI](https://github.com/curdriceaurora/Local-File-Organizer/actions/workflows/ci.yml/badge.svg)](https://github.com/curdriceaurora/Local-File-Organizer/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-local%20report-blue)](../htmlcov/index.html)

> AI-powered local file management. Privacy-first — runs 100% on your device.

**3,146 tests** | **184 modules** | **43 file types** | Python 3.9+

## Features

- **AI-Powered Organisation**: Qwen 2.5 3B (text) + Qwen 2.5-VL 7B (vision) via Ollama
- **Copilot Chat**: Natural-language assistant — "organise ./Downloads", "find report.pdf", "undo"
- **Organisation Rules**: Automated sorting with conditions, preview, and YAML persistence
- **Terminal UI**: 8-view Textual TUI (Files, Analytics, Audio, History, Copilot, and more)
- **Full CLI**: Organize, rules, suggest, dedupe, daemon, analytics, update, profiles
- **Auto-Update**: GitHub Releases checks with verified downloads and rollback
- **Intelligence**: Pattern learning, preference tracking, smart suggestions, auto-tagging
- **Deduplication**: Hash and semantic duplicate detection
- **Undo/Redo**: Full operation history
- **PARA + Johnny Decimal**: Built-in organisational methodologies
- **Cross-Platform**: macOS (DMG), Windows (installer), Linux (AppImage) executables

## Screenshots

![TUI overview](docs/assets/tui-overview.svg)

![TUI demo](docs/assets/tui-demo.gif)

## Quick Start

```bash
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

- [User Guide](docs/USER_GUIDE.md)
- [CLI Reference](docs/CLI_REFERENCE.md)
- [Configuration Guide](docs/CONFIGURATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Tutorials](docs/tutorials/README.md)

## Optional Feature Packs

```bash
pip install -e ".[audio]"
pip install -e ".[dedup]"
pip install -e ".[build]"
```

## Development

```bash
# Run tests
pytest

# Lint
ruff check src/
```

## Configuration

Config lives in `config/file-organizer/config.yaml` relative to your config home. Override with `FILE_ORGANIZER_CONFIG`.

---

**Status**: Alpha | **Version**: 2.0.0-alpha.1 | **Last Updated**: 2026-02-09
