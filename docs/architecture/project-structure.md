# Project Structure

```text
Local-File-Organizer/
├── .claude/                          # CCPM project management
│   ├── commands/                     # PM commands
│   ├── prds/                         # Product requirements
│   ├── epics/                        # Epic planning workspace
│   ├── rules/                        # Standard operation rules
│   └── scripts/                      # Validation scripts
│
├── src/file_organizer/               # Main application (~78,800 LOC, 314 modules)
│   ├── models/                       # AI model abstractions (9 modules)
│   │   ├── base.py                   # BaseModel interface, ModelConfig
│   │   ├── text_model.py             # Ollama text generation
│   │   ├── vision_model.py           # Vision-language models
│   │   ├── audio_model.py            # Audio transcription
│   │   ├── audio_transcriber.py      # Comprehensive audio transcription
│   │   ├── model_manager.py          # Unified model lifecycle management
│   │   ├── registry.py               # Model registry
│   │   ├── suggestion_types.py       # Type definitions
│   │   └── analytics.py              # Model analytics
│   │
│   ├── services/                     # Business logic layer
│   │   ├── analytics/                # Storage & metrics analysis
│   │   ├── audio/                    # Audio file processing
│   │   ├── auto_tagging/             # Tag recommendation & learning
│   │   ├── copilot/                  # AI copilot features
│   │   ├── deduplication/            # Image & document deduplication
│   │   │   ├── image_dedup/          # Perceptual hashing
│   │   │   ├── document_dedup/       # Embedding-based dedup
│   │   │   ├── backup_manager.py
│   │   │   └── quality_assessor.py
│   │   ├── intelligence/             # User preference learning (23 modules)
│   │   ├── video/                    # Video processing
│   │   ├── text_processor.py         # Text file pipeline
│   │   ├── vision_processor.py       # Image/video pipeline
│   │   ├── pattern_analyzer.py       # Pattern detection
│   │   ├── smart_suggestions.py      # Placement suggestions
│   │   ├── misplacement_detector.py  # Context analysis
│   │   └── suggestion_feedback.py    # Feedback tracking
│   │
│   ├── core/                         # Main orchestrator (Phase A modernization)
│   │   ├── __init__.py
│   │   ├── organizer.py              # FileOrganizer thin facade (~390 lines)
│   │   ├── types.py                  # Core type definitions
│   │   ├── display.py                # Output/display helpers
│   │   ├── file_ops.py               # File operation primitives
│   │   ├── dispatcher.py             # Request dispatching
│   │   ├── initializer.py            # Service initialization
│   │   └── hardware_profile.py       # Hardware capability detection
│   │
│   ├── cli/                          # Command-line interfaces (18 modules)
│   │   ├── main.py                   # CLI entrypoint
│   │   ├── dedupe.py                 # Deduplication commands
│   │   ├── dedupe_v2.py              # Deduplication v2
│   │   ├── profile.py                # Profile management
│   │   ├── undo_redo.py              # Undo/redo commands
│   │   ├── autotag.py                # Auto-tagging commands
│   │   ├── analytics.py              # Analytics commands
│   │   ├── daemon.py                 # Daemon control commands
│   │   ├── marketplace.py            # Plugin marketplace
│   │   ├── copilot.py                # AI copilot commands
│   │   ├── interactive.py            # Interactive mode
│   │   ├── suggest.py                # Suggestion commands
│   │   ├── rules.py                  # Rules management
│   │   ├── update.py                 # Self-update commands
│   │   ├── api.py                    # API server commands
│   │   └── completion.py             # Shell completion
│   │
│   ├── api/                          # FastAPI REST server
│   ├── web/                          # Web UI (templates, routes, static)
│   ├── desktop/                      # pywebview launcher (app.py — single-process desktop)
│   ├── tui/                          # Textual TUI
│   ├── daemon/                       # Background daemon & file watcher
│   ├── events/                       # Event bus system
│   ├── parallel/                     # Parallel processing framework
│   ├── pipeline/                     # Processing pipeline orchestration
│   ├── methodologies/                # PARA, Johnny Decimal, etc.
│   ├── plugins/                      # Plugin system & marketplace
│   ├── integrations/                 # Third-party service integrations
│   ├── interfaces/                   # Protocol definitions (Phase A modernization)
│   │   ├── __init__.py
│   │   ├── model.py                  # TextModelProtocol, VisionModelProtocol, AudioModelProtocol
│   │   ├── processor.py              # FileProcessorProtocol, BatchProcessorProtocol
│   │   ├── storage.py                # StorageProtocol, CacheProtocol
│   │   └── intelligence.py           # LearnerProtocol, ScorerProtocol
│   ├── optimization/                 # Performance optimization
│   ├── deploy/                       # Deployment automation
│   ├── watcher/                      # File system watching
│   ├── client/                       # Client library
│   ├── updater/                      # Self-update system
│   ├── history/                      # Operation history (6 modules)
│   ├── undo/                         # Undo/redo system (5 modules)
│   ├── utils/                        # Utilities
│   │   ├── file_readers.py           # 40+ file format readers
│   │   ├── text_processing.py        # Text utilities
│   │   └── chart_generator.py        # Visual analytics
│   └── config/                       # Configuration management
│
├── tests/                            # 237 test files
│   ├── api/                          # API tests
│   ├── ci/                           # CI pipeline tests
│   ├── core/                         # Core tests (test_organizer.py, test_hardware_profile.py)
│   ├── daemon/                       # Daemon tests
│   ├── deploy/                       # Deployment tests
│   ├── docs/                         # Documentation tests
│   ├── events/                       # Event bus tests
│   ├── history/                      # History system tests
│   ├── integration/                  # Integration tests
│   ├── interfaces/                   # Protocol conformance tests (test_protocol_conformance.py, 12 tests)
│   ├── methodologies/                # Methodology tests
│   ├── models/                       # Model tests
│   ├── optimization/                 # Optimization tests
│   ├── parallel/                     # Parallel processing tests
│   ├── pipeline/                     # Pipeline tests
│   ├── plugins/                      # Plugin tests
│   ├── services/                     # Service layer tests
│   │   ├── analytics/
│   │   ├── auto_tagging/
│   │   ├── deduplication/
│   │   └── intelligence/
│   └── undo/                         # Undo/redo tests
│
├── scripts/                          # Build & utility scripts
│   ├── build_windows.ps1
│   ├── build_windows.iss
│   ├── build_macos.sh
│   └── build_linux.sh
│
├── .github/                          # GitHub Actions workflows & templates
├── alembic/                          # Database migrations
├── deploy/                           # Deployment automation
├── desktop/                          # Desktop app assets (icons, build/, context-menus/)
├── docs/                             # Project documentation
├── examples/                         # Usage examples
├── packaging/                        # Installer packaging
├── plugins/                          # Plugin marketplace
├── project-docs/                     # Extended project documentation
├── technical-debt/                   # Tracked technical debt
├── demo.py                           # CLI demo
└── pyproject.toml                    # Project configuration
```

---
