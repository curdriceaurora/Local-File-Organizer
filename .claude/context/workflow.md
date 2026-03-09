---
created: 2026-03-08T23:57:34Z
last_updated: 2026-03-08T23:57:34Z
version: 1.0
author: Claude Code PM System
---

# Workflow & Rules Reference

This file bridges context (what the project is) with rules (how to work on it).
All rules live in `.claude/rules/`. Load the relevant ones before each task.

## Rules Index — Load Before Starting Work

### Session Start (Every Session)

1. Read `memory/MEMORY.md` — current task state, lessons, active branches
2. Invoke `Skill("context:prime")` — load all context files
3. Read `.claude/agents/` relevant agent definitions
4. Invoke `Skill("pm:issue-start", args="<N>")` — register CCPM tracking

### Before Writing Any Code or Tests

| Situation | Rule File to Read |
|-----------|------------------|
| Writing feature code | `.claude/rules/feature-generation-patterns.md` (F1-F9 anti-patterns) |
| Writing tests | `.claude/rules/test-execution.md`, `.claude/rules/quick-validation-checklist.md` |
| Writing CI config | `.claude/rules/ci-generation-patterns.md` (C1-C6 anti-patterns) |
| Writing documentation | `.claude/rules/docs-generation-patterns.md`, `.claude/rules/documentation-generation-checklist.md` |
| Using GitHub paths/files | `.claude/rules/path-standards.md` (no absolute paths) |
| Creating issues/PRs | `.claude/rules/github-operations.md`, `.claude/rules/github-issue-ccpm-integration.md` |

### Before Every Commit

Run through **all** of these in order:

1. **`.claude/rules/quick-validation-checklist.md`** — G1 (no `/tmp/`), G2 (no f-strings in logger), G4 (no unused code), G5 (test names match assertions)
2. **Stage files**, then run: `bash .claude/scripts/pre-commit-validation.sh`
3. Invoke `Agent(subagent_type="code-reviewer")` for major changes
4. Only then: `git commit`

### PR Review Process

Follow `.claude/rules/pr-workflow-master.md` as the entry point. It links to:

| Step | Rule File |
|------|-----------|
| State machine | `.claude/rules/pr-workflow-state-machine.md` |
| Review response | `.claude/rules/pr-review-response-protocol.md` |
| Monitoring | `.claude/rules/pr-monitoring-protocol.md` |
| Merge troubleshooting | `.claude/rules/pr-merge-troubleshooting.md` |
| Industry conformance | `.claude/rules/pr-workflow-conformance.md` |

### CCPM Project Management

All issue/epic operations **must** use PM skills, never raw `gh` commands:

| Task | Skill |
|------|-------|
| Start work | `Skill("pm:issue-start", args="<N>")` |
| Sync progress | `Skill("pm:issue-sync", args="<N>")` |
| Close issue | `Skill("pm:issue-close", args="<N>")` |

See: `.claude/rules/pm-skills-mandatory.md`, `.claude/rules/github-operations.md`

### Code Quality Anti-Pattern Rules

These are the patterns that consistently surface in PR review — read before generating code:

| Pattern Category | Rule File | Key Anti-Patterns |
|-----------------|-----------|------------------|
| Feature code | `feature-generation-patterns.md` | F1 error handling, F2 type annotations, F3 thread safety, F4 security, F5 hardcoded values |
| Test code | `quick-validation-checklist.md` | G1 absolute paths, G2 f-strings in logger, G4 unused code, G5 test name accuracy |
| CI / GitHub Actions | `ci-generation-patterns.md` | C4 wrong coverage %, C2 wrong trigger, C3 lru_cache with env vars |
| Documentation | `docs-generation-patterns.md` | D5 markdown format (highest frequency!), D1 inaccurate claims, D6 contradictions |

### Git & Branch Rules

- Branch naming: `feature/issue-{N}-{description}` or `fix/issue-{N}-{description}`
- Never commit to `main` directly — see `.claude/rules/main-branch-protection.md`
- Branch operations: `.claude/rules/branch-operations.md`
- Worktree operations: `.claude/rules/worktree-operations.md`

### Automation Scripts

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `.claude/scripts/pre-commit-validation.sh` | Full validation (lint, format, types, tests) | Before every commit |
| `.claude/scripts/resolve-pr-threads.sh` | Resolve GitHub PR review threads | After pushing review fixes |
| `.claude/scripts/test-and-log.sh` | Run tests with full log capture | Via `testing:run` skill |

## Quick Decision Tree

```
Starting work?
  → Read MEMORY.md + context:prime + load rules + pm:issue-start

Writing code?
  → Read feature-generation-patterns.md FIRST
  → Write code
  → Run quick-validation-checklist.md checks
  → Stage + pre-commit-validation.sh
  → Commit

Writing tests?
  → Read test-execution.md + quick-validation-checklist.md FIRST
  → Write tests using Agent(subagent_type="test-runner") for execution
  → Run quality checks
  → Commit

Responding to PR review?
  → Read pr-workflow-master.md (entry point for all PR work)
  → Follow 6-step pr-review-response-protocol.md
  → Resolve threads with resolve-pr-threads.sh --replies replies.json

Done with task?
  → pm:issue-sync + pm:issue-close
  → context:update
```
