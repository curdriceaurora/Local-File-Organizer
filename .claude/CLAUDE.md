# Claude Code Project Instructions

## Project: File Organizer v2.0

This is an AI-powered local file management system with privacy-first architecture.

## Project Structure

```
Local-File-Organizer/
├── .claude/              # CCPM project management
│   ├── commands/         # PM commands
│   ├── prds/             # Product requirements
│   ├── epics/            # Epic planning workspace
│   ├── context/          # Project-wide context
│   └── agents/           # Specialized agent definitions
├── file_organizer_v2/    # Main application
│   ├── src/file_organizer/
│   │   ├── models/       # AI model abstractions
│   │   ├── services/     # Business logic
│   │   ├── core/         # Orchestration
│   │   └── utils/        # Utilities
│   ├── scripts/          # Test and utility scripts
│   ├── demo.py           # CLI demo
│   └── pyproject.toml    # Project configuration
└── file_organizer_v2/BUSINESS_REQUIREMENTS_DOCUMENT.md