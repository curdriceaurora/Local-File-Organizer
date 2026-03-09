---
created: 2026-03-08T23:57:34Z
last_updated: 2026-03-08T23:57:34Z
version: 1.0
author: Claude Code PM System
---

# Project Structure

## Root Layout

```
Local-File-Organizer/
├── src/file_organizer/     # Main package (~78,800 LOC, 314 modules)
├── tests/                  # Test suite (237 test files, ~10,851 tests)
├── docs/                   # Documentation (architecture, setup, testing, reference)
├── scripts/                # Build and utility scripts
├── .claude/                # CCPM project management system
│   ├── agents/             # Agent definitions (code-reviewer, test-runner, etc.)
│   ├── commands/           # Skill definitions (pm:*, context:*, testing:*, pr*)
│   ├── context/            # Project context files (this directory)
│   ├── epics/              # CCPM epic tracking
│   ├── rules/              # Project rules (31 rule files)
│   └── scripts/            # Automation scripts (pre-commit-validation.sh, etc.)
├── pyproject.toml          # Package config, dependencies, tool settings
├── .pre-commit-config.yaml # Pre-commit hook config
├── CLAUDE.md               # Main project instructions for Claude
└── README.md               # Public project documentation
```

## Source Package (`src/file_organizer/`)

```
file_organizer/
├── api/            # FastAPI route definitions (REST endpoints)
├── cli/            # Typer CLI commands (organize, dedupe, profile, etc.)
├── client/         # HTTP client for API interaction
├── config/         # ConfigManager — paths, settings, user preferences
├── core/           # Core organizer logic, file processing pipeline
├── daemon/         # Background daemon mode
├── deploy/         # Docker/deployment configuration
├── events/         # Event bus (publish/subscribe for loose coupling)
├── history/        # Operation history for undo/redo
├── integrations/   # Third-party integrations
├── interfaces/     # Abstract interfaces/protocols
├── methodologies/  # Organization strategies (PARA, Johnny Decimal, custom)
├── models/         # AI model wrappers
│   ├── audio_transcriber.py  # faster-whisper wrapper
│   ├── vision_model.py       # Ollama vision model wrapper
│   ├── text_model.py         # Ollama text model wrapper
│   └── model_manager.py      # Model lifecycle management
├── optimization/   # Performance optimization utilities
├── parallel/       # Parallel processing support
├── pipeline/       # File processing pipeline stages
├── plugins/        # Plugin system + marketplace
├── services/       # Business logic services
│   ├── audio/      # Audio classification, transcription, organization
│   ├── deduplication/ # Image/document dedup (perceptual hashing, embeddings)
│   ├── video/      # Video metadata, scene detection, organization
│   └── vision_processor.py  # Image/video AI processing
├── tui/            # Textual TUI views (file browser, analytics, audio, etc.)
├── undo/           # Undo/redo system (rollback, validation)
├── updater/        # Auto-update system
├── utils/          # Utility functions
│   └── readers/    # File format readers (documents, ebook, archives, scientific, CAD)
├── watcher/        # File system watcher (daemon mode)
└── web/            # FastAPI app (routes, helpers, WebSocket)
```

## Test Structure (`tests/`)

Mirrors source package structure with additions:
```
tests/
├── services/
│   ├── audio/      # 9 test files — audio service tests (281 tests)
│   ├── video/      # 3 test files — video service tests (96 tests)
│   ├── deduplication/ # 15+ test files — dedup tests
│   └── test_vision_processor.py
├── models/         # Model tests (audio_transcriber, vision_model, etc.)
├── utils/          # File reader tests
├── ci/             # CI guardrail tests
├── conftest.py     # Shared fixtures (mock_text_model, mock_ollama, etc.)
└── [root-level]    # API, CLI, web, TUI integration tests
```

## Key Conventions

- **Test naming**: `test_{module_name}.py` or `test_{feature}.py`
- **Test markers**: `@pytest.mark.unit`, `@pytest.mark.ci`, `@pytest.mark.smoke`, `@pytest.mark.integration`
- **Source naming**: `snake_case.py` for modules, `PascalCase` for classes
- **Branch naming**: `feature/issue-{N}-{description}` or `fix/issue-{N}-{description}`
- **Import style**: Absolute imports only (`from file_organizer.services.video...`)
