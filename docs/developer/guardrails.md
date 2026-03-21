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
2. `pre-commit run --all-files`
3. `pytest tests/ci -q --no-cov --override-ini="addopts="`

Why this split:
- `pre-commit` is the staged-file gate — `--all-files` ensures local and CI run the same hooks
- `tests/ci` is the semantic gate
- the shell script is just the orchestrator

## How to Add a New Guardrail

Add a new rule to the narrowest layer that can enforce it cleanly:

1. Use `.pre-commit-config.yaml` for changed-file, grep-like, formatter, lint, or focused test gates.
2. Use `tests/ci/` for AST checks, repository-wide assertions, workflow contracts, or docs/code alignment.
3. Update `.github/workflows/ci.yml` when a CI-only guardrail needs runtime support such as `GITHUB_TOKEN` or `pull-requests: read`.
4. Update documentation after the enforcement layer exists, not before.

Do not add new blocking policy directly to `.claude/scripts/pre-commit-validation.sh`.

## API Compatibility Rule Index

Issue `#813` adds allowlisted public-signature compatibility checks. These are
semantic checks and therefore belong in CI tests, not shell-script heuristics.

| Rule ID | Canonical enforced layer | Why this home |
|---------|--------------------------|---------------|
| `legacy-positional-prefix-changed` | `tests/ci/test_api_compat_guardrails.py` | Protects positional-call compatibility on allowlisted public callables |
| `new-optional-param-must-be-keyword-only` | `tests/ci/test_api_compat_guardrails.py` | Prevents accidental API drift from newly optional positional parameters |
| `allowlisted-callable-missing` | `tests/ci/test_api_compat_guardrails.py` | Fails fast when a tracked public API surface is renamed or removed without contract updates |

Implementation detail:
- Detector implementation lives in `src/file_organizer/review_regressions/api_compat.py`.
- Deterministic positive/safe proofs live in `tests/unit/review_regressions/test_api_compat_detectors.py`.

### Custom API-Compat Contracts

When defining custom allowlists, import from the detector module directly:

```python
from pathlib import Path

from file_organizer.review_regressions.api_compat import (
    PublicApiCompatibilityDetector,
    PublicCallableContract,
)

custom_detector = PublicApiCompatibilityDetector(
    contracts=(
        PublicCallableContract(
            path=Path("src/file_organizer/core/organizer.py"),
            qualname="FileOrganizer.__init__",
            legacy_positional_params=("text_model_config", "vision_model_config"),
        ),
    )
)
```

Why direct module import:
- avoids ambiguity between pack-level exports and detector-specific types
- keeps custom-contract code aligned with the detector's canonical module

## Memory Lifecycle Rule Index

Issue `#803` adds buffer/memory lifecycle regression checks. These are semantic
invariants and therefore belong in CI tests, not shell-script heuristics.

| Rule ID | Canonical enforced layer | Why this home |
|---------|--------------------------|---------------|
| `pooled-buffer-ownership-via-length` | `tests/ci/test_memory_lifecycle_guardrails.py` | Prevents ownership-state inference from `len(buffer)` in pool code paths |
| `eager-buffer-pool-allocation` | `tests/ci/test_memory_lifecycle_guardrails.py` | Blocks eager `BufferPool()` creation in `__init__` before context is available |
| `absolute-rss-in-batch-feedback` | `tests/ci/test_memory_lifecycle_guardrails.py` | Enforces RSS delta usage in feedback loops instead of raw absolute RSS |
| `legacy-acquire-release-without-consume` | `tests/ci/test_memory_lifecycle_guardrails.py` | Catches no-op acquire/release sequences that indicate legacy dead paths |

Implementation detail:
- Detector implementation lives in `src/file_organizer/review_regressions/memory_lifecycle.py`.
- Deterministic positive/safe proofs live in `tests/unit/review_regressions/test_memory_lifecycle_detectors.py`.

## Search Guardrail Rule Index

Issue `#869` adds corpus-safety checks for the search service. These are
AST-based semantic checks and therefore belong in CI tests, not shell-script
heuristics.

| Rule ID | Canonical enforced layer | Why this home |
|---------|--------------------------|---------------|
| `S1:symlink-filter(is_symlink())` | `tests/ci/test_search_code_quality.py` | Prevents symlink traversal into untrusted targets such as `/etc/passwd` or `~/.ssh/` |
| `S2:hidden-file-filter(startswith("."))` | `tests/ci/test_search_code_quality.py` | Prevents indexing of `.git`, `.env`, `.ssh/authorized_keys`, and other hidden paths |

Implementation detail:
- Guardrail logic lives in `tests/ci/test_search_code_quality.py` (function `_find_unguarded_traversals`).
- Detection uses AST call-node matching scoped to each function's own body — docstrings and comments cannot produce false positives.
- Rule definitions and fix examples live in `.claude/rules/search-generation-patterns.md` patterns S1 and S2.

## T10 Predicate Negative-Case Rule Index

Issues `#930` and `#931` add two enforcement layers for the T10 pattern: every
`_is_*`/`_has_*`/`_find_*` predicate in detector modules must have a paired
negative test case (`assert not predicate(...)`).

| Enforcement layer | Location | When it fires |
|-------------------|----------|---------------|
| Pre-commit hook | `.pre-commit-config.yaml` → `predicate-negative-coverage` | When detector modules or their test files are staged |
| CI backstop | `tests/ci/test_predicate_negative_coverage.py` | On every CI run (full scan) |

Shared logic lives in `.claude/scripts/check_predicate_negative_coverage.py`.
The CI test imports from this script via `importlib`; the pre-commit hook runs
it directly.  Update the script when new detector modules are added.

| Detector module | Test file | Module stem in `_MODULE_TO_TEST` |
|-----------------|-----------|----------------------------------|
| `correctness.py` | `test_correctness_detectors.py` | `correctness` |
| `security.py` | `test_security_detectors.py` | `security` |
| `memory_lifecycle.py` | `test_memory_lifecycle_detectors.py` | `memory_lifecycle` |
| `test_quality.py` | `test_test_quality_detectors.py` | `test_quality` |
| `api_compat.py` | `test_api_compat_detectors.py` | `api_compat` |

To add a new detector module: add its entry to `_MODULE_TO_TEST` in the script,
add `assert not predicate(...)` calls to the test file for every new predicate,
then verify `pre-commit run predicate-negative-coverage` and
`pytest tests/ci/test_predicate_negative_coverage.py` both pass.

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
