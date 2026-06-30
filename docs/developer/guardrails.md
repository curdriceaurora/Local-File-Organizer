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
| Pre-PR orchestration | `scripts/dev/pre-commit-validation.sh` | Runs the enforced layers together before push or PR creation |

Pitfall: if a rule only exists in prose or only exists in the shell script, it
will drift. Blocking policy belongs in pre-commit hooks or `tests/ci`.

## Canonical Pre-PR Flow

Run this before opening or updating a PR:

```bash
bash scripts/dev/pre-commit-validation.sh
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

Do not add new blocking policy directly to `scripts/dev/pre-commit-validation.sh`.

The MECE backlog for review anti-patterns that should become remediation and
enforcement issues lives in
[`guardrail-promotion-backlog.md`](guardrail-promotion-backlog.md).

## Blocking Guardrails

Once a rail's backlog reaches zero, flip its registry mode to `enforce`.
Blocking rails run through the `ci-rails` pre-commit hook and
`scripts/ci/ci_rails.py`, so local pre-commit and CI both fail on new
violations. Re-run the rail directly to verify it exits 0 before promoting
it:

```bash
python scripts/ci/guardrails/check_called_attribute_assertion.py
```

### Importable Guardrail Modules

Project-owned CI guardrail scripts live under `scripts/ci/guardrails/` and are
importable as normal Python modules from `scripts.ci.guardrails`. Keep each
module runnable as a script for pre-commit and CI, but write tests against the
imported module:

```python
from scripts.ci.guardrails import check_example_guardrail


def test_example(tmp_path: Path) -> None:
    assert check_example_guardrail.check_file(tmp_path / "subject.py") == []
```

Avoid adding new `importlib.util.spec_from_file_location` loaders for
`scripts/ci/guardrails` modules.

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

## Template JavaScript Rule Index

Issue `#1407` adds a semantic template check for inline JavaScript contexts.
The detector lives in `src/file_organizer/review_regressions/template_js.py`
and is exercised by `tests/unit/review_regressions/test_template_js_detectors.py`
plus the repo-wide CI enforcement test.

| Rule ID | Canonical home | What it flags |
|---------|----------------|---------------|
| `unsafe-js-interpolation` | `tests/ci/test_first_wave_repo_enforcement.py` | Jinja interpolation inside `<script>` blocks or inline `on*=` handlers unless the value is emitted as a direct `tojson` JS value outside quotes/backticks |

Safe patterns:
- `{{ value|tojson }}` used directly as a JavaScript value
- inert `data-*` attributes plus external JS that reads `dataset`
- static inline handlers with no template interpolation

## T10 Predicate Negative-Case Rule Index

Issues `#930` and `#931` add two enforcement layers for the T10 pattern: every
`_is_*`/`_has_*`/`_find_*` predicate in detector modules must have a paired
negative test case (`assert not predicate(...)`).

| Enforcement layer | Location | When it fires |
|-------------------|----------|---------------|
| Pre-commit hook | `.pre-commit-config.yaml` → `predicate-negative-coverage` | When detector modules or their test files are staged |
| CI backstop | `tests/ci/test_predicate_negative_coverage.py` | On every CI run (full scan) |

Shared logic lives in `scripts/ci/guardrails/check_predicate_negative_coverage.py`.
The CI test imports it as
`scripts.ci.guardrails.check_predicate_negative_coverage`; the pre-commit hook
runs the same file directly. Update the script when new detector modules are
added.

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

## SafeDir-Required Rule (WP-6.1)

Issue `#1351` adds the `safedir-required` CI rail, which flags raw `open()`,
`Path.open()`, and `shutil` copy/move calls in production source. The rail is
declared in `scripts/ci/rails.toml` and is run by the `ci-rails` pre-commit
hook and by `scripts/ci/ci_rails.py` in CI.

The rail is now **enforced** — it blocks commits and CI runs when violations
are found.

### What is flagged

| Pattern | Message |
|---------|---------|
| `open(path, ...)` | `raw open() call` |
| `path.open(...)` on a `Path` or similar object | `raw Path.open() call` |
| `shutil.copy2`, `shutil.move`, `shutil.copytree`, etc. | `raw shutil.<op>() call` |

### What is NOT flagged

Library-specific `.open()` calls on known non-filesystem namespaces are
excluded to avoid detector overreach:

| Namespace | Reason excluded |
|-----------|----------------|
| `os.open()` | Returns a low-level file descriptor (int), not a Python file object |
| `Image.open()` | PIL/Pillow image decode call |
| `fitz.open()` | PyMuPDF document open |
| `tarfile.open()` | stdlib tar archive open |
| `tokenize.open()` | stdlib encoding-aware source reader |
| `aiofiles.open()` | Async file I/O library |
| `zipfile.open()` | stdlib ZipFile method |

### Inline exemptions

For accepted exceptions (proc filesystem reads, undo-journal primitives, plugin
installers, etc.), add an inline exemption with a brief reason:

```python
with open("/proc/meminfo") as f:  # noqa: safedir-required  # read-only Linux proc FS
    ...

shutil.copy2(src, dst)  # noqa: safedir-required  # updater — src/dst are pre-validated
```

Run the rail directly to verify it exits 0:

```bash
python scripts/ci/guardrails/check_safedir_required.py
```

The guardrail module is importable for tests:

```python
from scripts.ci.guardrails import check_safedir_required

def test_my_check(tmp_path: Path) -> None:
    assert check_safedir_required.check_file(tmp_path / "subject.py") == []
```

## Atomic-Write Rule (WP-6.1)

Issue `#1351` adds the `atomic-write` CI rail, which flags raw file writes in
Python modules under `src/file_organizer/`. The rail is declared in
`scripts/ci/rails.toml`, runs via
`scripts/ci/guardrails/check_atomic_write.py`, and is enforced by the CI-rails
runner and pre-commit hook.

The rail is now **enforced** — commits and CI runs fail when violations are
found.

Prefer these helpers instead of raw writes:

- `atomic_write_text()` for JSON/YAML/text persistence
- `atomic_write_bytes()` for in-memory binary payloads
- `atomic_write_with()` for streaming writers like `pickle.dump()`
- `append_durable()` for append-only logs

Run the rail directly to verify it exits 0:

```bash
python scripts/ci/guardrails/check_atomic_write.py
```

## Test-Separator-Paths Rule (WP-6.2)

Issue `#1368` promotes `test-separator-paths` to an enforced CI rail. The rail
is declared in `scripts/ci/rails.toml`, runs via
`scripts/ci/guardrails/check_test_separator_paths.py`, and is executed by both
the `ci-rails` pre-commit hook and `scripts/ci/ci_rails.py` in CI.

The rail is now **enforced** — commits and CI runs fail when violations are
found.

### What is flagged

- `Path("foo/bar")`
- `Path("foo\\bar")`

Prefer segment composition with the division operator:

```python
Path("foo") / "bar"
```

### Inline exemptions

Use only targeted, line-local exemptions for true edge cases:

```python
value = Path("payload/that/must/stay/literal")  # noqa: test-separator-paths
```

Run the rail directly to verify it exits 0:

```bash
python scripts/ci/guardrails/check_test_separator_paths.py
```

## Pytest-Raises-Hygiene Rule (WP-6.2)

Issue `#1369` promotes `pytest-raises-hygiene` to an enforced CI rail. The rail
is declared in `scripts/ci/rails.toml`, runs via
`scripts/ci/guardrails/check_pytest_raises_hygiene.py`, and is executed by both
the `ci-rails` pre-commit hook and `scripts/ci/ci_rails.py` in CI.

The rail is now **enforced** — commits and CI runs fail when violations are
found.

Prefer `pytest.raises(..., match=...)` whenever the exception message is part
of the contract. Use `# noqa: pytest-raises-hygiene` only for cases that are
explicitly message-agnostic.

Run the rail directly to verify it exits 0:

```bash
python scripts/ci/guardrails/check_pytest_raises_hygiene.py
```

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
