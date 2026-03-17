# Testing Guide

File Organizer uses `pytest` for comprehensive test coverage with 916+ tests across all modules.

## Quick Start

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=file_organizer --cov-report=html

# Fast smoke tests (pre-commit validation, matches actual gate)
pytest tests/ -m "smoke" -q --strict-markers --timeout=30 --override-ini="addopts="

# Run specific module tests
pytest tests/services/ -v
```

## Test Organization

Tests are organized by module under `tests/` mirroring the source structure:

```text
tests/
├── api/              # FastAPI routes, middleware, models (100+ tests)
├── cli/              # CLI commands (65+ tests)
├── services/         # Business logic (300+ tests)
├── tui/              # Terminal UI (50+ tests)
├── web/              # Web routes and templates (40+ tests)
├── models/           # Data models (40+ tests)
├── config/           # Configuration (30+ tests)
├── integration/      # Cross-module workflows (130+ tests)
└── ci/               # CI/workflow validation (20+ tests)
```

## Test Markers

Use pytest markers to categorize tests:

```text
@pytest.mark.unit          # Unit tests (isolated, fast)
@pytest.mark.smoke         # Critical path tests (< 30s total, pre-commit validation)
@pytest.mark.integration   # Integration tests (cross-module workflows)
@pytest.mark.e2e           # End-to-end tests (full user journeys)
@pytest.mark.asyncio       # Async tests (FastAPI, TUI, services)
@pytest.mark.benchmark     # Performance tests
@pytest.mark.ci            # CI-specific tests
@pytest.mark.slow          # Long-running tests (>5s)
@pytest.mark.regression    # Regression tests (full suite only)
```

### Running Tests by Marker

```bash
# Only smoke tests (fast pre-commit validation - full gate)
pytest tests/ -m "smoke" -q --strict-markers --timeout=30 --override-ini="addopts="

# All unit tests
pytest -m unit

# Integration + E2E tests
pytest -m "integration or e2e"

# Exclude slow tests
pytest -m "not slow"

# CI gate tests only
pytest -m ci
```

## Coverage Metrics

### Current Coverage Status (Epic #571 Complete)

| Module | Lines | Covered | Coverage | Target |
|--------|-------|---------|----------|--------|
| **api/** | 2,400+ | 2,200+ | 92% | 80% ✅ |
| **services/** | 2,800+ | 2,300+ | 82% | 80% ✅ |
| **cli/** | 1,200+ | 900+ | 75% | 80% 🔶 |
| **tui/** | 1,400+ | 1,100+ | 79% | 90% 🔶 |
| **web/** | 1,800+ | 1,400+ | 78% | 80% 🔶 |
| **models/** | 500+ | 450+ | 90% | 90% ✅ |
| **config/** | 400+ | 380+ | 95% | 90% ✅ |
| **Docstrings** | 4,130 items | 3,924 | 95.0% | 95% ✅ |

**Overall**: 916+ tests, ~95%+ on tested modules, 95.0% docstring coverage

### Coverage Gaps

Known areas with lower coverage (0-50%):
- `updater/` - Application update system (0%)
- `watcher/` - File system monitoring (0%)
- `cli/` subcommands - Some commands untested
- `tui/` views - Complex UI state logic (partial)

These represent ~15% of the codebase and are marked for Phase C work.

### Running Coverage Reports

```bash
# Per-module coverage
pytest --cov=file_organizer.api --cov-report=term-missing

# Full project coverage with HTML report
pytest --cov=file_organizer --cov-report=html
# Open htmlcov/index.html to view

# Docstring coverage (requires interrogate)
interrogate -v src/file_organizer --fail-under 95
```

## Testing Patterns

### API Route Testing

Use `httpx` with ASGI transport for testing FastAPI endpoints:

```python
import pytest
from httpx import ASGITransport, AsyncClient, Client
from file_organizer.api.main import create_app

@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

# Or for synchronous use:
@pytest.fixture
def sync_client():
    app = create_app()
    transport = ASGITransport(app=app)
    with Client(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_organize_endpoint(client):
    response = await client.post("/api/organize", json={"path": "/tmp"})
    assert response.status_code == 200
    assert "organized" in response.json()
```

### Service Testing

Test services with real dependencies, mocking only external boundaries:

```python
from pathlib import Path
from file_organizer.services.text_processor import TextProcessor

def test_text_processor(tmp_path):
    processor = TextProcessor()
    # Create test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("Sample content for testing")

    result = processor.process_file(test_file)
    assert result is not None
    assert "test" in str(result).lower() or len(result) > 0
```

### CLI Testing

Use `typer.testing.CliRunner` for CLI command testing:

```python
from typer.testing import CliRunner
from file_organizer.cli.main import app

runner = CliRunner()

def test_organize_command():
    result = runner.invoke(app, ["organize", "/tmp/files"])
    assert result.exit_code == 0
    assert "organized" in result.output
```

### TUI Testing

Use Textual's `pilot` for testing terminal UI:

```python
import pytest
from file_organizer.tui.app import FileOrganizerApp

@pytest.mark.asyncio
async def test_app_loads():
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        assert pilot.app.title == "File Organizer"
```

### Integration Testing

Integration tests exercise real service instances with only external HTTP (Ollama/OpenAI) mocked at the `model._do_generate()` level. This verifies the wiring between components that unit tests mock away.

```bash
# Run all integration tests
pytest -m integration

# Run a specific integration test file
pytest tests/integration/test_error_propagation.py -v
```

**Shared fixtures** (from `tests/integration/conftest.py`):

| Fixture | Purpose |
|---------|---------|
| `stub_all_models` | Stubs init + generate for both text and vision models |
| `stub_text_model_init` | Patches `TextModel.initialize()` to skip Ollama client setup |
| `stub_text_model_generate` | Patches `TextModel._do_generate()` with deterministic responses |
| `stub_vision_model_init` | Patches `VisionModel.initialize()` to skip Ollama client setup |
| `stub_vision_model_generate` | Patches `VisionModel._do_generate()` with deterministic responses |
| `stub_nltk` | No-ops `ensure_nltk_data()` |
| `integration_source_dir` | Temp directory with `.txt`, `.csv`, `.md` files |
| `integration_output_dir` | Clean temp output directory |
| `isolated_config_dir` | Temp config directory (no user config interference) |

**Helpers** (importable from `tests.integration.conftest`):

| Helper | Purpose |
|--------|---------|
| `make_text_config(**overrides)` | Build a `ModelConfig` for text models |
| `make_vision_config(**overrides)` | Build a `ModelConfig` for vision models |
| `patch_text_generate(side_effect)` | Context manager to patch `TextModel._do_generate` with custom behavior |
| `minimal_png_bytes()` | Returns a valid 1x1 PNG image for vision tests |

**Example** (from `tests/integration/test_error_propagation.py`):

```python
@pytest.mark.integration
class TestModelErrors:
    def test_model_exception_uses_fallback_values(
        self,
        stub_text_model_init: None,
        stub_nltk: None,
        integration_source_dir: Path,
    ) -> None:
        """When model.generate() raises, TextProcessor uses fallback values."""
        text_cfg = make_text_config()
        processor = TextProcessor(config=text_cfg)
        processor.initialize()

        with patch_text_generate_error(RuntimeError("GPU out of memory")):
            result = processor.process_file(
                integration_source_dir / "report.txt"
            )

        # Graceful degradation — fallback values, not failure
        assert result.error is None
        assert result.folder_name == "documents"
```

**Key design decisions**:

- Mock at `_do_generate()`, not at service level — exercises real service-to-model wiring
- Real filesystem via `tmp_path` — tests actual file I/O
- `TextProcessor` uses graceful degradation: model errors produce fallback values (`"documents"`/`"document"`), not `failed_files`
- All tests marked `@pytest.mark.integration` — CI runs them on main pushes only, not on every PR

See `.claude/epics/integration-test-harness/epic.md` for the full architecture and gap analysis.

## Test Quality Standards

All tests must follow these standards:

1. **Real Assertions**: Every test has meaningful assertions verifying behavior
   - ✅ `assert result.status_code == 200`
   - ❌ `assert True` (useless placeholder)

2. **No Internal Mocking**: Only mock external boundaries (HTTP, GPU, filesystem)
   - ✅ Mock `httpx.post()` calls to external APIs
   - ❌ Mock internal service methods

3. **Fast Execution**: Individual tests < 5 seconds
   - Use fixtures for setup
   - Avoid real I/O when possible (use temp files)

4. **Isolation**: Tests don't interfere with each other
   - Use temp directories for file operations
   - Use unique ports for server tests
   - Clear database state between tests

5. **Clear Names**: Test names describe what's being tested
   - ✅ `test_organize_creates_subdirectories_for_file_types()`
   - ❌ `test_organize()`

6. **Docstrings**: Module-level docstring in each test file
   ```python
   """Tests for the file organization pipeline.

   Covers: text extraction, pattern analysis, suggestion generation.
   """
```

## Pre-Commit Validation

Before committing, run the smoke test suite:

```bash
# Fast pre-commit validation (< 30 seconds, matches actual gate)
pytest tests/ -m "smoke" -q --strict-markers --timeout=30 --override-ini="addopts="

# Or use the canonical pre-PR guardrail orchestrator
bash .claude/scripts/pre-commit-validation.sh
```

Both must pass before committing code changes.

For CLI help and usage assertions, prefer `result.output` instead of
`result.stdout`. Typer and Rich can render styled help text differently across
environments, so normalize rendered output before asserting exact help content.

## CI/CD Testing

GitHub Actions runs automated checks on every PR and push to main:

**Pull Request Validation:**
- `pytest -m "ci"` test subset runs (selected critical tests)
- Linting checks (ruff for Python, markdownlint for docs)
- Type checking (mypy)
- No coverage threshold enforced

**Main Branch Pushes:**
- Full test suite passes (`pytest`)
- Coverage must be ≥ 95% (code) and ≥ 95% (docstrings) — both gates must pass
- Linting must pass (ruff and markdownlint)
- Type checking must pass (mypy)

See `.github/workflows/` for CI configuration.

## Common Testing Issues

### Issue: Import errors in tests

**Solution**: Ensure test file is in correct directory with `__init__.py`
```bash
touch tests/your_module/__init__.py
```

### Issue: Async test failures

**Solution**: Mark with `@pytest.mark.asyncio` and use `async def`
```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_call()
    assert result is not None
```

### Issue: Fixture scope confusion

**Solution**: Use `function` scope for most fixtures (default), `session` for expensive setup
```python
@pytest.fixture(scope="function")  # Reset for each test
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir
```

### Issue: Flaky tests (fail intermittently)

**Solution**: Remove race conditions, use deterministic test data
```python
# Bad: depends on timing
time.sleep(0.1)
assert event_received

# Good: use explicit synchronization
event.wait(timeout=5)
assert event.is_set()
```

## Test Coverage by Epic

### Epic #571: Desktop UI Test Coverage

- **Phase A**: API, plugins, CLI, web, services (12% → 91% coverage) ✅ COMPLETE
- **Phase B**: TUI, models, updater, watcher, docstrings (91% → 96.8%) ✅ COMPLETE
- **Phase C**: Remaining modules and integration (target: 95%+)

See `.claude/epics/desktopui-test-coverage/` for detailed task tracking.

## References

- [Testing Strategy Details](../testing/testing-strategy.md)
- [Coverage Report](../testing/coverage-report.md)
- [pytest Documentation](https://docs.pytest.org/)
- [Textual Testing Guide](https://textual.textualize.io/guide/testing/)
- [FastAPI Testing](https://fastapi.tiangolo.com/advanced/testing-dependencies/)
