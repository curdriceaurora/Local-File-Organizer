---
created: 2026-03-08T23:57:34Z
last_updated: 2026-03-09T07:37:36Z
version: 1.1
author: Claude Code PM System
---

# Project Overview

## Summary

File Organizer v2.0 is a production-grade, privacy-first AI file management system. It uses local LLMs (Ollama) and local audio models (faster-whisper) to intelligently organize files by analyzing their content — no internet connection or API keys required.

**Scale**: ~78,800 LOC · 314 modules · 237 test files · ~10,851 tests

## Feature Set

### ✅ Implemented (All 6 Phases Complete)

| Phase | Features |
|-------|----------|
| 1 | Text + Image processing, basic CLI |
| 2 | TUI with Textual, rich terminal UI |
| 3 | Audio, PARA methodology, Johnny Decimal, CAD, Archives, Scientific formats |
| 4 | Deduplication, Preferences, Undo/Redo, Analytics |
| 5 | Event system, Daemon, Docker, CI/CD, Parallel processing |
| 6 | Web Interface (FastAPI), Web UI, Plugin Marketplace |

### File Format Support (48+ types)

| Category | Formats |
|----------|---------|
| Documents | .txt, .md, .pdf, .docx, .pptx, .xlsx, .csv, .json, .xml, .html, .rtf |
| Images | .jpg, .jpeg, .png, .gif, .bmp, .tiff, .webp |
| Video | .mp4, .mov, .avi, .mkv, .webm |
| Audio | .mp3, .wav, .flac, .aac, .ogg |
| Archives | .zip, .7z, .tar, .gz, .rar, .bz2, .xz |
| Scientific | .hdf5, .nc, .mat, .npy, .fits, .csv (scientific), .parquet |
| CAD | .dxf, .dwg, .step, .iges, .stl, .obj |

### Interfaces

- **CLI** (`file-organizer` / `fo`): Full-featured command-line tool
- **TUI**: Textual-based full-screen interface
- **Web UI**: FastAPI + real-time WebSocket/SSE
- **REST API**: Programmatic access

## Current State

- All phases implemented and tested
- CI gate: 95% coverage on main branch pushes
- **New**: OpenAI-compatible provider tier in progress (epic/openai-provider, Issue #335)
- **Completed**: Issue #611 deferred tests — all PRs #668, #669, #670 merged
- **Completed**: Ollama graceful degradation (#677) — verifiable offline detection

## Integration Points

- **Ollama**: Local LLM inference (must be running locally)
- **faster-whisper**: Local audio transcription (optional install)
- **PIL/Pillow**: Image processing and validation
- **PyMuPDF**: PDF content extraction
- **Textual**: TUI framework
- **FastAPI**: Web API and UI

## Quick Start

```bash
pip install -e .
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
file-organizer --help
fo organize --input ~/Downloads --dry-run
```
