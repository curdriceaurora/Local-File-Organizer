# File Organizer User Guide

## Overview

File Organizer is an AI-powered local file management system that organises your files intelligently using local LLMs. Everything runs on your device — no cloud, no data sharing.

## Installation

### Prerequisites

- **Python 3.9+**
- **Ollama** for local AI inference
- **8 GB RAM** minimum (16 GB recommended)
- **~10 GB disk** for AI models

### Install from Source

```bash
cd file_organizer_v2
pip install -e .
```

### Install AI Models

```bash
# Text model (~1.9 GB)
ollama pull qwen2.5:3b-instruct-q4_K_M

# Vision model (~6.0 GB)
ollama pull qwen2.5vl:7b-q4_K_M
```

### Pre-built Binaries

Download from the [Releases page](https://github.com/curdriceaurora/Local-File-Organizer/releases):

- **macOS**: `.dmg` installer (arm64 / x86_64)
- **Windows**: `.exe` installer (x86_64)
- **Linux**: `.AppImage` or `.tar.gz` (x86_64)

## Getting Started

### Organize Files

```bash
# Organize a directory
file-organizer organize ~/Downloads ~/Organized

# Preview without moving files
file-organizer organize ~/Downloads ~/Organized --dry-run

# Short alias
fo organize ~/Downloads ~/Organized
```

### Interactive Copilot

The copilot provides a natural-language chat interface:

```bash
# Interactive REPL
file-organizer copilot chat

# Single command
file-organizer copilot chat "organize ~/Downloads"
```

**Example conversation:**
```
You> organize my Downloads folder
Copilot> Organised 42 files from ~/Downloads into ~/Downloads/organized
         (3 skipped, 0 failed).

You> undo
Copilot> Last operation undone.

You> find report.pdf
Copilot> Found 3 file(s) matching 'report.pdf':
           - ~/Documents/Q4-report.pdf
           - ~/Downloads/annual-report.pdf
           - ~/Desktop/report.pdf
```

### Terminal UI (TUI)

Launch the full terminal user interface:

```bash
file-organizer tui
```

**Navigation:**
| Key | View |
|-----|------|
| 1 | Files — Browse and preview files |
| 2 | Organized — View organization results |
| 3 | Analytics — Storage metrics dashboard |
| 4 | Methodology — PARA / Johnny Decimal |
| 5 | Audio — Audio file browser |
| 6 | History — Undo/redo operations |
| 7 | Settings — Configuration |
| 8 | Copilot — AI chat interface |
| q | Quit |
| Tab | Cycle focus |

## Organisation Rules

Rules automate file organisation based on conditions like extension, name pattern, or size.

### Create Rules

```bash
# Move PDFs to Documents
file-organizer rules add pdf-to-docs --ext ".pdf" --action move --dest "~/Documents/PDFs"

# Archive large files
file-organizer rules add archive-large --ext ".zip,.7z" --action archive --dest "~/Archive" --priority 5

# Organize images by type
file-organizer rules add sort-images --ext ".jpg,.png,.gif" --action move --dest "~/Pictures/{ext}"
```

### Preview Rules

```bash
# See what would happen without moving anything
file-organizer rules preview ~/Downloads

# Non-recursive scan
file-organizer rules preview ~/Downloads --no-recursive
```

### Manage Rules

```bash
file-organizer rules list           # List all rules
file-organizer rules sets           # List rule sets
file-organizer rules toggle pdf-to-docs  # Enable/disable
file-organizer rules remove pdf-to-docs  # Delete
file-organizer rules export --output rules.yaml  # Export
file-organizer rules import rules.yaml           # Import
```

## Configuration

### Profiles

```bash
# View current config
file-organizer config show

# Edit settings
file-organizer config edit --text-model "qwen2.5:3b-instruct-q4_K_M"
file-organizer config edit --temperature 0.7
file-organizer config edit --device mps  # Apple Silicon GPU

# Named profiles
file-organizer config edit --profile work --methodology para
file-organizer config show --profile work
file-organizer config list
```

### AI Models

```bash
file-organizer model list              # List available models
file-organizer model pull model:tag    # Download a model
file-organizer model cache             # Show cache stats
```

## Undo/Redo

Every file operation is tracked and reversible:

```bash
file-organizer undo                    # Undo last operation
file-organizer redo                    # Redo last undo
file-organizer history                 # View recent operations
file-organizer history --limit 20      # More history
file-organizer history --stats         # Statistics
```

## Auto-Update

```bash
file-organizer update check            # Check for updates
file-organizer update install          # Download and install
file-organizer update install --dry-run  # Preview update
file-organizer update rollback         # Revert to previous version
```

## Supported File Types

**Documents**: txt, md, pdf, docx, csv, xlsx, ppt, pptx, epub
**Images**: jpg, png, gif, bmp, tiff
**Video**: mp4, avi, mkv, mov, wmv
**Audio**: mp3, wav, flac, m4a, ogg
**Archives**: zip, 7z, tar, rar
**Scientific**: hdf5, netcdf, mat
**CAD**: dxf, dwg, step, iges

**Total**: 43 file types supported.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.
