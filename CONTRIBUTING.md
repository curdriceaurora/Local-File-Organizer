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

**Additional Checks** (via `bash .claude/scripts/pre-commit-validation.sh`):

| Check | Purpose | Catches |
|-------|---------|---------|
| **mypy** | Type safety (strict mode) | Type errors block commit |
| **broken-link-check** | Documentation links | Broken references to files |
| **dict-style access** | Dataclass pattern validation | Dict-style access on dataclasses |
| **mock target validation** | Mock patch targets | Invalid `@patch()` targets |

**Manual Validation**:

```bash
# Run all pre-commit hooks on entire codebase
pre-commit run --all-files

# Run specific hook
pre-commit run ruff-check --all-files
pre-commit run codespell --all-files

# Run full validation script (includes hooks + additional checks)
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

Before pushing changes, run these checks to avoid wasting CI minutes and Copilot Review quota:

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
| **CI** | `.github/workflows/ci.yml` | push to `main`, PRs | Lint + test (Linux 3.11/3.12) + docstring coverage gate |
| **CI Full Matrix** | `.github/workflows/ci-full.yml` | daily (06:00 UTC), manual | Extended platform: macOS + Windows (Python 3.12) |
| **Security** | `.github/workflows/security.yml` | weekly (Monday), PRs | pip-audit + bandit + CodeQL |

**Rule**: each check lives in exactly one workflow.

- `ci.yml` is the *fast-path gate*: runs on every push and PR, covers the primary
  Linux matrix. Coverage, lint, and docstring thresholds live here.
- `ci-full.yml` is the *breadth gate*: runs daily to catch platform-specific regressions
  on macOS and Windows. It does **not** duplicate the Linux matrix.
- `security.yml` owns all security tooling.

`scripts/test-local-matrix.sh` mirrors the Python matrix locally on the host OS.
`act` mirrors the full workflow inside Docker for ubuntu-latest parity.

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
# Run all tests
pytest

# Run with coverage
pytest --cov=file_organizer --cov-report=html

# Run specific markers
pytest -m unit          # Unit tests only
pytest -m "not slow"    # Skip slow tests
pytest -m "not regression"  # Skip regression (matches CI PR behaviour)
```

### Test Markers

| Marker | Purpose |
|--------|---------|
| `@pytest.mark.unit` | Fast unit tests |
| `@pytest.mark.integration` | Integration tests |
| `@pytest.mark.slow` | Long-running tests |
| `@pytest.mark.regression` | Full regression (skipped on CI PRs) |
| `@pytest.mark.ci` | CI pipeline validation |

---

## Pull Requests

1. Create a feature branch from `main`: `git checkout -b feature/description`
2. Make changes with tests
3. Run `./scripts/test-local-matrix.sh --quick` (minimum) or full matrix
4. Run `ruff check src/` for linting
5. Commit with descriptive message
6. Push and open a PR against `main`

PRs trigger both CI workflows automatically. Copilot Review runs on every PR (premium feature),
so catching issues locally saves real money.
