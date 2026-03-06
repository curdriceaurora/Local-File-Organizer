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
4. [Multi-Task Execution Strategy](#multi-task-execution-strategy)
5. [Terminology](#terminology)
6. [Testing Requirements](#testing-requirements)
7. [Claude Agent Permissions](#claude-agent-permissions)
8. [External References](#external-references)
9. [Pre-Commit Checklist](#pre-commit-checklist)
10. [Quick Start](#quick-start)
11. [Project Structure](#project-structure)
12. [Architecture Overview](#architecture-overview)
13. [Dependencies & Setup](#dependencies--setup)
14. [AI Model Configuration](#ai-model-configuration)
15. [Development Guidelines](#development-guidelines)
16. [Testing Strategy](#testing-strategy)
17. [Workflow Orchestration](#workflow-orchestration)
18. [Supported File Types](#supported-file-types)
19. [Performance Notes](#performance-notes)

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
- Verify code review is complete if required (use `/code-reviewer` skill after major implementations)
- Confirm coverage gates pass if applicable
- Run pre-commit validation: `bash .claude/scripts/pre-commit-validation.sh`

**Mandatory Quality Gates (In Order - Non-Negotiable):**

1. **Code Simplification** (`/simplify`)
   - After significant code changes (>50 lines of new code)
   - Reviews for reuse, efficiency, and quality issues
   - **MUST run BEFORE code review**
   - Fixes suggestions and stages changes

2. **Code Review** (`/code-reviewer`)
   - After completing major implementation steps (features, bug fixes, tests)
   - Validates against CLAUDE.md standards
   - Checks for architectural, design, and logic issues
   - **MUST run BEFORE pre-commit validation**
   - Addresses findings and stages changes

3. **Pre-Commit Validation**
   - Run: `bash .claude/scripts/pre-commit-validation.sh`
   - Validates: linting, formatting, types, tests, patterns
   - **MUST PASS before committing**
   - Pre-commit will prompt to run quality gates if changes are significant

4. **CCPM Tracking** (Mandatory)
   - Use `/pm:issue-start` when beginning work
   - Use `/pm:issue-sync` after major progress
   - Use `/pm:issue-close` when task complete
   - **Non-optional** - provides visibility and audit trail

**Order Matters:** Simplify → Code Review → Pre-Commit → Commit → CCPM Sync

**What Each Gate Catches:**
- **Automation (Pre-Commit)**: Linting, formatting, type checking, basic tests, patterns
- **Code Review**: Test logic, assertions, API contracts, design patterns, error handling
- **Simplify**: Code reuse, efficiency, unnecessary complexity
- **Copilot Review**: Additional cross-file patterns, edge cases (happens in PR review, should be caught earlier)

**Why Order Matters:** Earlier gates catch issues before later gates. Test logic must be validated by `/code-reviewer` before pre-commit can verify it. Pre-commit can't validate whether assertions are meaningful or if tests match API contracts.

**Completion Criteria:** Do not say "All done" until ALL steps are verified. If any step fails verification, fix it before moving on.

---

## Multi-Task Execution Strategy

**CRITICAL:** When decomposing a task into multiple PRs or subtasks, apply MECE principles and dependency analysis BEFORE creating branches.

### MECE Decomposition (Mutually Exclusive, Collectively Exhaustive)

Every subtask must satisfy:

1. **Mutually Exclusive**: Each subtask touches different files/components
   - ❌ Bad: PR #1 modifies `organize_routes.py`, PR #2 also modifies `organize_routes.py`
   - ✅ Good: PR #1 modifies `files_routes.py`, PR #2 modifies `organize_routes.py`

2. **Collectively Exhaustive**: All subtasks together complete the requirement
   - ✅ Task 610.1: Bulk operations (rename/move/delete)
   - ✅ Task 610.2: Dashboard metrics
   - ✅ Task 610.3: Live SSE streams
   - ❌ Missing: Marketplace modernization (should be a separate task or included)

3. **Independent Mergeable**: PRs can merge in any order without conflicts
   - Run merge order analysis before starting
   - If PR A blocks PR B, sequence them instead of parallelizing

### Dependency Analysis Checklist

Before creating parallel PRs:

```text
□ List all files that will be modified across all subtasks
□ Check for file overlaps (conflict risk)
□ Identify hard dependencies (PR A must merge before PR B)
□ Plan merge order: dependencies first, then independents
□ If overlaps exist: sequence instead of parallelize
```

### Implementation Pattern

**Step 1: Decompose with MECE**
```bash
# Create truly independent subtasks
Task 610.1: Bulk File Operations
  - Files: files_routes.py, templates/files/*

Task 610.2: Profile Dashboard
  - Files: router.py, templates/dashboard_pulse.html

Task 610.3: Live SSE Streams
  - Files: organize_routes.py, static/js/app.js (SSE only)

Task 610.4: Marketplace Modernization
  - Files: marketplace_routes.py, templates/marketplace/*
```

**Step 2: Create CCPM Tracking**
```bash
# For each subtask:
/pm:epic-start task-610
cat > .claude/epics/task-610/1-bulk-operations.md << EOF
---
name: bulk-file-operations
status: open
---
# Task 610.1: Bulk File Operations
...
EOF
```

**Step 3: Execute Sequentially with Verification**
```bash
# Task 1
/pm:issue-start 610.1
# ... implement ...
/simplify          # Review code quality
/code-reviewer     # Validate implementation
bash .claude/scripts/pre-commit-validation.sh  # Quality gate
git commit & git push
/pm:issue-sync 610.1
/pm:issue-close 610.1

# Task 2 (can now start, independent of Task 1)
/pm:issue-start 610.2
# ... same workflow ...
```

**Step 4: Merge in Dependency Order**
```bash
# No dependencies? Merge any order - no rebases needed
# PR #628 → PR #629 → PR #630 → PR #631
# All merge cleanly because truly independent
```

### Red Flags (Indicates Bad Decomposition)

- ❌ "PR A and PR B both modify the same file"
- ❌ "PR B can't merge until PR A merges"
- ❌ "Need to rebase PR B after PR A merges"
- ❌ "4 PRs created but 2 overlap in scope"
- ❌ "Work includes unrelated features (smoke tests, old branches)"

If any flag appears: **STOP. Re-decompose before creating branches.**

### Parallelization vs Sequencing Decision

**Parallelize only if:**
- ✅ True file separation (no overlaps)
- ✅ No dependencies between tasks
- ✅ Each task can merge independently
- ✅ PR count ≤ 3 (coordination overhead grows with each PR)

**Sequence instead if:**
- ❌ Any file overlap exists
- ❌ Task B depends on Task A
- ❌ Merge order matters
- ❌ More than 3 parallel PRs

---

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

**CCPM Framework Maintenance** (MANDATORY):
- Use `/pm:issue-start` when beginning work on any task
- Use `/pm:issue-sync` to update progress and sync with GitHub
- Use `/pm:issue-close` when tasks are complete
- Create and update daily logs in `.claude/epics/sprint-*/daily-logs/` as work progresses
- Update execution status files in `.claude/epics/*/execution-status.md`
- Follow all rules in `.claude/rules/` directory
- **CCPM tracking is NOT optional - it provides visibility and audit trails**

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

**Code Quality Validation** (CRITICAL - MANDATORY before EVERY commit):
```bash
# Run validation BEFORE committing
bash .claude/scripts/pre-commit-validation.sh
# If fails: fix issues and run again
# If passes: safe to commit
git commit -m "message"
```
Do not bypass this step. Validation catches issues that code review would flag later.

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

### Complete Quality Validation Script

**First**, run the automated validation script which performs all checks:

```bash
bash .claude/scripts/pre-commit-validation.sh
```

This single command validates:
- ✅ Branch verification
- ✅ Code linting (ruff check)
- ✅ Code formatting (ruff format)
- ✅ Build artifacts detection (`.coverage`, `*.bak`, `*.pyc`)
- ✅ Pattern validation (dict-style dataclass access, imports, etc.)
- ✅ Smoke test suite (`pytest tests/ -m smoke`)
- ✅ Broken links in markdown
- ✅ Type checking

**If validation fails**, fix the violations and re-run the script until it passes. **NEVER proceed if validation fails.**

### Alternative: Manual Steps (If Script Unavailable)

If the validation script is unavailable, complete these steps manually:

#### Step 1: Code Quality Validation

```bash
ruff check .
```

- If violations found, run: `ruff check . --fix`
- Verify all violations are resolved before proceeding

#### Step 2: Code Formatting

```bash
ruff format . --check
```

- If formatting issues found, run: `ruff format .` to auto-fix
- Verify formatting passes check before proceeding

#### Step 3: Run Smoke Test Suite

```bash
pytest tests/ -m smoke -x -q
```

- Ensure all smoke tests pass
- Smoke suite (<30s) runs critical path tests; full suite runs in CI
- Do NOT commit with failing tests

#### Step 4: Review Your Diff

```bash
git diff --cached
```

- Verify no duplicate imports
- Verify no misplaced lines (e.g., pytestmark in wrong location)
- Verify changes match intended modifications
- Check for known patterns (see `.claude/rules/code-quality-validation.md`)

#### Step 5: Commit Only If All Pass

```bash
git commit -m "message"
```
**NEVER commit if any validation fails.**

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

## ⚠️ CRITICAL: PM Skills and CCPM Tracking Are Mandatory

**CCPM Framework is MANDATORY for ALL work:**
- Use `/pm:issue-start` when beginning any task
- Use `/pm:issue-sync` to update progress and GitHub
- Use `/pm:issue-close` when task is complete
- Creates visibility, audit trail, and resumability

**NEVER manually create or update GitHub issues/PRs without PM skills:**
- ❌ Don't manually create GitHub PRs
- ❌ Don't manually post GitHub comments
- ❌ Don't manually update tracking documents
- ✅ Use PM skills for all GitHub operations

**Why this matters:**
- Without CCPM tracking: "DUDE WHERE ARE YOU?" (no visibility)
- Without PM skills: Comments stay unresolved despite fixes
- Without structure: Merge conflicts and churn (see Issue #610 lessons)

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
- Use plan mode ESPECIALLY for multi-task work (use MECE decomposition)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Write detailed specs upfront to reduce ambiguity
- Explicitly document task dependencies and merge order

### 2. Quality Gates (Non-Negotiable)

Every major implementation must pass these gates in order:

1. **Code Simplification** (`/simplify` skill)
   - After significant code changes (>50 lines of new code)
   - Reviews for reuse, efficiency, quality issues
   - Must complete BEFORE code review

2. **Code Review** (`/code-reviewer` skill)
   - After completing major implementation steps
   - Validates against CLAUDE.md standards
   - Checks for architectural issues
   - Must complete BEFORE committing

3. **Pre-Commit Validation**
   - Run: `bash .claude/scripts/pre-commit-validation.sh`
   - Must PASS before committing
   - Catches lint, format, test, artifact, pattern issues

4. **CCPM Tracking** (PM skills)
   - Use `/pm:issue-start` when beginning work
   - Use `/pm:issue-sync` after major progress
   - Use `/pm:issue-close` when task complete
   - Maintains visibility and audit trail

**Order matters**: Simplify → Code Review → Pre-Commit → Commit → CCPM Sync

### 3. CCPM Framework (Mandatory)

**NEVER skip CCPM tracking. This is how work visibility is maintained.**

For any task:
```bash
# Start work
/pm:issue-start {issue_number}

# Do work with quality gates
/simplify          # After major code changes
/code-reviewer     # After implementation complete
bash .claude/scripts/pre-commit-validation.sh  # Before commit

# Sync progress periodically
/pm:issue-sync {issue_number}

# When complete
/pm:issue-close {issue_number}
```

Without CCPM tracking:
- ❌ No visibility into what you're doing
- ❌ Can't resume work if context breaks
- ❌ User can't track progress
- ❌ No audit trail of decisions

### 4. Subagent Strategy

- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution
- **DO NOT parallelize multi-task work without MECE decomposition first**

### 5. Verification Before Done

- Never mark a task complete without proving it works
- Verify at system boundaries: GitHub PRs exist, CI passes, comments resolved
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness
- Query GitHub API to verify state (don't assume)

### 6. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 7. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Decompose with MECE, write plan, document dependencies
2. **Verify Plan**: Review against coding standards (use `/code-reviewer`)
3. **Track Progress**: Use CCPM (`/pm:issue-start`, `/pm:issue-sync`)
4. **Apply Quality Gates**: Simplify → Code Review → Pre-Commit → Commit
5. **Capture Lessons**: Update memory/lessons after corrections

## Core Principles

- **Accuracy Over Speed**: Verification at each step prevents costly churn
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Use Right Tools**: PM skills, pre-commit checks, code review - not optional shortcuts
- **MECE for Multi-Tasks**: Independent work parallelize; dependent work sequence

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

### Pre-Commit Validation (MANDATORY)

Before EVERY single commit, run:

```bash
bash .claude/scripts/pre-commit-validation.sh
# Must PASS before committing
```

**Why this is non-negotiable:**
- Catches 80% of code review issues before they're published
- Prevents churn (validation now vs code review later)
- Maintains code quality standards
- Reduces feedback loops

**If validation fails:**
- Fix violations locally
- Re-run validation
- Only commit after passing

**Key patterns the script validates:**
1. Dict-style dataclass access → use `hasattr()`
2. Wrong return types → read implementation first
3. Non-existent imports → verify module exists
4. Wrong constructor params → check class definition
5. Build artifacts → add to `.gitignore`

See: `.claude/rules/code-quality-validation.md` for detailed patterns

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

**Last Updated**: 2026-03-06
**Version**: 2.0.0-alpha.1

## Recent Updates

**2026-03-06: Integrated #610 Retrospective Learnings**
- Added Multi-Task Execution Strategy section with MECE principles
- Enhanced Task Execution with mandatory quality gates (simplify, code-reviewer, pre-commit)
- Updated Workflow Orchestration to emphasize CCPM tracking (not optional)
- Made Pre-Commit Validation the primary workflow (bash script, not manual steps)
- Added verification at system boundaries (don't assume GitHub state)
- Integrated code-reviewer and simplify skill requirements into workflow
- Added red flags for bad task decomposition
- Emphasized accuracy over speed for multi-task work
