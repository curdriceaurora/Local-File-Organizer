---
created: 2026-03-08T23:57:34Z
last_updated: 2026-03-08T23:57:34Z
version: 1.0
author: Claude Code PM System
---

# Product Context

## Target Users

### Primary: Privacy-Conscious Power Users
- Knowledge workers with large, disorganized file collections
- Developers, researchers, creators
- Users who refuse cloud solutions (GDPR concerns, data sovereignty, offline work)
- Technically comfortable with CLI but appreciate a TUI/Web UI option

### Secondary: IT Professionals & Sysadmins
- Managing shared file servers
- Batch-processing organizational cleanup
- Running as a daemon for continuous organization

## Core User Problems

1. **"I can't find anything"** — Downloads folder with 10,000 files, no structure
2. **"I don't trust cloud"** — Google Drive, Dropbox, or OneDrive not acceptable
3. **"Naming files is tedious"** — AI should generate meaningful names from content
4. **"I have duplicates everywhere"** — Same files in 5 places after years of backups

## Core Features

### File Organization
- AI-generated folder names and filenames from content analysis
- Support for 48+ file types: documents, images, video, audio, archives, scientific, CAD
- Multiple organization methodologies: PARA, Johnny Decimal, custom rules
- Dry-run preview before any changes

### AI Processing
- Text: content summarization, topic extraction → smart naming
- Images: visual description, OCR, scene understanding
- Audio: transcription (faster-whisper), topic detection, speaker estimation
- Video: metadata extraction, scene detection, duration-based routing

### Safety & Control
- Undo/redo system for all file operations
- Complete operation history with rollback
- Trash-based deletion (recoverable)
- Dry-run mode for all operations

### Interfaces
- **CLI**: `file-organizer organize`, `fo dedupe`, `fo profile`, etc.
- **TUI**: Full-screen Textual interface with file browser, analytics, audio view
- **Web UI**: FastAPI + WebSocket for real-time status, SSE progress streams
- **API**: REST API for integration with other tools

### Advanced
- Plugin marketplace (hot-loadable plugins)
- Deduplication (perceptual hashing for images, semantic for documents)
- Analytics dashboard (processing history, file type breakdown)
- Daemon mode (watch folder, auto-organize)
- Docker deployment

## Key Use Cases

1. **Organize Downloads**: Point at ~/Downloads, AI creates structured folders by content type and topic
2. **Photo Library**: Organize by date/event/subject using vision AI
3. **Research Archive**: PARA methodology for projects/areas/resources/archive
4. **Podcast Archive**: Audio transcription → episode-based naming/routing
5. **Dedup Library**: Find and remove duplicate images/documents

## Non-Goals

- No cloud sync or remote storage
- No collaborative editing
- No mobile apps
- No document editing (read + organize only)
