# File Organizer v2.0

[![CI](https://github.com/curdriceaurora/Local-File-Organizer/actions/workflows/ci.yml/badge.svg)](https://github.com/curdriceaurora/Local-File-Organizer/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-user%20guide-blue)](docs/USER_GUIDE.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0--alpha.3-orange)](CHANGELOG.md)

> AI-powered local file management. Local-first by default (Ollama, no cloud required) --
> or connect any OpenAI-compatible endpoint or Anthropic Claude when you need it.

**840 tests** | **408 modules** | **39 file types**

![TUI overview](docs/assets/tui-overview.svg)

## Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Web UI](#web-ui-preview)
- [Documentation](#documentation)
- [Optional Feature Packs](#optional-feature-packs)
- [Project Structure](#project-structure)
- [Development](#development)
- [Contributing](#contributing)
- [Configuration](#configuration)
- [License](#license)

## Features

### AI and Analysis

- **AI-Powered Organization**: Qwen 2.5 3B (text) + Qwen 2.5-VL 7B (vision) via Ollama — or any OpenAI-compatible endpoint (OpenAI, LM Studio, vLLM) — or Anthropic Claude
- **Audio Transcription**: Local speech-to-text with faster-whisper (GPU-accelerated)
- **Video Analysis**: Scene detection and keyframe extraction
- **Intelligence**: Pattern learning, preference tracking, smart suggestions, auto-tagging

### Interfaces

- **Terminal UI**: 8-view Textual TUI (Files, Analytics, Audio, History, Copilot, and more)
- **Web UI**: Browser-based interface via FastAPI and HTMX
- **Desktop App**: Native OS window via pywebview — single Python process, no Electron, no Rust
- **Full CLI**: Organize, rules, suggest, dedupe, daemon, analytics, update, profiles
- **Copilot Chat**: Natural-language assistant -- "organize ./Downloads", "find report.pdf", "undo"

### Organization

- **Organization Rules**: Automated sorting with conditions, preview, and YAML persistence
- **PARA + Johnny Decimal**: Built-in organizational methodologies
- **Deduplication**: Hash and semantic duplicate detection
- **Undo/Redo**: Full operation history
- **Auto-Update**: GitHub Releases checks with verified downloads and rollback
- **Cross-Platform**: macOS (DMG), Windows (installer), Linux (AppImage) executables

## How It Works

```
 Source Directory          AI Analysis              Organized Output
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  ./Downloads │     │  Content         │     │  ./Organized     │
│              │     │  Extraction      │     │                  │
│  report.pdf  │────>│  (text, vision,  │────>│  Work/           │
│  photo.jpg   │     │   audio, video)  │     │    Reports/      │
│  meeting.mp3 │     │                  │     │  Photos/         │
│  clip.mp4    │     │  AI Categorize   │     │    Vacation/     │
│  notes.txt   │     │  (Ollama/OpenAI/ │     │  Audio/          │
│              │     │   Claude)        │     │    Meetings/     │
└──────────────┘     └──────────────────┘     └──────────────────┘
                              │
                     ┌────────┴────────┐
                     │  Learn & Adapt  │
                     │  (patterns,     │
                     │   preferences,  │
                     │   rules)        │
                     └─────────────────┘
```

1. **Scan** — Reads files from a source directory, extracting text, metadata, and visual content per file type (80+ formats supported)
2. **Analyze** — Sends extracted content to an AI model (Ollama, OpenAI, or Claude) for categorization and naming
3. **Organize** — Moves or copies files into a structured folder hierarchy with AI-generated names
4. **Learn** — Tracks your patterns and preferences over time for smarter future suggestions

## Screenshots

![TUI demo](docs/assets/tui-demo.gif)

## Quick Start

### With Ollama (local, default)

```bash
pip install -e ".[desktop]"

# Pull models
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M

# Organize files (dry run first)
file-organizer organize ./Downloads ./Organized --dry-run

# Launch the TUI
file-organizer tui

# Launch the native desktop window
file-organizer-desktop
```

### With OpenAI or compatible API

```bash
pip install -e ".[cloud]"

export FO_PROVIDER=openai
export OPENAI_API_KEY=sk-...
file-organizer organize ./Downloads ./Organized --dry-run
```

### With Anthropic Claude

```bash
pip install -e ".[claude]"

export FO_PROVIDER=claude
export ANTHROPIC_API_KEY=sk-ant-...
file-organizer organize ./Downloads ./Organized --dry-run
```

## Web UI (Preview)

Start the FastAPI server and open the UI:

```bash
uvicorn file_organizer.api.main:app --reload
```

Then visit `http://localhost:8000/ui/` for the HTMX interface.

## Documentation

- [Getting Started](docs/getting-started.md)
- [User Guide](docs/USER_GUIDE.md)
- [CLI Reference](docs/cli-reference.md)
- [Desktop App Guide](docs/desktop-app.md)
- [Configuration Guide](docs/CONFIGURATION.md)
- [Troubleshooting](docs/troubleshooting.md)

## Optional Feature Packs

| Pack | Install Command | Features |
|------|----------------|----------|
| Cloud | `pip install -e ".[cloud]"` | OpenAI-compatible API provider (OpenAI, LM Studio, vLLM) |
| Claude | `pip install -e ".[claude]"` | Anthropic Claude API provider (text + vision) |
| LLaMA | `pip install -e ".[llama]"` | Local llama.cpp inference (GGUF models, no Ollama needed) |
| Audio | `pip install -e ".[audio]"` | Speech-to-text (faster-whisper, torch) |
| Video | `pip install -e ".[video]"` | Scene detection (OpenCV, scenedetect) |
| Dedup | `pip install -e ".[dedup]"` | Image deduplication (perceptual hashing) |
| Archive | `pip install -e ".[archive]"` | 7z and RAR archive support |
| Scientific | `pip install -e ".[scientific]"` | HDF5, NetCDF, MATLAB formats |
| CAD | `pip install -e ".[cad]"` | DXF and CAD format support |
| Desktop | `pip install -e ".[desktop]"` | Native desktop window via pywebview (uvicorn + WebKit/Edge) |
| Build | `pip install -e ".[build]"` | Executable packaging (PyInstaller) |
| All | `pip install -e ".[all]"` | Everything above |

### Audio system dependencies

For full audio format support, the `[audio]` pack uses **FFmpeg** (all platforms) and optionally **CUDA + cuDNN** (NVIDIA GPU users).

**FFmpeg** — required for non-`.wav` formats (MP3, M4A, FLAC, OGG); optional if you only transcribe raw `.wav`:

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows (winget)
winget install ffmpeg
```

**CUDA + cuDNN** — optional, for significantly faster transcription (see [faster-whisper benchmarks](https://github.com/SYSTRAN/faster-whisper) for hardware-specific numbers):

```bash
# Install CUDA Toolkit from https://developer.nvidia.com/cuda-downloads
# Install cuDNN from https://developer.nvidia.com/cudnn

# Verify the full transcription backend (not just PyTorch)
python3 -c "from faster_whisper import WhisperModel; print('faster-whisper OK')"
python3 -c "import torch; print('CUDA:', torch.cuda.is_available())"
```

**Fallback behavior**: without FFmpeg, only `.wav` files are transcribed; other formats are organized by filename/metadata but not content-analyzed. Without CUDA, transcription runs on CPU (slower but fully functional).

See the [Installation Guide](docs/admin/installation.md) for troubleshooting and advanced configuration.

## Project Structure

<details>
<summary>Click to expand</summary>

```
src/file_organizer/
├── api/              # FastAPI web backend
├── cli/              # CLI commands and entry points
├── client/           # HTTP client utilities
├── config/           # Configuration management
├── core/             # Organization engine and business logic
├── daemon/           # Background file watcher daemon
├── deploy/           # Deployment helpers
├── desktop/          # Native desktop app (pywebview)
├── events/           # Event system
├── history/          # Operation history and undo/redo
├── integrations/     # External service integrations
├── interfaces/       # Abstract interfaces and protocols
├── methodologies/    # PARA, Johnny Decimal implementations
├── models/           # Data models
├── optimization/     # Performance optimization
├── parallel/         # Parallel processing
├── pipeline/         # File processing pipeline
├── plugins/          # Plugin system (audio, video, archives, etc.)
├── review_regressions/ # Code quality detectors
├── services/         # Core services (analytics, dedup, text, etc.)
├── tui/              # Textual terminal UI (8 views)
├── undo/             # Undo/redo infrastructure
├── updater/          # Auto-update from GitHub Releases
├── utils/            # Shared utilities
├── watcher/          # File system watcher
└── web/              # HTMX web UI templates and assets
```

</details>

## Development

```bash
# Run tests
pytest

# Lint
ruff check src/
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and how to submit changes.

## Configuration

Configuration is stored in platform-appropriate locations using `platformdirs`:
- **macOS**: `~/Library/Application Support/file-organizer/`
- **Linux**: `~/.config/file-organizer/` (or `$XDG_CONFIG_HOME/file-organizer/`)
- **Windows**: `%APPDATA%/file-organizer/`

See [Configuration Guide](docs/CONFIGURATION.md) for details.

## License

This project is licensed under the [MIT License](LICENSE).

---

**Status**: Alpha 3 | **Version**: 2.0.0-alpha.3 | **Last Updated**: 2026-04-10
