# CI Generation Anti-Patterns

Reference ruleset for writing CI/CD configuration that passes PR review without correction.
Sourced from CodeRabbit and Copilot review comments — 84 classified CI findings (115 PRs, issues #84–#655).

**Frequency baseline**: 84 classified findings — ~8 findings per CI PR average.

---

## Pre-Generation Checklist (MANDATORY before writing any CI config)

- [ ] Read existing `.github/workflows/ci.yml` BEFORE adding any new workflow step
- [ ] Verify coverage threshold against `pyproject.toml` `cov-fail-under` value BEFORE documenting it
- [ ] Check `@lru_cache` decorators on functions that read env vars — remove if found
- [ ] No wall-clock time limits in CI (`< 1s`, `< 5s`) — use relative assertions or skip entirely

---

## Pattern C1: FLAKY_GATE — ~8 findings

**What it is**: Hard wall-clock time limits in CI (e.g., `assert duration < 1`) that fail under shared runner load; `time.sleep` in tests instead of event-based waits.

**Bad**:
```python
# BAD — strict wall-clock limit fails under CI load
start = time.time()
result = process_file(large_file)
assert time.time() - start < 1.0, "Processing too slow"

# BAD — time.sleep blocks test runner unnecessarily
time.sleep(2)
assert service.is_ready()
```

**Good**:
```python
# GOOD — relative threshold or no timing assertion
result = process_file(large_file)
assert result is not None  # skip timing in CI

# GOOD — poll with timeout instead of fixed sleep
import time
deadline = time.time() + 10
while time.time() < deadline:
    if service.is_ready():
        break
    time.sleep(0.1)
else:
    pytest.fail("Service not ready within 10s")
```

**Pre-generation check**: Search for `assert.*< [0-9]` in test files before adding timing assertions.

---

## Pattern C2: WRONG_TRIGGER — ~6 findings

**What it is**: Job runs on events where it shouldn't — e.g., coverage upload on `pull_request` events (partial suite gives misleading metrics), or expensive jobs running on every push to every branch.

**Bad**:
```yaml
# BAD — coverage upload on PR events (partial suite = wrong metrics)
on:
  push:
  pull_request:

jobs:
  test-and-upload:
    steps:
      - run: pytest --cov
      - uses: codecov/codecov-action@v3
```

**Good**:
```yaml
# GOOD — coverage upload only on main push
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    steps:
      - run: pytest --cov
      - name: Upload coverage (main only)
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: codecov/codecov-action@v3
```

**Pre-generation check**: For every `uses:` action that writes to an external service (codecov, GitHub releases, etc.), add `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`.

---

## Pattern C3: CACHE_MISCONFIG — ~5 findings

**What it is**: `@lru_cache` on functions that read env vars — cache holds stale values across test runs or when the env var changes between calls.

**Bad**:
```python
# BAD — cached function reads env var; cache never invalidated between tests
@lru_cache(maxsize=None)
def get_config_manager() -> ConfigManager:
    config_dir = os.environ.get("FO_CONFIG_DIR", "~/.config/file-organizer")
    return ConfigManager(config_dir)
```

**Good**:
```python
# GOOD — no cache, fresh read each time (env may change in tests)
def get_config_manager() -> ConfigManager:
    config_dir = os.environ.get("FO_CONFIG_DIR", "~/.config/file-organizer")
    return ConfigManager(config_dir)

# GOOD — if caching needed, use explicit invalidation
_config_manager: Optional[ConfigManager] = None

def get_config_manager() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(os.environ.get("FO_CONFIG_DIR", "~/.config/file-organizer"))
    return _config_manager

def reset_config_manager() -> None:
    global _config_manager
    _config_manager = None
```

**Pre-generation check**: Search for `@lru_cache` on any function that calls `os.environ.get` or `os.getenv`.

```bash
# Detection command
rg "@lru_cache" src/ -A 5 | grep -B 3 "environ\|getenv"
```

---

## Pattern C4: COVERAGE_GATE — 25 findings (most frequent CI pattern)

**What it is**: Coverage threshold declared in PR description, README, or docs doesn't match the value actually enforced in `pyproject.toml` or the workflow file.

**Bad**:
```markdown
<!-- In README.md — WRONG threshold -->
## CI Requirements
- Code coverage ≥ 74%

# In PR description — WRONG threshold
Coverage gate: 75%
```
*(Actual enforced value in pyproject.toml: `cov-fail-under = 95`)*

**Good**:
```bash
# ALWAYS check actual value before documenting
grep "cov-fail-under\|fail_under" pyproject.toml
# → cov-fail-under = 95

# THEN document the actual value
# "Code coverage gate: 95% (enforced via pyproject.toml cov-fail-under=95)"
```

**Pre-generation check**: Before writing any coverage percentage in any document, run:
```bash
grep "cov-fail-under\|fail_under" pyproject.toml
```
Use only the number that command returns.

**Current project values** (verify before using):
- Code coverage gate: `cov-fail-under = 95` (in `pyproject.toml`)

---

## Pattern C5: SECRET_EXPOSURE — ~4 findings

**What it is**: Tokens logged or passed via query string in CI context; env vars echoed in workflow steps.

**Bad**:
```yaml
# BAD — env var echoed to logs
- name: Debug
  run: echo "Token is ${{ secrets.API_TOKEN }}"

# BAD — secret passed as CLI argument (visible in process list)
- run: python script.py --token ${{ secrets.API_TOKEN }}
```

**Good**:
```yaml
# GOOD — secret passed as environment variable
- name: Run script
  env:
    API_TOKEN: ${{ secrets.API_TOKEN }}
  run: python script.py  # reads from env, not args

# GOOD — mask in logs if must echo
- run: echo "::add-mask::${{ secrets.API_TOKEN }}"
```

---

## Pattern C6: SLOW_WORKFLOW — ~8 findings

**What it is**: Full matrix on every PR; duplicated jobs; unnecessary steps not gated behind `if:` conditions; no caching of dependencies.

**Bad**:
```yaml
# BAD — full OS matrix on every PR
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    python-version: ["3.9", "3.10", "3.11", "3.12"]
```

**Good**:
```yaml
# GOOD — fast matrix on PR, full matrix on main
strategy:
  matrix:
    os: ${{ github.event_name == 'pull_request' && '["ubuntu-latest"]' || '["ubuntu-latest", "windows-latest", "macos-latest"]' }}
    python-version: ${{ github.event_name == 'pull_request' && '["3.11"]' || '["3.9", "3.10", "3.11", "3.12"]' }}

# GOOD — cache dependencies
- uses: actions/cache@v3
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/pyproject.toml') }}
```

---

## Rule of Thumb

Before writing any CI config:
1. **C4**: `grep "cov-fail-under" pyproject.toml` — use this exact number everywhere
2. **C3**: Search `@lru_cache` + `environ` — remove cache if found
3. **C2**: Add `if: github.event_name == 'push'` guard to external write actions
4. **C1**: No wall-clock time assertions in tests (`assert duration < N`)
