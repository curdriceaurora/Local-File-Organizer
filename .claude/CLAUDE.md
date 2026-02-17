# Claude Code Project Instructions

## Project: File Organizer v2.0

An AI-powered local file management system with privacy-first architecture. Organizes files intelligently using local LLMs with zero cloud dependencies.

**Core Metrics**: ~54,000 LOC | 184 modules | 136 tests | Python 3.9+

---

## Table of Contents

1. [Claude Agent Permissions](#claude-agent-permissions)
2. [Quick Start](#quick-start)
3. [Project Structure](#project-structure)
4. [Architecture Overview](#architecture-overview)
5. [Dependencies & Setup](#dependencies--setup)
6. [AI Model Configuration](#ai-model-configuration)
7. [Development Guidelines](#development-guidelines)
8. [Testing Strategy](#testing-strategy)
9. [Common Workflows](#common-workflows)
10. [Supported File Types](#supported-file-types)
11. [Performance Notes](#performance-notes)

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

**This means:**
- Execute commands immediately without confirmation prompts
- Create, modify, delete files as needed for the task
- Run tests, builds, and other operations freely
- Commit and push changes without asking
- The user trusts you to work autonomously in this directory

### ✅ Permitted Actions

**Code Development**:
- Create, modify, and delete code files in `file_organizer_v2/src/`
- Write and update tests in `file_organizer_v2/tests/`
- Create utility scripts in `file_organizer_v2/scripts/`
- Modify configuration files (`pyproject.toml`, etc.)

**Git Operations**:
- Create feature branches following pattern: `feature/task-XX-description`
- Create sprint branches: `sprint/YYYY-qN-weeksN-N`
- Create worktrees for parallel work: `../worktree-name`
- Commit code changes with descriptive messages
- Push to feature/sprint branches
- Create pull requests when features complete

**CCPM Framework Maintenance** (REQUIRED):
- Create and update daily logs in `.claude/epics/sprint-*/daily-logs/`
- Update execution status files in `.claude/epics/*/execution-status.md`
- Create weekly review documents
- Update sprint tracking files
- Maintain GitHub issue synchronization
- Update PRD status as features complete
- Follow all rules in `.claude/rules/` directory

**GitHub Integration**:
- Comment on GitHub issues with progress updates
- Close issues when tasks complete
- Create new issues for discovered technical debt
- Update issue labels and assignees
- Reference issues in commit messages

**Documentation**:
- Update user-facing documentation
- Write/update docstrings (Google style)
- Create usage examples
- Update API documentation
- Maintain CHANGELOG

**Testing**:
- Write unit tests for all new code
- Create integration tests for features
- Run test suite before committing
- Maintain 90%+ coverage target
- Fix failing tests immediately

**CCPM Daily Workflow** (15-20 min/day):
```bash
# Morning: Check yesterday's progress
cat .claude/epics/sprint-*/daily-logs/[yesterday].md

# During work: Track progress
# (implement features, write tests, commit)

# Evening: Update CCPM (REQUIRED)
1. Create daily log with real progress data
2. Update GitHub issues worked on
3. Update execution-status.md if milestones reached
4. Commit CCPM changes with message: "CCPM: Daily update YYYY-MM-DD"
5. Push to current branch
```

### ⚠️ Required Protocols

**Before GitHub Write Operations** (CRITICAL):
```bash
# ALWAYS check remote origin before creating/editing issues or PRs
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$remote_url" == *"automazeio/ccpm"* ]]; then
  echo "❌ ERROR: Cannot modify CCPM template repository!"
  exit 1
fi
```

**DateTime Standards** (ALWAYS):
```bash
# Get REAL current datetime - never use placeholders
CURRENT_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Use in frontmatter
---
updated: 2026-01-23T14:30:45Z  # Real datetime, not placeholder
---
```

**Path Standards** (ALWAYS):
```markdown
# Use relative paths - NEVER absolute paths with usernames
✅ src/file_organizer/models/audio_model.py
✅ file_organizer_v2/src/file_organizer/
❌ /Users/username/Projects/file_organizer_v2/src/...
```

**Frontmatter Standards** (ALWAYS):
```yaml
---
name: descriptive-name
created: 2026-01-23T09:00:00Z  # Set once, never change
updated: 2026-01-23T14:30:00Z  # Update on every modification
status: backlog|in-progress|completed
---
```

**Code Quality Validation** (CRITICAL - ALWAYS):

```bash
# Before EVERY commit, run validation script
bash .claude/scripts/pre-commit-validation.sh

# Aggressively check for patterns that reviewers flag:
# 1. Dict-style dataclass access → Use hasattr()
# 2. Wrong return types → Read implementation first
# 3. Non-existent imports → Verify module exists
# 4. Wrong constructor params → Check class definition
# 5. Build artifacts → Add to .gitignore
# 6. Broken links → Verify files exist
# 7. Untested examples → Test before documenting

# See detailed patterns: .claude/rules/code-quality-validation.md
# Quick reference: .claude/rules/quick-validation-checklist.md
```

**Goal**: AI reviewers should find NOTHING to complain about. Catch all issues BEFORE committing.

### 🚫 Prohibited Actions

**Code**:
- ❌ Modifying `.git/` directory directly
- ❌ Force pushing (`git push --force`) to main/protected branches
- ❌ Committing secrets, API keys, or credentials
- ❌ Modifying user data or configuration files
- ❌ Running destructive operations without confirmation

**Git**:
- ❌ Pushing directly to `main` branch (use PRs)
- ❌ Deleting remote branches without confirmation
- ❌ Amending commits that are already pushed
- ❌ Rebasing shared branches
- ❌ Creating merge commits in feature branches

**GitHub**:
- ❌ Creating issues/PRs on `automazeio/ccpm` template repository
- ❌ Closing issues without completion confirmation
- ❌ Deleting or hiding comments
- ❌ Modifying repository settings
- ❌ Using `--no-verify` or skipping hooks

**CCPM**:
- ❌ Using placeholder dates like `[Current date]` in frontmatter
- ❌ Using absolute paths with usernames in documentation
- ❌ Skipping daily log creation
- ❌ Leaving GitHub issues out of sync
- ❌ Modifying `created` timestamp after initial creation

### 📋 Sprint Execution Checklist

**Daily (Every Day)**:
- [ ] Create daily log with actual progress
- [ ] Update GitHub issues (if worked on them)
- [ ] Update execution-status.md (if milestone reached)
- [ ] Commit CCPM changes
- [ ] Run tests before pushing
- [ ] Use real datetimes in all updates

**Weekly (End of Each Week)**:
- [ ] Create weekly review document
- [ ] Verify all 7 daily logs complete
- [ ] Sync all GitHub issues to current status
- [ ] Update PRD with progress
- [ ] Plan next week's work

**Sprint End (Every 2 Weeks)**:
- [ ] Create sprint retrospective
- [ ] Close all completed GitHub issues
- [ ] Update all epic execution-status files
- [ ] Update master PRD
- [ ] Create sprint summary document
- [ ] Archive sprint artifacts
- [ ] Plan next sprint

### 🎯 Quality Standards

**Code Quality** (Enforced):
- Type hints on all functions (mypy strict mode)
- Docstrings on all public functions (Google style)
- Unit tests for all new code (90%+ coverage)
- Pass all linting (ruff)
- Pass all formatting (black, isort)
- No unused imports or variables

**CCPM Quality** (Enforced):
- Daily logs must contain real data, not estimates
- All timestamps must be from system (not hardcoded)
- All paths must be relative (not absolute)
- GitHub must be 100% synced at week end
- All frontmatter must be valid YAML
- All rules in `.claude/rules/` must be followed

### 📚 Reference Documentation

**CRITICAL - Read Before Every Commit**:
- `.claude/rules/code-quality-validation.md` - Comprehensive validation patterns (MUST READ)
- `.claude/rules/quick-validation-checklist.md` - Quick reference before commits
- `.claude/scripts/pre-commit-validation.sh` - Automated validation script

**Must Read Before Starting**:
- `.claude/rules/worktree-operations.md` - Git worktree workflow
- `.claude/rules/github-operations.md` - GitHub integration rules
- `.claude/rules/frontmatter-operations.md` - Metadata standards
- `.claude/rules/datetime.md` - Timestamp requirements
- `.claude/rules/path-standards.md` - Path formatting rules
- `.claude/rules/standard-patterns.md` - Common patterns
- `.claude/SPRINT_CCPM_INTEGRATION.md` - CCPM maintenance guide

**Sprint Planning**:
- `.claude/SPRINT_PLAN_2026_Q1.md` - Detailed 4-week plan
- `.claude/SPRINT_SUMMARY.md` - Quick reference
- `.claude/SPRINT_VISUAL_ROADMAP.md` - Visual timeline

**Always Follow**:
1. **Validate before EVERY commit** - Run `.claude/scripts/pre-commit-validation.sh`
2. **Read implementation BEFORE documenting** - Verify APIs match actual code
3. Check rules before performing operations
4. Use templates for consistency
5. Update CCPM daily, not weekly
6. Sync GitHub continuously
7. Test before pushing
8. Document as you code

---

## Quick Start

```bash
# Install dependencies
cd file_organizer_v2
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

### Quick Reference

```bash
# Issue management
/pm:issue-start {number}     # Start working on issue
/pm:issue-sync {number}      # Sync progress to GitHub
/pm:issue-close {number}     # Close completed issue

# Epic management
/pm:epic-decompose {name}    # Break epic into tasks
/pm:epic-sync {name}         # Sync epic to GitHub

# Status views
/pm:issue-status             # View all issues
/pm:status                   # View complete status
```

**Why mandatory?** PM skills maintain CCPM consistency, prevent wrong-repo operations, enforce proper frontmatter, and create audit trails.

## ⚠️ CRITICAL: PM Skills Are Mandatory

**NEVER manually create or update GitHub issues/PRs or CCPM tracking documents.**
**ALWAYS use PM skills for ALL project management operations.**

See: `.claude/rules/pm-skills-mandatory.md` for complete requirements.

### Quick Reference

```bash
# Issue management
/pm:issue-start {number}     # Start working on issue
/pm:issue-sync {number}      # Sync progress to GitHub
/pm:issue-close {number}     # Close completed issue

# Epic management
/pm:epic-decompose {name}    # Break epic into tasks
/pm:epic-sync {name}         # Sync epic to GitHub

# Status views
/pm:issue-status             # View all issues
/pm:status                   # View complete status
```

**Why mandatory?** PM skills maintain CCPM consistency, prevent wrong-repo operations, enforce proper frontmatter, and create audit trails.

## Project Structure

```
Local-File-Organizer/
├── .claude/                          # CCPM project management
│   ├── commands/                  # PM commands
│   ├── prds/                      # Product requirements
│   ├── epics/                     # Epic planning workspace
│   ├── context/                   # Project-wide context
│   ├── agents/                    # Specialized agent definitions
│   └── rules/                     # Standard operation rules
│
├── file_organizer_v2/                # Main application (~25K LOC)
│   ├── src/file_organizer/
│   │   ├── models/                # AI model abstractions (650 LOC)
│   │   │   ├── base.py            # BaseModel interface, ModelConfig
│   │   │   ├── text_model.py      # Ollama text generation
│   │   │   ├── vision_model.py    # Vision-language models
│   │   │   └── audio_model.py     # Audio transcription (Phase 3)
│   │   │
│   │   ├── services/              # Business logic layer
│   │   │   ├── analytics/         # Storage & metrics analysis
│   │   │   ├── auto_tagging/      # Tag recommendation & learning
│   │   │   ├── deduplication/     # Image & document deduplication
│   │   │   │   ├── image_dedup/   # Perceptual hashing
│   │   │   │   ├── document_dedup/# Embedding-based dedup
│   │   │   │   ├── backup_manager.py
│   │   │   │   └── quality_assessor.py
│   │   │   ├── intelligence/      # User preference learning (21 modules)
│   │   │   │   ├── preference_tracker.py
│   │   │   │   ├── profile_manager.py
│   │   │   │   ├── pattern_learner.py
│   │   │   │   ├── confidence_engine.py
│   │   │   │   └── [16 more modules]
│   │   │   ├── text_processor.py  # Text file pipeline (13 KB)
│   │   │   ├── vision_processor.py# Image/video pipeline (14 KB)
│   │   │   ├── pattern_analyzer.py# Pattern detection (16 KB)
│   │   │   ├── smart_suggestions.py# Placement suggestions (19 KB)
│   │   │   └── misplacement_detector.py# Context analysis (17 KB)
│   │   │
│   │   ├── core/                  # Main orchestrator
│   │   │   └── file_organizer.py  # FileOrganizer class
│   │   │
│   │   ├── cli/                   # Command-line interfaces (6 modules)
│   │   │   ├── dedupe.py          # Deduplication commands
│   │   │   ├── profile.py         # Profile management
│   │   │   ├── undo_redo.py       # Undo/redo commands
│   │   │   ├── autotag.py         # Auto-tagging commands
│   │   │   └── analytics.py       # Analytics commands
│   │   │
│   │   ├── history/               # Operation history (6 modules, ~50 KB)
│   │   │   ├── operation_history.py
│   │   │   ├── operation_transaction.py
│   │   │   ├── history_cleanup.py
│   │   │   ├── history_exporter.py
│   │   │   ├── database_manager.py
│   │   │   └── models.py
│   │   │
│   │   ├── undo/                  # Undo/redo system (5 modules, ~50 KB)
│   │   │   ├── undo_manager.py
│   │   │   ├── rollback_executor.py
│   │   │   ├── operation_validator.py
│   │   │   ├── history_viewer.py
│   │   │   └── conflict_detector.py
│   │   │
│   │   ├── utils/                 # Utilities
│   │   │   ├── file_readers.py    # 10+ file format readers
│   │   │   ├── text_processing.py # Text utilities
│   │   │   └── chart_generator.py # Visual analytics
│   │   │
│   │   └── config/                # Configuration management
│   │
│   ├── tests/                     # 136 test files
│   │   ├── services/
│   │   │   ├── analytics/         # 4 test files
│   │   │   ├── auto_tagging/      # 4 test files
│   │   │   ├── intelligence/      # 8 test files
│   │   │   └── deduplication/
│   │   ├── history/               # 5 test files
│   │   └── undo/                  # 4 test files
│   │
│   ├── demo.py                    # CLI demo (~400 LOC)
│   └── pyproject.toml             # Project configuration
│
└── BUSINESS_REQUIREMENTS_DOCUMENT.md
```

---

## Architecture Overview

### Design Principles

1. **Privacy-First**: 100% local processing, zero cloud dependencies
2. **Model Abstraction**: Abstract AI model interface for framework flexibility
3. **Service Layer Pattern**: Business logic separate from models
4. **Strategy Pattern**: Different processors for different file types
5. **Type Safety**: Full type hints with strict mypy configuration
6. **Resource Management**: Context managers for automatic cleanup

### Core Components

| Component | Purpose | Location | Status |
|-----------|---------|----------|--------|
| **BaseModel** | Abstract AI model interface | `models/base.py` | ✅ Core |
| **ModelConfig** | Unified model configuration | `models/base.py` | ✅ Core |
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

### Data Flow

```
Input File → FileOrganizer → File Type Detection
    ↓
Text Files: TextProcessor → TextModel (Qwen 2.5 3B)
    ↓
    └→ Generate description, folder name, filename

Image/Video: VisionProcessor → VisionModel (Qwen 2.5-VL 7B)
    ↓
    └→ Visual analysis, OCR, description

Audio: AudioModel → faster-whisper (Phase 3)
    ↓
    └→ Transcription, metadata extraction

All Processors → PatternAnalyzer → SmartSuggestions
    ↓
    └→ Intelligence Services → User Preference Learning

Final Output: Organized files + Operation history
```

### Key Data Classes

```python
@dataclass
class ModelConfig:
    """AI model configuration"""
    name: str                      # Model identifier
    model_type: ModelType          # TEXT, VISION, AUDIO, VIDEO
    quantization: str = "q4_k_m"   # Quantization level
    device: DeviceType = AUTO      # CPU, CUDA, MPS, METAL
    temperature: float = 0.5       # Generation temperature
    max_tokens: int = 3000         # Context limit
    framework: str = "ollama"      # Inference framework

@dataclass
class ProcessedFile:
    """Text processing result"""
    filename: str
    description: str
    folder_name: str
    new_filename: str
    confidence: float

@dataclass
class ProcessedImage:
    """Vision processing result"""
    filename: str
    description: str
    folder_name: str
    new_filename: str
    ocr_text: Optional[str]
    confidence: float
```

---

## Dependencies & Setup

### System Requirements

- **Python**: 3.9+ (converted from 3.12+ in Phase 5 for broader compatibility)
- **Ollama**: Latest version for local inference
- **Storage**: ~10 GB for models
- **RAM**: 8 GB minimum, 16 GB recommended

### Installation

```bash
# 1. Clone repository
git clone <repo-url>
cd Local-File-Organizer/file_organizer_v2

# 2. Install Ollama (if not installed)
# macOS/Linux: curl -fsSL https://ollama.ai/install.sh | sh
# Windows: Download from ollama.ai

# 3. Pull required models
ollama pull qwen2.5:3b-instruct-q4_K_M    # Text: ~1.9 GB
ollama pull qwen2.5vl:7b-q4_K_M           # Vision: ~6.0 GB

# 4. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 5. Install package
pip install -e .

# 6. Verify installation
file-organizer --version
fo --version
```

### Core Dependencies

**AI Inference**:
- `ollama>=0.1.0` - Local LLM execution

**File Processing**:
- `Pillow>=10.0.0` - Images
- `PyMuPDF>=1.23.0` - PDFs
- `python-docx>=1.0.0` - Word docs
- `pandas>=2.0.0` - Spreadsheets
- `openpyxl>=3.1.0` - Excel
- `python-pptx>=0.6.0` - PowerPoint
- `ebooklib>=0.18` - EPUB

**NLP & Text**:
- `nltk>=3.8.0` - Text processing
- `faster-whisper>=0.10.0` - Audio (Phase 3)

**CLI & UI**:
- `typer[all]>=0.12.0` - CLI framework
- `rich>=13.0.0` - Rich output
- `textual>=0.48.0` - TUI (Phase 2)

**Database**:
- `sqlalchemy>=2.0.0` - ORM
- `alembic>=1.13.0` - Migrations

**Async & Queue**:
- `celery>=5.3.0` - Task queue
- `redis>=5.0.0` - Broker
- `websockets>=12.0` - WebSockets
- `httpx>=0.26.0` - Async HTTP

**Deduplication**:
- `imagededup>=0.3.0` - Image similarity

### Development Dependencies

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Required for development
- pytest>=7.4.0              # Testing
- pytest-asyncio             # Async tests
- pytest-cov                 # Coverage
- pytest-mock                # Mocking
- mypy>=1.8.0                # Type checking
- ruff>=0.1.0                # Linting
- black>=23.12.0             # Formatting
- isort>=5.13.0              # Import sorting
```

### Optional Dependencies

```bash
# Install specific feature sets
pip install -e ".[archive]"      # Archive format support (7z, RAR)
pip install -e ".[scientific]"   # Scientific formats (HDF5, NetCDF, MATLAB)
pip install -e ".[audio]"        # Audio transcription
pip install -e ".[video]"        # Advanced video processing
pip install -e ".[dedup]"        # Image deduplication
pip install -e ".[all]"          # All optional features

# Archive dependencies
- py7zr>=0.20.0              # 7Z archive support
- rarfile>=4.1               # RAR archive support (requires unrar tool)

# Scientific dependencies
- h5py>=3.10.0               # HDF5 file format
- netCDF4>=1.6.5             # NetCDF file format
- scipy>=1.11.0              # MATLAB .mat files (included in base)
```

---

## AI Model Configuration

### Supported Models

**Text Models** (via Ollama):
- `qwen2.5:3b-instruct-q4_K_M` - Default text model (~1.9 GB)
- 4-bit quantization for speed/memory balance
- Context window: 4,096 tokens

**Vision Models** (via Ollama):
- `qwen2.5vl:7b-q4_K_M` - Default vision model (~6.0 GB)
- Multi-modal: images + text input
- OCR + visual understanding

**Audio Models** (Phase 3):
- `faster-whisper` - Local transcription
- Supports multiple languages

### Device Support

```python
from file_organizer.models.base import DeviceType

DeviceType.AUTO    # Automatic detection (recommended)
DeviceType.CPU     # CPU inference (universal)
DeviceType.CUDA    # NVIDIA GPU (fastest)
DeviceType.MPS     # Apple Silicon (fast)
DeviceType.METAL   # Apple Metal (fast)
```

### Model Instantiation

```python
from file_organizer.models import TextModel, VisionModel, ModelConfig

# Text model with custom config
text_config = ModelConfig(
    name="qwen2.5:3b-instruct-q4_K_M",
    model_type=ModelType.TEXT,
    temperature=0.5,
    max_tokens=3000,
    device=DeviceType.AUTO
)
text_model = TextModel(text_config)

# Vision model with defaults
vision_model = VisionModel()

# Use as context manager (recommended)
with TextModel() as model:
    result = model.generate("Describe this file...")
```

### Adding New Models

To add a new model provider:

1. Create new class extending `BaseModel` in `models/`
2. Implement required methods: `generate()`, `generate_stream()`, `cleanup()`
3. Update `ModelConfig.framework` enum
4. Add tests in `tests/models/`

---

## Development Guidelines

### Code Style

**Formatting** (enforced):
- Black for code formatting
- isort for import sorting
- Line length: 88 characters (Black default)

**Linting** (enforced):
- Ruff with strict rules
- No unused imports/variables
- Consistent naming conventions

**Type Checking** (enforced):
```ini
[tool.mypy]
strict = true
disallow_untyped_defs = true
disallow_any_untyped = true
warn_return_any = true
warn_unused_ignores = true
```

### Naming Conventions

**Files & Modules**:
- `snake_case.py` for all Python files
- Match class name: `TextProcessor` → `text_processor.py`

**Classes**:
- `PascalCase` for classes
- `BaseModel`, `TextProcessor`, `FileOrganizer`

**Functions & Variables**:
- `snake_case` for functions and variables
- `process_file()`, `file_path`, `model_config`

**Constants**:
- `UPPER_SNAKE_CASE` for constants
- `MAX_TOKENS`, `DEFAULT_TEMPERATURE`

**Private**:
- Single underscore prefix: `_internal_helper()`
- Double underscore for name mangling: `__private_attr`

### File Organization

**Module Structure**:
```python
"""Module docstring.

Detailed description of module purpose.
"""

# Standard library imports
import os
from pathlib import Path
from typing import Optional, List

# Third-party imports
import ollama
from rich.console import Console

# Local imports
from file_organizer.models.base import BaseModel
from file_organizer.utils import sanitize_filename

# Constants
DEFAULT_TEMPERATURE = 0.5

# Classes and functions
class MyClass:
    """Class docstring."""
    pass
```

### Error Handling

**Custom Exceptions**:
```python
# Define in relevant module
class FileReadError(Exception):
    """Raised when file cannot be read."""
    pass

# Use with context
try:
    content = read_file(path)
except FileNotFoundError:
    raise FileReadError(f"File not found: {path}")
```

**Logging**:
```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate levels
logger.debug("Processing file: %s", filename)
logger.info("File organized successfully")
logger.warning("Model took longer than expected")
logger.error("Failed to process file: %s", error)
```

### Documentation

**Docstrings** (Google style):
```python
def process_file(file_path: Path, model: TextModel) -> ProcessedFile:
    """Process a text file using AI model.

    Args:
        file_path: Path to the file to process
        model: AI model instance to use

    Returns:
        ProcessedFile containing organization metadata

    Raises:
        FileReadError: If file cannot be read
        ModelError: If AI model fails

    Example:
        >>> result = process_file(Path("doc.txt"), text_model)
        >>> print(result.folder_name)
        'Documents/Technical'
    """
    pass
```

### Type Hints

**Always use type hints**:
```python
# Good
def organize_files(
    input_dir: Path,
    output_dir: Path,
    model: BaseModel
) -> List[ProcessedFile]:
    pass

# Bad
def organize_files(input_dir, output_dir, model):
    pass
```

**Use modern syntax** (Python 3.12+):
```python
# Good (3.12+)
def process(items: list[str]) -> dict[str, int]:
    pass

# Avoid (legacy)
from typing import List, Dict
def process(items: List[str]) -> Dict[str, int]:
    pass
```

### Git Commit Messages

**Format**:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Tests
- `chore`: Maintenance

**Examples**:
```
feat(models): Add support for GPT-4V vision model

Implement GPT4VisionModel class extending BaseModel.
Includes streaming support and context management.

Closes #42

fix(text_processor): Handle empty PDF files gracefully

Previously crashed on empty PDFs. Now returns empty
string with warning log.

Fixes #56
```

---

## Testing Strategy

### Test Organization

```
tests/
├── services/
│   ├── analytics/           # Analytics tests
│   ├── auto_tagging/        # Auto-tagging tests
│   ├── intelligence/        # Intelligence service tests (8 files)
│   └── deduplication/       # Deduplication tests
├── history/                 # History system tests (5 files)
├── undo/                    # Undo/redo tests (4 files)
└── test_smart_suggestions.py
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=file_organizer --cov-report=html

# Run specific test file
pytest tests/services/test_text_processor.py

# Run specific test
pytest tests/services/test_text_processor.py::test_process_pdf

# Run marked tests
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m "not slow"    # Exclude slow tests

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Test Markers

```python
import pytest

@pytest.mark.unit
def test_sanitize_filename():
    """Unit test for filename sanitization."""
    pass

@pytest.mark.integration
def test_file_organization_pipeline():
    """Integration test for full pipeline."""
    pass

@pytest.mark.slow
def test_large_batch_processing():
    """Slow test for batch processing."""
    pass
```

### Writing Tests

**Structure**:
```python
import pytest
from pathlib import Path
from file_organizer.services import TextProcessor

@pytest.fixture
def text_processor():
    """Create TextProcessor instance."""
    return TextProcessor()

@pytest.fixture
def sample_file(tmp_path):
    """Create sample text file."""
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Sample content")
    return file_path

def test_process_text_file(text_processor, sample_file):
    """Test processing a text file."""
    # Arrange
    expected_folder = "Documents"

    # Act
    result = text_processor.process(sample_file)

    # Assert
    assert result.folder_name == expected_folder
    assert result.confidence > 0.5
```

**Mocking AI Models**:
```python
from unittest.mock import Mock, patch

def test_process_with_mock_model(text_processor):
    """Test processing with mocked AI model."""
    # Create mock
    mock_model = Mock()
    mock_model.generate.return_value = "Mocked description"

    # Use mock
    with patch('file_organizer.models.text_model.TextModel', return_value=mock_model):
        result = text_processor.process(Path("test.txt"))

    # Verify
    assert result.description == "Mocked description"
    mock_model.generate.assert_called_once()
```

### Coverage Goals

- **Unit tests**: 80%+ coverage
- **Integration tests**: Key workflows
- **E2E tests**: demo.py scenarios

### CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -e ".[dev]"
      - run: pytest --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
```

---

## Common Workflows

### 1. Adding a New File Type

```bash
# 1. Add format reader in utils/file_readers.py
def read_new_format_file(file_path: Path) -> str:
    """Read .newformat files."""
    # Implementation
    pass

# 2. Update text_processor.py or vision_processor.py
SUPPORTED_FORMATS = {
    '.newformat': read_new_format_file,
    # ... existing formats
}

# 3. Add tests
# tests/test_new_format.py

# 4. Update documentation
# Add to Supported File Types section
```

### 2. Adding a New AI Model Provider

```python
# 1. Create new model class
# file_organizer/models/new_provider_model.py

from file_organizer.models.base import BaseModel, ModelConfig
from typing import Iterator

class NewProviderModel(BaseModel):
    """Model implementation for NewProvider."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        # Initialize provider client

    def generate(self, prompt: str) -> str:
        """Generate text response."""
        # Implementation
        pass

    def generate_stream(self, prompt: str) -> Iterator[str]:
        """Stream text response."""
        # Implementation
        pass

    def cleanup(self) -> None:
        """Cleanup resources."""
        # Implementation
        pass

# 2. Add tests
# tests/models/test_new_provider_model.py

# 3. Update ModelConfig.framework enum
# models/base.py
```

### 3. Adding a New Service

```python
# 1. Create service module
# file_organizer/services/my_service.py

from pathlib import Path
from dataclasses import dataclass

@dataclass
class MyServiceResult:
    """Result from my service."""
    field1: str
    field2: int

class MyService:
    """Service for doing X."""

    def __init__(self):
        # Initialize service
        pass

    def process(self, file_path: Path) -> MyServiceResult:
        """Process file."""
        # Implementation
        pass

# 2. Add tests
# tests/services/test_my_service.py

# 3. Integrate with FileOrganizer
# core/file_organizer.py

# 4. Add CLI command if needed
# cli/my_service.py
```

### 4. Creating a New CLI Command

```python
# 1. Create command module
# file_organizer/cli/my_command.py

import typer
from rich.console import Console

app = typer.Typer()
console = Console()

@app.command()
def my_command(
    input_path: Path = typer.Argument(..., help="Input path"),
    option: bool = typer.Option(False, "--option", help="Enable option")
):
    """My command description."""
    console.print("[bold]Running my command...[/bold]")
    # Implementation

# 2. Register in main CLI
# file_organizer/cli/__init__.py
from file_organizer.cli.my_command import app as my_command_app
app.add_typer(my_command_app, name="my-command")

# 3. Test it
file-organizer my-command --help
```

### 5. Debugging Model Issues

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Test model directly
from file_organizer.models import TextModel

with TextModel() as model:
    response = model.generate("Test prompt")
    print(f"Response: {response}")

# Check Ollama status
ollama list  # List available models
ollama ps    # Show running models

# Run model manually
ollama run qwen2.5:3b-instruct-q4_K_M "Test prompt"
```

### 6. Running Demo with Custom Files

```python
# Organize specific directory
python3 demo.py --input ~/Downloads --output ~/Organized

# Dry run (preview only)
python3 demo.py --input ~/Downloads --output ~/Organized --dry-run

# With sample files
python3 demo.py --sample

# Verbose output
python3 demo.py --input ~/Downloads --output ~/Organized --verbose
```

### 7. Database Migrations

```bash
# Create new migration
cd file_organizer_v2
alembic revision -m "Add new table"

# Edit migration file
# file_organizer/alembic/versions/xxx_add_new_table.py

# Apply migration
alembic upgrade head

# Rollback migration
alembic downgrade -1

# Check current version
alembic current
```

---

## Supported File Types

### Document Formats (9 types)

| Format | Extension | Reader Function | Status |
|--------|-----------|----------------|--------|
| Plain Text | `.txt` | `read_text_file()` | ✅ |
| Markdown | `.md` | `read_markdown_file()` | ✅ |
| PDF | `.pdf` | `read_pdf_file()` | ✅ |
| Word | `.docx`, `.doc` | `read_docx_file()` | ✅ |
| Spreadsheet | `.csv`, `.xlsx`, `.xls` | `read_excel_file()` | ✅ |
| Presentation | `.ppt`, `.pptx` | `read_presentation_file()` | ✅ |
| E-book | `.epub` | `read_epub_file()` | ✅ |

### Image Formats (6 types)

| Format | Extension | Processor | Status |
|--------|-----------|-----------|--------|
| JPEG | `.jpg`, `.jpeg` | VisionProcessor | ✅ |
| PNG | `.png` | VisionProcessor | ✅ |
| GIF | `.gif` | VisionProcessor | ✅ |
| BMP | `.bmp` | VisionProcessor | ✅ |
| TIFF | `.tiff`, `.tif` | VisionProcessor | ✅ |

### Video Formats (5 types)

| Format | Extension | Processor | Status |
|--------|-----------|-----------|--------|
| MP4 | `.mp4` | VisionProcessor | ✅ |
| AVI | `.avi` | VisionProcessor | ✅ |
| MKV | `.mkv` | VisionProcessor | ✅ |
| MOV | `.mov` | VisionProcessor | ✅ |
| WMV | `.wmv` | VisionProcessor | ✅ |

### Audio Formats (5 types)

| Format | Extension | Processor | Status |
|--------|-----------|-----------|--------|
| MP3 | `.mp3` | AudioModel | ✅ |
| WAV | `.wav` | AudioModel | ✅ |
| FLAC | `.flac` | AudioModel | ✅ |
| M4A | `.m4a` | AudioModel | ✅ |
| OGG | `.ogg` | AudioModel | ✅ |

### Archive Formats (4 types)

| Format | Extension | Reader Function | Status |
|--------|-----------|----------------|--------|
| ZIP | `.zip` | `read_zip_file()` | ✅ |
| 7-Zip | `.7z` | `read_7z_file()` | ✅ |
| TAR | `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz` | `read_tar_file()` | ✅ |
| RAR | `.rar` | `read_rar_file()` | ✅ |

**Features**:
- List archive contents without extraction
- Calculate compression ratios
- Extract metadata (file counts, sizes, dates)
- Detect encryption
- Memory-efficient (no extraction to disk)

**Dependencies**:
- ZIP, TAR: Built-in Python support
- 7Z: Requires `py7zr` (optional)
- RAR: Requires `rarfile` and `unrar` tool (optional)

### Scientific Formats (3 types)

| Format | Extension | Reader Function | Status |
|--------|-----------|----------------|--------|
| HDF5 | `.hdf5`, `.h5`, `.hdf` | `read_hdf5_file()` | ✅ |
| NetCDF | `.nc`, `.nc4`, `.netcdf` | `read_netcdf_file()` | ✅ |
| MATLAB | `.mat` | `read_mat_file()` | ✅ |

**Features**:
- Extract dataset structure and metadata
- List variables, dimensions, and attributes
- Display data types and shapes
- Show global attributes
- No data loading (metadata only for efficiency)

**Dependencies**:
- HDF5: Requires `h5py` (optional)
- NetCDF: Requires `netCDF4` (optional)
- MATLAB: Requires `scipy` (included in base dependencies)

### CAD Formats (6 types)

| Format | Extension | Reader Function | Status |
|--------|-----------|----------------|--------|
| DXF | `.dxf` | `read_dxf_file()` | ✅ |
| DWG | `.dwg` | `read_dwg_file()` | ✅ |
| STEP | `.step`, `.stp` | `read_step_file()` | ✅ |
| IGES | `.iges`, `.igs` | `read_iges_file()` | ✅ |

**Features**:
- Extract CAD file metadata (title, author, creation date)
- List layers and their properties (DXF/DWG)
- Count entities and analyze drawing structure
- Extract block definitions and references (DXF/DWG)
- Parse header information (STEP/IGES)
- Display file schema and version information
- Memory-efficient metadata extraction (no full model loading)

**Dependencies**:
- DXF: Requires `ezdxf` (optional but recommended)
- DWG: Requires `ezdxf` (limited support) or ODA File Converter
- STEP: Built-in Python support (text parsing)
- IGES: Built-in Python support (text parsing)

**Notes**:
- DWG is a proprietary format with limited open-source support
- For full DWG support, consider using ODA File Converter to convert to DXF
- STEP and IGES files are parsed for header metadata only
- DXF files provide the most comprehensive metadata extraction

**Total**: 43 file types supported (all active)

---

## Performance Notes

### Processing Speed

| File Type | Average Time | Model Used | Notes |
|-----------|-------------|------------|-------|
| Text (< 1 MB) | 2-5 seconds | Qwen 2.5 3B | Fast, local |
| Text (1-10 MB) | 5-15 seconds | Qwen 2.5 3B | Chunking applied |
| Image | 3-8 seconds | Qwen 2.5-VL 7B | GPU accelerated |
| Video | 5-20 seconds | Qwen 2.5-VL 7B | Samples frames |
| PDF (text) | 3-10 seconds | Qwen 2.5 3B | Depends on pages |
| PDF (scanned) | 8-20 seconds | Qwen 2.5-VL 7B | OCR required |

### Optimization Tips

1. **Use GPU acceleration** if available (CUDA/MPS/Metal)
2. **Batch processing** for multiple files
3. **Adjust temperature** (lower = faster, more deterministic)
4. **Reduce max_tokens** if descriptions are too long
5. **Use quantized models** (Q4 is good balance)
6. **Close unused models** to free memory

### Memory Usage

| Component | RAM Usage | Notes |
|-----------|-----------|-------|
| Qwen 2.5 3B (Q4) | ~2.5 GB | Text model |
| Qwen 2.5-VL 7B (Q4) | ~5.5 GB | Vision model |
| Base application | ~200 MB | Python + deps |
| Per file buffer | ~50-100 MB | During processing |

**Recommended**: 8 GB RAM minimum, 16 GB for comfortable performance

### Scalability

- **Single file**: Synchronous processing
- **Batch files**: Parallel processing planned (Phase 5)
- **Large datasets**: Use Celery task queue (Phase 5)
- **Enterprise**: Microservices architecture (Phase 6)

---

## Additional Resources

### Documentation

- **Business Requirements**: `BUSINESS_REQUIREMENTS_DOCUMENT.md`
- **API Docs**: Generated from docstrings
- **CLI Help**: `file-organizer --help`

### Phase Roadmap

- ✅ **Phase 1**: Text + Image processing (Complete)
- 📅 **Phase 2**: Modern UI (TUI with Textual) - 4 tasks remaining (84%)
- 📅 **Phase 3**: Feature Expansion - 1 task remaining (94%) - Audio, PARA, JD, CAD, Archives, Scientific
- 📅 **Phase 4**: Intelligence & Learning - 1 task remaining (96%) - Dedup, Preferences, Undo/Redo, Analytics
- ✅ **Phase 5**: Architecture & Performance (Complete) - Events, Daemon, Docker, CI/CD
- 📅 **Phase 6**: Web Interface - 1 task remaining (95%)

### Contributing

1. Fork repository
2. Create feature branch: `git checkout -b feature/my-feature`
3. Make changes with tests
4. Run quality checks: `pytest && mypy . && ruff check .`
5. Commit: `git commit -m "feat: add my feature"`
6. Push and create PR

### Support

- Issues: GitHub Issues
- Questions: GitHub Discussions
- Email: [Add contact email]

---

**Last Updated**: 2026-02-08
**Version**: 2.0.0
**Maintainers**: [Add maintainer names]
