# Python Version Migration Guide

This document describes the changes made to support Python 3.9+ and how to run
the project across multiple Python versions.

## What Changed

### `from __future__ import annotations`

Every Python module in the project now starts with:

```python
from __future__ import annotations
```

This import, available since Python 3.7, defers evaluation of type annotations
so that newer syntax such as `X | Y` (PEP 604, Python 3.10+) and built-in
generic types like `list[str]` (PEP 585, Python 3.9+) can be used as
annotations on Python 3.9 without raising `TypeError` at import time.

**Before (required Python 3.10+):**

```python
def process(path: str | None) -> dict[str, list[int]]:
    ...
```

**After (works on Python 3.9+):**

```python
from __future__ import annotations

def process(path: str | None) -> dict[str, list[int]]:
    ...
```

Annotations are stored as strings and only resolved when explicitly inspected
(e.g., via `typing.get_type_hints()`). The runtime never evaluates `str | None`
on Python 3.9, so no `TypeError` occurs.

### StrEnum Backport

Python 3.11 introduced `enum.StrEnum`. The project provides a transparent
backport in `file_organizer/_compat.py`:

```python
from file_organizer._compat import StrEnum

class ProcessorType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
```

On Python 3.11+, this re-exports the stdlib `StrEnum`. On Python 3.9-3.10, a
polyfill class is used that inherits from both `str` and `Enum`, providing the
same behavior:

- Members compare equal to their string values: `ProcessorType.TEXT == "text"`
- Members work in string formatting: `f"type is {ProcessorType.TEXT}"`
- Members are hashable and can be used as dict keys.

### Compatibility Constants

The `_compat` module also exports version-detection constants:

```python
from file_organizer._compat import (
    PY_VERSION,          # e.g., (3, 9)
    HAS_STRENUM,         # True on 3.11+
    HAS_UNION_TYPE,      # True on 3.10+ (runtime X | Y)
    HAS_MATCH_STATEMENT, # True on 3.10+
    HAS_EXCEPTION_GROUPS,# True on 3.11+
    UTC,                 # datetime.timezone.utc (all versions)
)
```

Use these when you need runtime version branching.

## How to Run on Python 3.9-3.12

### Prerequisites

```bash
# Install the target Python version (example using pyenv)
pyenv install 3.9.18
pyenv install 3.10.13
pyenv install 3.11.7
pyenv install 3.12.1

# Or use your system package manager
# macOS: brew install python@3.9
# Ubuntu: sudo apt install python3.9
```

### Installation

```bash
# Create a virtual environment with the target Python
python3.9 -m venv .venv
source .venv/bin/activate

# Install the package
pip install -e ".[dev]"

# Verify installation
python -c "import file_organizer; print('OK')"
```

### Running

```bash
# CLI
file-organizer --help

# Or the short alias
fo --help
```

## Known Limitations Per Version

### Python 3.9

- `StrEnum` is polyfilled. The backport passes the same tests but is not
  identical to the stdlib implementation in edge cases (e.g., `auto()`
  generates lowercase names, matching 3.11 behavior).
- `X | Y` syntax cannot be used at runtime outside annotations (e.g., in
  `isinstance()` checks). Use `Union[X, Y]` from `typing` or the
  `check_type()` helper from `_compat` for runtime type checks.
- `match` statements are not available. Code must use `if/elif` chains.
- `datetime.UTC` does not exist. Use `datetime.timezone.utc` or the
  `UTC` constant from `_compat`.

### Python 3.10

- `StrEnum` is polyfilled (same as 3.9).
- `ExceptionGroup` and `except*` are not available.
- `X | Y` works at runtime for type checks (`isinstance(x, int | str)`).

### Python 3.11

- Full feature parity. `StrEnum` uses the stdlib implementation.
- `ExceptionGroup` and `except*` are available.
- `datetime.UTC` alias is available.

### Python 3.12

- Full feature parity with all modern features.
- Type parameter syntax (`type X = ...`) is available but not used
  in the project to maintain 3.9 compatibility.

## Multi-Version Testing with tox

The project uses [tox](https://tox.wiki/) to test across all supported Python
versions.

### Setup

```bash
# Install tox
pip install tox

# Ensure Python interpreters are available on PATH
# (pyenv, system packages, or manually installed)
```

### Running Tests

```bash
# Run all environments (skips missing interpreters)
tox

# Run a specific Python version
tox -e py39
tox -e py310
tox -e py311
tox -e py312

# Run linting
tox -e lint

# Run type checking
tox -e type

# Pass extra arguments to pytest
tox -e py39 -- -k "test_watcher" --tb=long
```

### tox Configuration

The project's `tox.ini` defines the following environments:

| Environment | Description |
|-------------|------------------------------------|
| `py39` | Run tests under Python 3.9 |
| `py310` | Run tests under Python 3.10 |
| `py311` | Run tests under Python 3.11 |
| `py312` | Run tests under Python 3.12 |
| `lint` | Lint with ruff (target: py39) |
| `type` | Type check with mypy (target: py39) |

The `skip_missing_interpreters = true` setting means tox will not fail if a
Python version is not installed -- it simply skips that environment.

### CI Integration

In a CI pipeline, install the desired Python versions and run tox:

```yaml
# Example GitHub Actions matrix
strategy:
  matrix:
    python-version: ["3.9", "3.10", "3.11", "3.12"]

steps:
  - uses: actions/setup-python@v5
    with:
      python-version: ${{ matrix.python-version }}
  - run: pip install tox
  - run: tox -e py$(echo ${{ matrix.python-version }} | tr -d '.')
```

## Migration Script

A helper script is provided at `file_organizer_v2/migrate_to_py39.sh` for
converting union operator syntax. It uses `pyupgrade --py39-plus` to
automatically rewrite `X | Y` annotations to `Union[X, Y]` form. The
preferred approach (already applied to this codebase) is to use
`from __future__ import annotations` instead, which avoids the need to change
annotation syntax at all.

## Developer Guidelines

1. **Always add `from __future__ import annotations`** as the first import in
   every new Python file.

1. **Use modern annotation syntax** (`X | Y`, `list[str]`, `dict[str, int]`)
   in type hints. The future import ensures compatibility.

1. **Do not use `X | Y` at runtime** outside annotations on Python 3.9. For
   runtime type checks, use:

   ```python
   from file_organizer._compat import check_type
   if check_type(value, (str, int)):
       ...
   ```

1. **Import `StrEnum` from `_compat`**, not from `enum`:

   ```python
   from file_organizer._compat import StrEnum
   ```

1. **Use `datetime.timezone.utc`** (or `_compat.UTC`) instead of
   `datetime.UTC`.

1. **Run `tox -e py39`** before pushing to verify backward compatibility.

1. **Set ruff and mypy targets to `py39`** (already configured in
   `pyproject.toml`).
