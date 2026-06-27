# Development Guidelines

## Code Style

- **Black** formatting (line length 100), **isort** imports, **Ruff** lint (strict), **mypy** strict types
- Enforced via `.pre-commit-config.yaml` and `.claude/scripts/pre-commit-validation.sh`

## Naming

| Type | Convention |
|------|-----------|
| Files/modules | `snake_case.py` |
| Classes | `PascalCase` |
| Functions/variables | `snake_case` |
| Constants | `UPPER_SNAKE_CASE` |
| Private | `_leading_underscore` |

## Commit Messages

Format: `<type>(<scope>): <subject>` where type is `feat | fix | docs | style | refactor | test | chore`.

Body should explain *why*, not just *what*.

## Pre-Commit Validation (mandatory before every commit)

```bash
bash .claude/scripts/pre-commit-validation.sh
```

If it fails: fix locally, re-run, only commit after passing. Never skip with `--no-verify`.

### On shared feature branches (multi-agent or multi-session work)

Always synchronise with the remote **before** running pre-commit and committing:

```bash
git pull --rebase origin <branch>   # ← sync first
# make changes
bash .claude/scripts/pre-commit-validation.sh
git add <files> && git commit && git push
```

**Why this matters:** pre-commit validates the local working tree. If another agent has pushed to the same branch since your last pull, the remote may contain a different version of a file than what pre-commit sees locally. Validating a stale local copy gives a false green — CI then fails on the actual remote content. Pull before you validate, not after.

## Pre-Commit Hooks (`.pre-commit-config.yaml`)

- `ruff check` — lint
- `pytest` — websocket validations, CI guardrails, web UI, non-regression tests
- `codespell` — spell check `src/` + `docs/`
- `absolute-path-check` — blocks absolute paths like `/Users/…`
- `pymarkdown` — markdown lint per `.pymarkdown.json`

## Quality Gate Order

1. Write code following patterns in `.claude/patterns/` (use `/audit` skill to verify)
2. `bash .claude/scripts/pre-commit-validation.sh` (local)
3. `/code-reviewer` (design review)
4. Commit (hooks run automatically)

## References

- Config: `pyproject.toml`, `.pre-commit-config.yaml`, `.pymarkdown.json`
- Anti-patterns: `.claude/patterns/feature-generation-patterns.md` (F1-F10), `.claude/patterns/test-generation-patterns.md` (T1-T10), etc.
- Detailed validation: `.claude/rules/code-quality-validation.md`

---
**Last Updated**: 2026-04-11
