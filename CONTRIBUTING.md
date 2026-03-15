# Contributing to File Organizer

## Development Environment Setup

### Prerequisites

- **Python 3.11+** (we test against 3.11, 3.12)
- **Ollama** (for AI model inference)

### Python Version Management (pyenv)

Our CI tests against Python 3.11 and 3.12. To catch version-specific issues
locally before pushing, install all target versions via [pyenv](https://github.com/pyenv/pyenv):

```bash
# Install pyenv
brew install pyenv          # macOS
curl https://pyenv.run | bash  # Linux

# Install CI-targeted Python versions
pyenv install 3.11.11
pyenv install 3.12.8
```

### Install the Package

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with development dependencies
pip install -e ".[dev]"

# Verify
file-organizer --version
```

### Pre-Commit Hooks (Automatic Validation)

This project uses automated pre-commit validation to catch common issues before commits:

```bash
# Install git pre-commit hooks (one-time setup after first time)
pre-commit install

# Now on every commit, these hooks automatically run:
```

**Pre-Commit Hooks** (run automatically on `git commit`):

| Hook | Purpose | Catches |
|------|---------|---------|
| **ruff-check** | Python linting (strict, includes RUF100) | Style, imports, stale `# noqa` comments |
| **codespell** | Spelling consistency | Typos, spelling inconsistencies |
| **absolute-path-check** | Hardcoded absolute paths | `/Users/`, `/home/`, `C:\Users\` paths |
| **pytest** (multiple) | CI guardrails, web UI, websocket tests | Test failures block commit |

**Pre-PR Orchestration** (via `bash .claude/scripts/pre-commit-validation.sh`):

| Layer | Canonical owner | Purpose |
|-------|-----------------|---------|
| **Staged-file guardrails** | `.pre-commit-config.yaml` | Mechanical checks, focused pytest gates, and changed-file validation |
| **Semantic guardrails** | `tests/ci/` | Behavior, contract, and review-regression checks |
| **CI runtime support** | `.github/workflows/ci.yml` | Permissions and environment required by CI-only guardrails |
| **Pre-PR orchestration** | `.claude/scripts/pre-commit-validation.sh` | Runs the enforced layers above before push/PR |
| **Reference guidance** | anti-pattern docs under `memory/` and `.claude/rules/` | Explains why a guard exists; not a blocking policy source |

**Manual Validation**:

```bash
# Run all pre-commit hooks on entire codebase
pre-commit run --all-files

# Run specific hook
pre-commit run ruff-check --all-files
pre-commit run codespell --all-files

# Run the canonical pre-PR guardrail orchestrator
bash .claude/scripts/pre-commit-validation.sh
```

**Skipping Hooks** (only if necessary):

```bash
# Commit bypassing pre-commit (NOT recommended)
git commit --no-verify

# But hooks will still run in CI, so issues will be caught there
```

---

## Pre-Push Checklist

**MANDATORY**: Before EVERY push, run the canonical pre-PR guardrail orchestrator:

```bash
bash .claude/scripts/pre-commit-validation.sh
# Must pass (exit code 0) before proceeding to push
```

This command orchestrates the real enforcement layers:
- `pre-commit validate-config`
- `pre-commit run --files ...` for changed files, or `--all-files` when nothing is staged
- `pytest tests/ci -q --no-cov --override-ini="addopts="`

For first-wave review-regression CI parity, you can run the same audit command
used by the standing enforcement checks:

```bash
python3 -m file_organizer.review_regressions.audit \
  --root . \
  --detector file_organizer.review_regressions.security:SECURITY_DETECTORS \
  --detector file_organizer.review_regressions.correctness:CORRECTNESS_DETECTORS \
  --detector file_organizer.review_regressions.test_quality:TEST_QUALITY_DETECTORS \
  --fail-on-findings
```

It is intentionally not a second policy engine. If you need a new blocking rule,
add it to `.pre-commit-config.yaml` or `tests/ci`, then let this script invoke it.

**Do not push if validation fails.** Fix violations and re-run until it passes.

---

### Quick Check (recommended before every push)

```bash
# Fastest — tests on Python 3.12 only (~2 min)
./scripts/test-local-matrix.sh --quick
```

### Full Matrix (recommended before opening a PR)

```bash
# Full CI mirror — Python 3.11/3.12 (~10 min)
./scripts/test-local-matrix.sh
```

### Individual Checks

```bash
# Python matrix only
./scripts/test-local-matrix.sh --python

# Lint only
ruff check src/

# Type check
mypy src/file_organizer/ --strict
```

### Full CI in Docker with `act` (ubuntu-latest parity)

[`act`](https://github.com/nektos/act) runs the actual `.github/workflows/*.yml` files inside
Docker containers that mirror `ubuntu-latest`. This catches platform-specific bugs that
`test-local-matrix.sh` misses (e.g., `st_birthtime` on macOS vs `st_mtime` on Linux).

**Prerequisites**: Docker Desktop running locally (~2 GB disk for the ubuntu-latest image on
first run).

```bash
# Install act
brew install act            # macOS
curl -s https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash  # Linux
choco install act-cli       # Windows
```

**Usage**:

```bash
# Run the full ci-full.yml matrix (simulates the daily cron schedule)
act schedule

# Same, but simulate a manual workflow_dispatch trigger
act workflow_dispatch

# Run just the Python test matrix
act schedule -j test-matrix

# Run the fast CI (ci.yml — simulates a push to main)
act push

# Run CI as if a PR was opened
act pull_request
```

The `.actrc` file in the project root pins the Docker image and architecture automatically.

**`act` vs `test-local-matrix.sh`**:

| | `act` | `test-local-matrix.sh` |
|--|-------|------------------------|
| OS parity | ubuntu-latest in Docker | Host OS (macOS/Windows) |
| Workflow sync | Uses actual YAML — stays in sync | Must be updated manually |
| Speed | Slower (Docker overhead) | Faster (native execution) |
| Dependencies | Docker Desktop required | pyenv only |
| Offline | Needs Docker images cached | Works fully offline |

---

## What the CI Runs

### Workflow ownership

| Workflow | File | Triggers | What it runs |
|----------|------|----------|-------------|
| **CI** | `.github/workflows/ci.yml` | push to `main`, PRs | Lint + non-benchmark tests (Linux 3.11/3.12), benchmark-only lane (no xdist), docstring coverage, Rust desktop checks for desktop-related changes |
| **CI Full Matrix** | `.github/workflows/ci-full.yml` | daily (06:00 UTC), manual | Extended platform: macOS + Windows (Python 3.12) |
| **Security** | `.github/workflows/security.yml` | weekly (Monday), PRs | pip-audit + bandit + CodeQL |

**Rule**: each check lives in exactly one workflow.

- `ci.yml` is the *fast-path gate*: runs on every push and PR, covers the primary
  Linux matrix. Coverage, lint, and docstring thresholds live here.
- `ci.yml` test split:
  - non-benchmark lane uses xdist (`-n=auto`) and excludes benchmark tests
  - benchmark-only lane runs without xdist (`--benchmark-only`)
  - on PRs, benchmark lane runs when benchmark surfaces change; on `main`, it runs as a dedicated lane
- `ci-full.yml` is the *breadth gate*: runs daily to catch platform-specific regressions
  on macOS and Windows. It does **not** duplicate the Linux matrix.
- `security.yml` owns all security tooling.

`scripts/test-local-matrix.sh` mirrors the Python matrix locally on the host OS.
`act` mirrors the full workflow inside Docker for ubuntu-latest parity.

## Guardrail Ownership

The canonical ownership rules and examples live in
[Developer Guardrails](docs/developer/guardrails.md). Use
`.pre-commit-config.yaml` for staged-file checks, `tests/ci/` for semantic
guardrails, `.github/workflows/ci.yml` for CI-only runtime support, and
`.claude/scripts/pre-commit-validation.sh` only as the pre-PR orchestrator.

---

## Common Pitfalls

These are the most frequent causes of CI failures that pass locally:

| Pitfall | Why it happens | How to avoid |
|---------|---------------|--------------|
| `datetime.utcnow()` | Deprecated in 3.12, removed in 3.14 | Use `datetime.now(timezone.utc)` |
| `os.stat().st_birthtime` | macOS-only; Linux raises `AttributeError` | Use platform-aware fallback (see `heuristics.py`) |
| `X \| Y` union types | Python 3.10+ only | Use `Union[X, Y]` or `Optional[X]` |
| `tomllib` | Python 3.11+ only | Use `tomli` backport or conditional import |

---

## Code Style

- **Formatter**: Black (line length 100)
- **Import sorting**: isort
- **Linter**: Ruff (strict)
- **Type checking**: mypy strict mode
- **Docstrings**: Google style

### Commit Messages

```text
<type>(<scope>): <subject>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example: `fix(history): replace deprecated datetime.utcnow() with timezone-aware alternative`

---

## Testing

```bash
# Run all tests (full suite)
pytest

# Run with coverage
pytest --cov=file_organizer --cov-report=html

# Run specific test subsets
pytest -m unit           # Unit tests only
pytest -m smoke          # Fast smoke suite (~3.5s) — local pre-commit validation
pytest -m ci             # CI validation tests — PR check suite
pytest -m "not slow"     # Skip slow tests for faster local development
pytest -m "not regression"  # Full suite without regression (PR validation)
pytest tests/            # Full suite including regression tests (complete local/CI run)
```

### Test Markers

| Marker | Purpose | When Used |
|--------|---------|-----------|
| `@pytest.mark.unit` | Fast unit tests | Both local and CI |
| `@pytest.mark.smoke` | Critical-path tests for pre-commit (~3.5s, deterministic, fast) | Local pre-commit validation |
| `@pytest.mark.ci` | PR validation tests | GitHub Actions PR checks |
| `@pytest.mark.integration` | Integration tests (real services, mocked HTTP) | Main branch CI only |
| `@pytest.mark.regression` | Full regression suite | Complete CI runs, manual testing |
| `@pytest.mark.slow` | Long-running tests | Skipped in pre-commit and PR CI |

### Integration Tests

Integration tests live in `tests/integration/` and exercise real service wiring with only external HTTP mocked. Use the shared fixtures from `tests/integration/conftest.py`:

```python
@pytest.mark.integration
def test_organizer_creates_output(
    stub_all_models,       # Stubs both text + vision model init and generate
    stub_nltk,             # No-ops NLTK data download
    integration_source_dir,  # Temp dir with .txt, .csv, .md files
    integration_output_dir,  # Clean temp output dir
):
    from tests.integration.conftest import make_text_config, make_vision_config

    org = FileOrganizer(
        text_model_config=make_text_config(),
        vision_model_config=make_vision_config(),
        dry_run=False,
    )
    result = org.organize(
        input_path=str(integration_source_dir),
        output_path=str(integration_output_dir),
    )
    assert result.processed_files == 3
```

Integration tests run on main branch pushes only (`pytest -m integration`), not on every PR. See [Testing Guide](docs/developer/testing.md#integration-testing) for the full fixture reference.

---

## Quality Gates

Before committing code, this project enforces three quality gates (in order). **Note**: The `/simplify` and `/code-reviewer` commands are Claude Code-specific tools. For contributors not using Claude Code, follow the automated validation script only.

1. **Pre-Commit Validation** (`bash .claude/scripts/pre-commit-validation.sh`)
   - Lint, format, type-check, test, validate patterns
   - Must PASS before committing
   - Prevents CI failures due to local issues
   - **Fast**: ~30 seconds (fail fast on cheap checks)

2. **Code Review** (`/code-reviewer` skill — Claude Code users only)
   - Validate implementation against CLAUDE.md standards
   - Check for architectural and design issues
   - Verify test logic and assertions
   - **Medium**: 30-60 seconds

3. **Code Simplification** (`/simplify` skill — Claude Code users only, optional)
   - Review code for efficiency and reuse
   - Suggest optimizations and improvements
   - Run after significant code changes (>50 lines)
   - **Expensive**: 1-5 minutes (improvement suggestions, not required)

**Order matters**: Pre-Commit (required) → Code Review (Claude Code only) → Simplify (Claude Code only, optional) → Commit

**For non-Claude-Code contributors**: Run only step 1 (pre-commit validation script). GitHub CI enforces additional checks.

For details, see `.claude/rules/code-quality-validation.md` and `.claude/rules/development-guidelines.md`.

---

## Pull Requests

1. Create a feature branch from `main`: `git checkout -b feature/description`
2. Make changes with tests
3. Run quality gates (in order):
   - `bash .claude/scripts/pre-commit-validation.sh` (required, all contributors)
   - `/code-reviewer` (Claude Code users only: validate design and logic)
   - `/simplify` (Claude Code users only: optional if >50 lines of code changes)
4. Commit with descriptive message following conventional commits
5. Push and open a PR against `main`

PRs trigger both CI workflows automatically. Copilot Review runs on every PR (premium feature),
so catching issues locally via quality gates saves time and money.

---

## PR Review Response Protocol

If reviewers request changes:

1. **Extract all findings upfront** (don't iterate one at a time)
2. **Verify each finding** against current code
3. **Apply all fixes in one local pass** (no pushing between fixes)
4. **Run quality gates** (pre-commit → code-reviewer → simplify)
5. **Commit and push once** with comprehensive message
6. **Don't monitor iteratively** — trust your quality gates did their job

This single-pass approach prevents review churn and keeps PR history clean.

See `.claude/rules/pr-review-response-protocol.md` for full details.
