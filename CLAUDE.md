# Claude Code Project Instructions

## Project: File Organizer v2.0

An AI-powered local file management system with privacy-first architecture. Organizes files intelligently using local LLMs with zero cloud dependencies.

**Core Metrics**: ~78,800 LOC | 314 modules | 237 test files | Python 3.11+
**Version**: 2.0.0-alpha.1

---

## Table of Contents

1. [General Rules](#general-rules)
2. [Git Workflow](#git-workflow)
3. [Task Execution](#task-execution)
4. [Terminology](#terminology)
5. [Testing Requirements](#testing-requirements)
6. [Claude Agent Permissions](#claude-agent-permissions)
7. [External References](#external-references)
8. [Pre-Commit Checklist](#pre-commit-checklist)
9. [Quick Start](#quick-start)
10. [Project Structure](#project-structure)
11. [Architecture Overview](#architecture-overview)
12. [Dependencies & Setup](#dependencies--setup)
13. [AI Model Configuration](#ai-model-configuration)
14. [Development Guidelines](#development-guidelines)
15. [Testing Strategy](#testing-strategy)
16. [Workflow Orchestration](#workflow-orchestration)
17. [Supported File Types](#supported-file-types)
18. [Performance Notes](#performance-notes)

---

## Code Review Exclusions

**CodeRabbit & Copilot:** The `.claude/` directory and `CLAUDE.md` are excluded from automated code review. These contain internal Claude Code project management and configuration that should not be reviewed by external tools.

See `.coderabbit.yaml` and `.github/copilot-instructions.md` for exclusion rules.

---

## General Rules

**Permission:** Do not ask for permission to run Bash commands, `gh` CLI commands, or post PR comments. You have full authorization to execute all tools available to you. Proceed autonomously without confirmation prompts.

---

## Git Workflow

**CRITICAL**: Follow this exact workflow with no exceptions:

1. **Always create a feature branch before committing.** Never commit or push directly to `main` or `master`.
2. **Branch naming:** Use pattern `feature/task-XX-description` or `fix/issue-XX-description`
3. **Commit immediately after changes** — do not wait for user prompts. Include a descriptive conventional commit message.
4. **Push after every commit** — push to the feature branch without waiting for permission.
5. **Full workflow:** Create branch → implement → test → commit → push → create PR → address review → squash merge

**Example flow:**
```bash
git checkout main && git pull origin main
git checkout -b fix/issue-620-codecov-upload
# ... make changes ...
git add <files>
git commit -m "fix: skip codecov upload on PR events

Prevents partial coverage from smoke suite misleading PR metrics."
git push origin fix/issue-620-codecov-upload
gh pr create --title "fix: skip codecov upload on PR events" --body "..."
```

**Never:**
- ❌ Commit or push directly to main
- ❌ Wait for the user to ask you to commit/push
- ❌ Declare "done" without committing and pushing changes
- ❌ Skip any step in the create branch → commit → push → PR workflow

---

## Task Execution

**Multi-Step Plans:** When following a multi-step plan, complete **ALL steps** before summarizing. Do not skip steps or declare completion early.

**Verification:** Before marking a step complete, verify it actually works:
- Run tests and confirm they pass
- Check that files were created/modified as expected
- Verify code review is complete if required
- Confirm coverage gates pass if applicable

**Code Review Steps:** Never skip code review or coverage gate steps. These are mandatory verification points, not optional.

**Completion Criteria:** Do not say "All done" until ALL steps are verified. If any step fails verification, fix it before moving on.

---

## Terminology

**Build:** When you see "build", it means **local Xcode build** unless explicitly stated otherwise. Use `xcodebuild` or Xcode UI. Do NOT check GitHub Actions CI.

**CI:** "CI" refers to GitHub Actions workflows. If you need to check CI status, use `gh workflow view` or `gh pr checks`.

**PR status:** Always verify both local tests AND GitHub CI checks pass before declaring a PR ready to merge.

---

## Testing Requirements

**Real Assertions:** Always write real assertions with meaningful test logic.
- ✅ Write actual assertions that verify behavior
- ❌ Never use `pytest.skip` as a placeholder
- ❌ Never write no-op assertions that don't test anything
- ❌ Never use `assert True` or `pass` in test bodies

**Test Quality:** Tests must actually exercise the code being tested and verify expected outcomes. If you find yourself writing a test that doesn't assert anything meaningful, the test design is wrong — fix it rather than leaving a placeholder.

---

## External References

This document contains critical enforcement rules and operational guidelines. Detailed reference documentation is organized in the following structure:

### Architecture & Design

- **[Project Structure](docs/architecture/project-structure.md)** - Complete directory tree, module organization (314 modules)
- **[Architecture Overview](docs/architecture/architecture-overview.md)** - Design principles, core components, data flow

### Setup & Configuration

- **[Dependencies & Setup](docs/setup/dependencies.md)** - Installation, system requirements, optional dependencies
- **[AI Model Configuration](docs/setup/models.md)** - Supported models, device support, model selection

### Testing & Quality

- **[Testing Strategy](docs/testing/testing-strategy.md)** - Test organization, markers, coverage goals, running tests

### Reference

- **[Supported File Types](docs/reference/file-formats.md)** - Complete file format support matrix (48+ types)
- **[Performance Metrics](docs/reference/performance.md)** - Processing times by file type, memory usage by component

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

A pre-commit configuration is defined in `.pre-commit-config.yaml`. After running `pre-commit install`, hooks run automatically on every commit. The configured hooks are:

- `ruff check` — lint the full project and `src/`
- `pytest` — websocket validations, CI guardrails, web UI, and non-regression tests
- `codespell` — spell check `src/` and `docs/`
- `absolute-path-check` — blocks absolute paths (e.g. `/Users/…`) in staged diffs
- `pymarkdown` — markdown lint using `.pymarkdown.json` rules

If a hook fails:
- Fix the reported violations (e.g. `ruff check . --fix` for lint, `codespell --write-changes` for spelling)
- Stage fixed files: `git add <files>`
- Try commit again

**This hook prevents accidental commits with lint, test, spelling, or markdown violations.**

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

See **[Project Structure Reference](docs/architecture/project-structure.md)** for the complete directory tree.

**Quick Summary:**
- `src/file_organizer/` — Main application (78,800 LOC, 314 modules)
- `tests/` — Test suite (237 test files)
- `.claude/` — CCPM project management
- `docs/` — Documentation
- `scripts/` — Build and utility scripts

---

## Architecture Overview

See **[Architecture Overview Reference](docs/architecture/architecture-overview.md)** for complete design principles, core components table, and data flow diagram.

**Quick Summary:**
- Privacy-first: 100% local processing
- 20+ core components with clear separation of concerns
- Service layer pattern with plugin extensibility
- Event-driven architecture for loose coupling

---

## Dependencies & Setup

See **[Dependencies & Setup Reference](docs/setup/dependencies.md)** for system requirements, installation steps, and optional dependency groups.

**Quick Start:**
```bash
pip install -e .
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
file-organizer --help
```

**Requirements:** Python 3.11+, Ollama, 8 GB RAM, 10 GB storage

---

## AI Model Configuration

See **[AI Model Configuration Reference](docs/setup/models.md)** for supported models, device support options, and configuration details.

**Default Models:**
- Text: Qwen 2.5 3B (~1.9 GB)
- Vision: Qwen 2.5-VL 7B (~6.0 GB)
- Audio: faster-whisper (local, multi-language)

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

- After ANY correction from the user: update 'tasks/lessons.md' with the pattern
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
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
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

```text
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

See **[Testing Strategy Reference](docs/testing/testing-strategy.md)** for test runners, markers, and coverage goals.

**Quick Test Commands:**
```bash
pytest                        # Run all tests
pytest --cov=file_organizer  # With coverage report
pytest -m "not regression"   # Skip regression tests
pytest -x -q                 # Stop on first failure
```

**Coverage Goals:** 80%+ unit, key workflows integrated, CI validation

---

## Supported File Types

See **[File Formats Reference](docs/reference/file-formats.md)** for complete list of supported file types.

**Supported Categories:**
- Documents (11), Images (7), Video (5), Audio (5)
- Archives (7), Scientific (7), CAD (6)
- **Total:** 48+ file types across 7 categories

---

## Performance Notes

See **[Performance Reference](docs/reference/performance.md)** for processing times and memory requirements.

**Quick Metrics:**
- Text: 2-5s, Image: 3-8s, Video: 5-20s, Audio: 2-10s
- Qwen 3B: 2.5 GB RAM, Qwen 7B: 5.5 GB RAM, App: 200 MB

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
