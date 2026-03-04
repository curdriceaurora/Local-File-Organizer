# Claude Code Project Instructions

## Project: File Organizer v2.0

An AI-powered local file management system with privacy-first architecture. Organizes files intelligently using local LLMs with zero cloud dependencies.

**Core Metrics**: ~78,800 LOC | 314 modules | 237 tests | Python 3.11+
**Version**: 2.0.0-alpha.1

---

## Table of Contents

1. [Claude Agent Permissions](#claude-agent-permissions)
2. [External References](#external-references)
3. [Pre-Commit Checklist](#pre-commit-checklist)
4. [Quick Start](#quick-start)
5. [Project Structure](#project-structure)
6. [Architecture Overview](#architecture-overview)
7. [Dependencies & Setup](#dependencies--setup)
8. [AI Model Configuration](#ai-model-configuration)
9. [Development Guidelines](#development-guidelines)
10. [Testing Strategy](#testing-strategy)
11. [Common Workflows](#common-workflows)
12. [Supported File Types](#supported-file-types)
13. [Performance Notes](#performance-notes)

---
## External References

This document contains critical enforcement rules and operational guidelines. Detailed reference documentation is organized in the following structure:

### Architecture & Design
- **[Project Structure](../docs/architecture/project-structure.md)** - Complete directory tree, module organization (314 modules)
- **[Architecture Overview](../docs/architecture/architecture-overview.md)** - Design principles, core components, data flow

### Setup & Configuration
- **[Dependencies & Setup](../docs/setup/dependencies.md)** - Installation, system requirements, optional dependencies
- **[AI Model Configuration](../docs/setup/models.md)** - Supported models, device support, model selection

### Testing & Quality
- **[Testing Strategy](../docs/testing/testing-strategy.md)** - Test organization, markers, coverage goals, running tests
- **[Code Quality Validation](../docs/setup/code-quality.md)** - Pre-commit validation, pattern checks, automated scripts

### Reference
- **[Supported File Types](../docs/reference/file-formats.md)** - Complete file format support matrix (48+ types)
- **[Performance Metrics](../docs/reference/performance.md)** - Processing times by file type, memory usage by component

---

## Claude Agent Permissions

**IMPORTANT**: Claude agents working on this project have the following permissions and responsibilities:

### 🚀 Auto-Approved Operations

**For all paths under the project workspace (`~/Projects/` or equivalent):**
- ✅ All file operations (read, write, edit, delete) are auto-approved
- ✅ All bash commands are auto-approved
- ✅ All git operations are auto-approved
- ✅ All test executions are auto-approved
- ✅ No need to ask for user permission - proceed directly

### ✅ Permitted Actions

**Code Development**:
- Create, modify, and delete code files in `src/file_organizer/`
- Write and update tests in `tests/`
- Create utility scripts in `scripts/`
- Modify configuration files (`pyproject.toml`, etc.)

**Git Operations**:
- Create feature branches following pattern: `feature/task-XX-description`
- Create worktrees for parallel work
- Commit, push, and create pull requests

**CCPM Framework Maintenance** (REQUIRED):
- Create and update daily logs in `.claude/epics/sprint-*/daily-logs/`
- Update execution status files in `.claude/epics/*/execution-status.md`
- Follow all rules in `.claude/rules/` directory

### ⚠️ Required Protocols

**Before GitHub Write Operations** (CRITICAL):
```bash
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$remote_url" == *"automazeio/ccpm"* ]]; then
  echo "❌ ERROR: Cannot modify CCPM template repository!"
  exit 1
fi
```

**DateTime Standards** (ALWAYS):
```bash
CURRENT_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

**Code Quality Validation** (CRITICAL - ALWAYS):
```bash
bash .claude/scripts/pre-commit-validation.sh
```

### 🚫 Prohibited Actions

- ❌ Force pushing to `main`/protected branches
- ❌ Committing secrets, API keys, or credentials
- ❌ Pushing directly to `main` (use PRs)
- ❌ Using placeholder dates in frontmatter
- ❌ Using `--no-verify` or skipping hooks

### 📚 Reference Documentation

- `.claude/rules/code-quality-validation.md` — Validation patterns (MUST READ before commit)
- `.claude/rules/quick-validation-checklist.md` — Quick reference
- `.claude/scripts/pre-commit-validation.sh` — Automated validation script
- `.claude/rules/github-operations.md` — GitHub integration rules
- `.claude/rules/datetime.md` — Timestamp requirements

---

## Pre-Commit Checklist

**MANDATORY**: Before EVERY commit, complete these steps in order:

### Step 1: Code Quality Validation
```bash
ruff check .
```
- If violations found, run: `ruff check . --fix`
- Verify all violations are resolved before proceeding

### Step 2: Code Formatting
```bash
ruff format . --check
```
- If formatting issues found, run: `ruff format .` to auto-fix
- Verify formatting passes check before proceeding

### Step 3: Run Test Suite
```bash
pytest tests/ -x -q
```
- Ensure all tests pass
- If tests fail, fix the failures before committing
- Do NOT commit with failing tests

### Step 4: Review Your Diff
Before running `git commit`:
```bash
git diff --cached
```
- Verify no duplicate imports
- Verify no misplaced lines (e.g., pytestmark in wrong location)
- Verify changes match intended modifications
- Watch for E402/I001 errors that ruff might have missed

### Step 5: Commit Only If All Pass
```bash
git commit -m "message"
```

**NEVER commit if ruff check, ruff format, or tests fail.**

### Git Pre-Commit Hook
A git hook is configured at `.git/hooks/pre-commit` that automatically runs `ruff check` and `ruff format --check` before allowing commits. If the hook fails:
- Fix the violations: `ruff check . --fix && ruff format .`
- Stage fixed files: `git add <files>`
- Try commit again

**This hook prevents accidental commits with lint violations.**

---

## Quick Start

```bash
# Install dependencies
pip install -e .

# Install Ollama and pull models
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M

# Run demo
python3 demo.py --sample --dry-run

# Run CLI
file-organizer --help
fo --help  # Short alias
```

---

## ⚠️ CRITICAL: PM Skills Are Mandatory

**NEVER manually create or update GitHub issues/PRs or CCPM tracking documents.**
**ALWAYS use PM skills for ALL project management operations.**

See: `.claude/rules/pm-skills-mandatory.md` for complete requirements.

---

## Project Structure

See **[Project Structure Reference](../docs/architecture/project-structure.md)** for the complete directory tree.

**Quick Summary:**
- `src/file_organizer/` — Main application (78,800 LOC, 314 modules)
- `tests/` — Test suite (237 tests)
- `.claude/` — CCPM project management
- `docs/` — Documentation
- `scripts/` — Build and utility scripts

---

## Architecture Overview

### Design Principles

1. **Privacy-First**: 100% local processing, zero cloud dependencies
2. **Model Abstraction**: Abstract AI model interface for framework flexibility
3. **Service Layer Pattern**: Business logic separate from models
4. **Strategy Pattern**: Different processors for different file types
5. **Event-Driven**: Event bus for loosely-coupled inter-component communication
6. **Plugin Architecture**: Extensible via plugin marketplace
7. **Type Safety**: Full type hints with strict mypy configuration
8. **Resource Management**: Context managers for automatic cleanup

### Core Components

| Component | Purpose | Location | Status |
|-----------|---------|----------|--------|
| **BaseModel** | Abstract AI model interface | `models/base.py` | ✅ Core |
| **ModelManager** | Unified model lifecycle | `models/model_manager.py` | ✅ Active |
| **TextModel** | Ollama text generation | `models/text_model.py` | ✅ Active |
| **VisionModel** | Vision-language wrapper | `models/vision_model.py` | ✅ Active |
| **AudioModel** | Audio transcription | `models/audio_model.py` | ✅ Active |
| **TextProcessor** | Text file pipeline | `services/text_processor.py` | ✅ Active |
| **VisionProcessor** | Image/video pipeline | `services/vision_processor.py` | ✅ Active |
| **FileOrganizer** | Main orchestrator | `core/file_organizer.py` | ✅ Active |
| **PatternAnalyzer** | Naming pattern detection | `services/pattern_analyzer.py` | ✅ Active |
| **SmartSuggestions** | Placement suggestions | `services/smart_suggestions.py` | ✅ Active |
| **Intelligence** | User preference learning | `services/intelligence/` | ✅ Active |
| **Deduplication** | Duplicate detection | `services/deduplication/` | ✅ Active |
| **OperationHistory** | Operation tracking | `history/` | ✅ Active |
| **UndoManager** | Undo/redo system | `undo/` | ✅ Active |
| **EventBus** | Inter-component events | `events/` | ✅ Active |
| **Daemon** | Background file watching | `daemon/` | ✅ Active |
| **API Server** | FastAPI REST endpoints | `api/` | ✅ Active |
| **Web UI** | Browser-based interface | `web/` | ✅ Active |
| **TUI** | Textual terminal UI | `tui/` | ✅ Active |
| **PluginSystem** | Extension marketplace | `plugins/` | ✅ Active |
| **Methodologies** | PARA, Johnny Decimal | `methodologies/` | ✅ Active |

### Data Flow

```
Input File → FileOrganizer → File Type Detection
    ↓
Text Files: TextProcessor → TextModel (Qwen 2.5 3B)
Image/Video: VisionProcessor → VisionModel (Qwen 2.5-VL 7B)
Audio: AudioModel/AudioTranscriber → faster-whisper

All Processors → PatternAnalyzer → SmartSuggestions
    ↓
Intelligence Services → User Preference Learning
EventBus → Daemon / Web UI / TUI notifications

Final Output: Organized files + Operation history
```

---

## Dependencies & Setup

### System Requirements

- **Python**: 3.9+
- **Ollama**: Latest version for local inference
- **Storage**: ~10 GB for models
- **RAM**: 8 GB minimum, 16 GB recommended

### Installation

```bash
# 1. Clone repository
git clone <repo-url>
cd Local-File-Organizer

# 2. Install Ollama and pull models
ollama pull qwen2.5:3b-instruct-q4_K_M    # Text: ~1.9 GB
ollama pull qwen2.5vl:7b-q4_K_M           # Vision: ~6.0 GB

# 3. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install package
pip install -e .

# 5. Verify
file-organizer --version
fo --version
```

### Optional Dependencies

```bash
pip install -e ".[audio]"       # Audio transcription (faster-whisper, torch)
pip install -e ".[video]"       # Video processing (opencv, scenedetect)
pip install -e ".[dedup]"       # Image deduplication (imagededup)
pip install -e ".[archive]"     # Archive support (7z, RAR)
pip install -e ".[scientific]"  # Scientific formats (HDF5, NetCDF, MATLAB)
pip install -e ".[cad]"         # CAD formats (ezdxf)
pip install -e ".[build]"       # Executable packaging (PyInstaller)
pip install -e ".[all]"         # Everything
```

### CLI Entrypoints

```toml
# pyproject.toml
[project.scripts]
file-organizer = "file_organizer.cli:main"
fo = "file_organizer.cli:main"
```

---

## AI Model Configuration

### Supported Models

- `qwen2.5:3b-instruct-q4_K_M` — Default text model (~1.9 GB)
- `qwen2.5vl:7b-q4_K_M` — Default vision model (~6.0 GB)
- `faster-whisper` — Audio transcription (local, multi-language)

### Device Support

```python
from file_organizer.models.base import DeviceType

DeviceType.AUTO    # Automatic detection (recommended)
DeviceType.CPU     # CPU inference (universal)
DeviceType.CUDA    # NVIDIA GPU (fastest)
DeviceType.MPS     # Apple Silicon (fast)
DeviceType.METAL   # Apple Metal (fast)
```

---

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity
### 2. Subagent Strategy to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution
### 3. Self-Improvement Loop
- After ANY correction from the user: update 'tasks/lessons. md' with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project
### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness
### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know
now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it
### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how
## Task Management
1. **Plan First**: Write plan to 'tasks/todo.md' with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review to 'tasks/todo.md'
6. **Capture Lessons**: Update 'tasks/lessons.md' after corrections
## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior deveoper standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## Development Guidelines

### Code Style

- **Black** for formatting (line length: 100)
- **isort** for import sorting
- **Ruff** for linting (strict)
- **mypy** strict mode for type checking

### Naming Conventions

- Files/modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_single_underscore`

### Git Commit Messages

```
<type>(<scope>): <subject>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Pre-Commit Validation (REQUIRED)

```bash
bash .claude/scripts/pre-commit-validation.sh
```

Key patterns to avoid:
1. Dict-style dataclass access → use `hasattr()`
2. Wrong return types → read implementation first
3. Non-existent imports → verify module exists
4. Wrong constructor params → check class definition
5. Build artifacts → add to `.gitignore`

---

## Testing Strategy

### Running Tests

```bash
pytest                                          # All tests
pytest --cov=file_organizer --cov-report=html  # With coverage
pytest tests/services/ -v                       # Specific directory
pytest -m "not regression" -x                  # Skip regression, stop on first fail
pytest -k "backup or dedup"                     # Filter by name
```

### Test Markers

```python
@pytest.mark.unit          # Unit tests
@pytest.mark.integration   # Integration tests
@pytest.mark.ci            # CI-specific tests
@pytest.mark.slow          # Slow tests
@pytest.mark.regression    # Regression tests
```

### Coverage Goals

- Unit tests: 80%+ coverage
- Integration tests: Key workflows
- CI tests: Pipeline and build validation

---

## Supported File Types

| Category | Formats | Count |
|----------|---------|-------|
| Documents | `.txt`, `.md`, `.pdf`, `.docx`, `.doc`, `.csv`, `.xlsx`, `.xls`, `.ppt`, `.pptx`, `.epub` | 11 |
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.tif` | 7 |
| Video | `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv` | 5 |
| Audio | `.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg` | 5 |
| Archives | `.zip`, `.7z`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.rar` | 7 |
| Scientific | `.hdf5`, `.h5`, `.hdf`, `.nc`, `.nc4`, `.netcdf`, `.mat` | 7 |
| CAD | `.dxf`, `.dwg`, `.step`, `.stp`, `.iges`, `.igs` | 6 |

**Total**: 48+ file types supported

---

## Performance Notes

| File Type | Average Time | Model |
|-----------|-------------|-------|
| Text (< 1 MB) | 2–5 s | Qwen 2.5 3B |
| Image | 3–8 s | Qwen 2.5-VL 7B |
| Video | 5–20 s | Qwen 2.5-VL 7B |
| Audio | 2–10 s | faster-whisper |
| PDF (text) | 3–10 s | Qwen 2.5 3B |

### Memory Usage

| Component | RAM |
|-----------|-----|
| Qwen 2.5 3B (Q4) | ~2.5 GB |
| Qwen 2.5-VL 7B (Q4) | ~5.5 GB |
| Base application | ~200 MB |

---

## Phase Roadmap

- ✅ **Phase 1**: Text + Image processing
- ✅ **Phase 2**: TUI with Textual
- ✅ **Phase 3**: Feature Expansion (Audio, PARA, Johnny Decimal, CAD, Archives, Scientific)
- ✅ **Phase 4**: Intelligence & Learning (Dedup, Preferences, Undo/Redo, Analytics)
- ✅ **Phase 5**: Architecture & Performance (Events, Daemon, Docker, CI/CD, Parallel)
- ✅ **Phase 6**: Web Interface (FastAPI, Web UI, Plugin Marketplace)

---

**Last Updated**: 2026-02-18
**Version**: 2.0.0-alpha.1
