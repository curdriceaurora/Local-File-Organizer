---
created: 2026-03-08T23:57:34Z
last_updated: 2026-03-08T23:57:34Z
version: 1.0
author: Claude Code PM System
---

# Project Brief

## What It Is

File Organizer v2.0 is a privacy-first, AI-powered local file management system. It intelligently organizes files using local LLMs with zero cloud dependencies — all processing happens on-device.

## Why It Exists

Users accumulate thousands of unorganized files across downloads, photos, documents, and media. Existing cloud-based solutions compromise privacy. File Organizer solves this with:
- **100% local processing** — no data leaves the machine
- **AI-driven metadata** — LLMs generate meaningful folder names, filenames, descriptions
- **Multi-modal support** — handles text, images, audio, video, CAD, archives, scientific formats

## Core Goals

1. Organize files intelligently using local AI (Ollama + faster-whisper)
2. Zero cloud dependencies — full offline operation
3. Support 48+ file types across 7 categories
4. Multiple organization methodologies (PARA, Johnny Decimal, custom)
5. Provide CLI, TUI (Textual), and Web UI (FastAPI) interfaces

## Success Criteria

- Files organized with AI-generated meaningful names and folder structures
- Works fully offline with no API keys required
- < 10s processing for text/image files
- 95% test coverage (enforced via CI gate)
- Cross-platform: macOS, Linux, Windows

## Scope

**In scope**: Local file organization, AI metadata generation, deduplication, undo/redo, analytics, plugin marketplace, daemon mode, Docker deployment

**Out of scope**: Cloud sync, mobile apps, multi-user collaboration

## License

MIT OR Apache-2.0 (dual-licensed)
