# File Organizer User Guide

## Overview

File Organizer is a privacy-first, local file management system. It combines an AI copilot, a Textual-based terminal UI, and an expanded CLI to organize files, detect duplicates, analyze storage, and apply methodologies like PARA and Johnny Decimal.

Everything runs on your device: no cloud uploads, no shared data.

## Installation

### Prerequisites

- **Python 3.9+**
- **Ollama** for local AI inference
- **8 GB RAM** minimum (16 GB recommended)

Optional:

- **FFmpeg** for audio and video preprocessing
- **GPU drivers** for accelerated inference (CUDA on NVIDIA, MPS/Metal on macOS)

### Install from Source

```bash
cd file_organizer_v2
pip install -e .
```

### Optional Feature Packs

```bash
# Audio transcription + metadata
pip install -e ".[audio]"

# Deduplication extras
pip install -e ".[dedup]"

# Build tooling for executables
pip install -e ".[build]"
```

### Install AI Models

```bash
# Text model
ollama pull qwen2.5:3b-instruct-q4_K_M

# Vision model
ollama pull qwen2.5vl:7b-q4_K_M
```

### Pre-built Binaries

Pre-built releases are available for macOS (Intel + Apple Silicon), Windows, and Linux. See the GitHub Releases page for the latest builds and auto-update compatibility.

## Getting Started

### Organize Files

```bash
# Organize a directory
file-organizer organize ./Downloads ./Organized

# Preview without moving files
file-organizer organize ./Downloads ./Organized --dry-run

# Short alias
fo organize ./Downloads ./Organized
```

### Interactive Copilot

```bash
# Interactive REPL
file-organizer copilot chat

# Single command
file-organizer copilot chat "organize ./Downloads"
```

Example conversation:

```
You> organize ./Downloads
Copilot> Organized 42 files into ./Organized (3 skipped, 0 failed).

You> undo
Copilot> Last operation undone.

You> find report.pdf
Copilot> Found 3 file(s) matching 'report.pdf'.
```

### Terminal UI (TUI)

Launch the full terminal interface:

```bash
file-organizer tui
```

![TUI overview](assets/tui-overview.svg)

Navigation:

| Key | View |
| --- | --- |
| 1 | Files — Browse and preview files |
| 2 | Organized — View organization preview |
| 3 | Analytics — Storage dashboard |
| 4 | Methodology — PARA / Johnny Decimal |
| 5 | Audio — Audio file browser |
| 6 | History — Undo/redo operations |
| 7 | Settings — Configuration |
| 8 | Copilot — AI chat |
| q | Quit |
| Tab | Cycle focus |

For a full shortcut list, see [docs/tutorials/tui-tour.md](tutorials/tui-tour.md).

## Organisation Rules

Rules automate file organisation based on conditions like extension, filename pattern, or size.

### Create Rules

```bash
# Move PDFs to Documents
file-organizer rules add pdf-to-docs --ext ".pdf" --action move --dest "Documents/PDFs"

# Archive large files
file-organizer rules add archive-large --ext ".zip,.7z" --action archive --dest "Archive" --priority 5

# Organize images by type
file-organizer rules add sort-images --ext ".jpg,.png,.gif" --action move --dest "Pictures/{ext}"
```

### Preview Rules

```bash
file-organizer rules preview ./Downloads
file-organizer rules preview ./Downloads --no-recursive
```

### Manage Rules

```bash
file-organizer rules list
file-organizer rules sets
file-organizer rules toggle pdf-to-docs
file-organizer rules remove pdf-to-docs
file-organizer rules export --output rules.yaml
file-organizer rules import rules.yaml
```

## Configuration

Configuration is stored in `config/file-organizer/config.yaml` relative to your config home directory. Override the location with `FILE_ORGANIZER_CONFIG`.

### Profiles

```bash
# View current config
file-organizer config show

# Edit settings
file-organizer config edit --text-model "qwen2.5:3b-instruct-q4_K_M"
file-organizer config edit --temperature 0.7
file-organizer config edit --device mps

# Named profiles
file-organizer config edit --profile work --methodology para
file-organizer config show --profile work
file-organizer config list
```

See the full schema in [docs/CONFIGURATION.md](CONFIGURATION.md).

## Audio Organisation

Audio files surface in the TUI Audio view with metadata and classification confidence. Install audio dependencies before use:

```bash
pip install -e ".[audio]"
```

Tutorial: [docs/tutorials/audio-organization.md](tutorials/audio-organization.md)

## Deduplication

Detect and resolve duplicates with the `dedupe` subcommands:

```bash
file-organizer dedupe scan ./Documents
file-organizer dedupe report ./Documents
file-organizer dedupe resolve ./Documents --strategy newest --dry-run
```

Tutorial: [docs/tutorials/dedupe-quickstart.md](tutorials/dedupe-quickstart.md)

## Undo/Redo

Every file operation is tracked and reversible:

```bash
file-organizer undo
file-organizer redo
file-organizer history --limit 20
file-organizer history --stats
```

In the TUI, open the History view (key `6`) and use `u` / `y`.

## Analytics

```bash
file-organizer analytics ./
```

The TUI Analytics view offers a dashboard with storage and dedupe insights.

Tutorial: [docs/tutorials/analytics-overview.md](tutorials/analytics-overview.md)

## Daemon Mode and File Watching

Use the daemon to watch directories and process incoming files automatically.

```bash
file-organizer daemon start --watch-dir ./inbox --output-dir ./organized
file-organizer daemon status
file-organizer daemon stop
```

You can also stream events or run a one-shot pipeline:

```bash
file-organizer daemon watch ./inbox
file-organizer daemon process ./inbox ./organized --dry-run
```

Tutorial: [docs/tutorials/daemon-watch.md](tutorials/daemon-watch.md)

## Methodologies (PARA + Johnny Decimal)

Set a default methodology and preview it in the TUI:

```bash
file-organizer config edit --methodology para
```

Tutorial: [docs/tutorials/para-jd-setup.md](tutorials/para-jd-setup.md)

## Smart Suggestions

Generate and apply AI suggestions based on detected patterns:

```bash
file-organizer suggest files ./Downloads
file-organizer suggest apply ./Downloads --dry-run
file-organizer suggest patterns ./Downloads
```

Auto-tagging is available via the legacy CLI (`python -m file_organizer.cli.autotag --help`) and uses the same intelligence signals.

## Profile Management

```bash
file-organizer profile list
file-organizer profile create work --activate
file-organizer profile export work --output work-profile.json
file-organizer profile import work-profile.json --as work-copy
```

## Auto-Update

```bash
file-organizer update check
file-organizer update install
file-organizer update install --dry-run
file-organizer update install --pre
file-organizer update rollback
```

Update checks run on TUI startup by default and are throttled by the configured interval. Set `FO_DISABLE_UPDATE_CHECK=1` to disable.

## Supported File Types

**Documents**: txt, md, pdf, docx, csv, xlsx, ppt, pptx, epub\
**Images**: jpg, png, gif, bmp, tiff\
**Video**: mp4, avi, mkv, mov, wmv\
**Audio**: mp3, wav, flac, m4a, ogg\
**Archives**: zip, 7z, tar, rar\
**Scientific**: hdf5, netcdf, mat\
**CAD**: dxf, dwg, step, iges

**Total**: 43 file types supported.

## Best Practices

- Start with `--dry-run` on new folders.
- Create a dedicated `inbox` folder for daemon workflows.
- Keep profiles small and task-focused (work, personal, archives).
- Use `rules preview` before enabling new rules.

## FAQ

**Does File Organizer upload my files?**
No. All processing happens locally.

**Can I use it without AI models?**
Basic organisation rules and manual flows work, but AI-based classification requires models.

**How do I reset configuration?**
Delete or rename `config/file-organizer/config.yaml` inside your config home directory.

## Troubleshooting

See [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.
