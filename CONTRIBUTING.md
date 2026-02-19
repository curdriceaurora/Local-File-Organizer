# Contributing to File Organizer

## Development Environment Setup

### Prerequisites

- **Python 3.9+** (we test against 3.9, 3.10, 3.11, 3.12)
- **Ollama** (for AI model inference)

### Python Version Management (pyenv)

Our CI tests against Python 3.9, 3.10, 3.11, and 3.12. To catch version-specific issues
locally before pushing, install all target versions via [pyenv](https://github.com/pyenv/pyenv):

```bash
# Install pyenv
brew install pyenv          # macOS
curl https://pyenv.run | bash  # Linux

# Install CI-targeted Python versions
pyenv install 3.9.21
pyenv install 3.10.16
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
# Full CI mirror — Python 3.9/3.10/3.11/3.12 (~10 min)
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

---

## What the CI Runs

Our CI has two workflows triggered on PRs to `main`:

| Workflow | File | What it runs |
|----------|------|-------------|
| **CI** | `.github/workflows/ci.yml` | Lint + Python 3.9/3.12 tests |
| **CI Full Matrix** | `.github/workflows/ci-full.yml` | Python 3.9/3.10/3.11/3.12 |

`scripts/test-local-matrix.sh` mirrors the Full Matrix workflow locally.

---

## Common Pitfalls

These are the most frequent causes of CI failures that pass locally:

| Pitfall | Why it happens | How to avoid |
|---------|---------------|--------------|
| `datetime.utcnow()` | Deprecated in 3.12, removed in 3.14 | Use `datetime.now(timezone.utc)` |
| `os.stat().st_birthtime` | macOS-only; Linux raises `AttributeError` | Use platform-aware fallback (see `heuristics.py`) |
| `match` statements | Python 3.10+ only | Use `if/elif` for 3.9 compatibility |
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

```
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
