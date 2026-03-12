# Guardrail Workflow

Guardrails exist to turn repeated PR review findings into enforced checks. The
goal is to catch high-confidence problems before review, without creating a
second competing policy engine.

## Canonical Ownership

Each blocking guardrail belongs in exactly one enforced layer:

| Guardrail type | Canonical home | Why |
|----------------|----------------|-----|
| Staged diff and mechanical checks | `.pre-commit-config.yaml` | Fast, deterministic checks on changed files before commit |
| Semantic regressions and contract checks | `tests/ci/` | Python-based assertions are easier to evolve and review than shell heuristics |
| CI-only runtime support | `.github/workflows/ci.yml` | Some guardrails need GitHub permissions or environment variables to behave in PR CI |
| Pre-PR orchestration | `.claude/scripts/pre-commit-validation.sh` | Runs the enforced layers together before push or PR creation |
| Explanatory guidance | `memory/`, `.claude/rules/`, and related docs | Captures lessons and rationale, but should not be the only blocking source |

Pitfall: if a rule only exists in prose or only exists in the shell script, it
will drift. Blocking policy belongs in pre-commit hooks or `tests/ci`.

## Canonical Pre-PR Flow

Run this before opening or updating a PR:

```bash
bash .claude/scripts/pre-commit-validation.sh
```

That command must expand to this canonical command set:

1. `pre-commit validate-config`
2. `pre-commit run --files <changed-files>` when a diff exists
3. `pre-commit run --all-files` when there is no diff
4. `pytest tests/ci -q --no-cov --override-ini="addopts="`

Why this split:
- `pre-commit` is the staged-file gate
- `tests/ci` is the semantic gate
- the shell script is just the orchestrator

## How to Add a New Guardrail

Add a new rule to the narrowest layer that can enforce it cleanly:

1. Use `.pre-commit-config.yaml` for changed-file, grep-like, formatter, lint, or focused test gates.
2. Use `tests/ci/` for AST checks, repository-wide assertions, workflow contracts, or docs/code alignment.
3. Update `.github/workflows/ci.yml` when a CI-only guardrail needs runtime support such as `GITHUB_TOKEN` or `pull-requests: read`.
4. Update documentation after the enforcement layer exists, not before.

Do not add new blocking policy directly to `.claude/scripts/pre-commit-validation.sh`.

## CLI Contract Test Conventions

Typer and Rich render help text differently across terminals and CI. For CLI
contract tests:

- Prefer `result.output` over `result.stdout`
- Normalize rendered help before asserting exact content
- Assert semantic fragments unless exact formatting is part of the contract

Example:

```python
result = runner.invoke(app, ["organize", "--help"])
assert result.exit_code == 0
rendered_help = _rendered_text(result.output)
assert "--no-prefetch" in rendered_help
```

Pitfall: direct assertions on styled help output can pass locally and fail in
GitHub Actions because Rich changes wrapping and ANSI rendering.

## GitHub-Environment Branching Helpers

Guardrail code that branches on `GITHUB_*` variables is CI-first code. Treat it
as such:

- Test both local mode and GitHub PR mode
- Cover the fallback path explicitly
- Avoid assuming a full git history or a specific merge-parent layout
- Prefer GitHub-provided PR context when the question is really about PR files

Examples of CI-only runtime support:
- `pull-requests: read` permission for PR file lookups
- `GITHUB_TOKEN` in workflow steps that call GitHub APIs

## Workflow Support Mapping

CI workflow configuration is part of the guardrail system, not an incidental
detail:

- `.github/workflows/ci.yml` must expose the permissions and environment needed
  by CI-only guardrails
- `tests/ci/test_workflows.py` should lock in those assumptions
- if a guardrail needs workflow support, document the ownership in the same PR

This keeps reviewers from having to infer whether a failure is in the rule
itself or in the CI runtime that the rule depends on.
