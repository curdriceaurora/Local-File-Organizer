# Testing Strategy

## Running Tests

```bash
pytest                                          # Full test suite
pytest --cov=file_organizer --cov-report=html  # With coverage
pytest tests/services/ -v                       # Specific directory
pytest -m smoke -x                              # Fast smoke suite (~3.5s, pre-commit validation)
pytest -m ci -x                                 # CI tests for PR validation
pytest -m "not regression" -x                   # All tests except regression (full run)
pytest -k "backup or dedup"                     # Filter by name
```

## Test Markers

```python
@pytest.mark.unit          # Unit tests
@pytest.mark.smoke         # Fast critical-path tests (pre-commit validation)
@pytest.mark.integration   # Integration tests
@pytest.mark.e2e           # End-to-end tests
@pytest.mark.asyncio       # Async tests (FastAPI, TUI, services)
@pytest.mark.benchmark     # Performance benchmarks
@pytest.mark.ci            # CI-specific tests
@pytest.mark.slow          # Slow tests
@pytest.mark.regression    # Regression tests (full suite only)
@pytest.mark.no_ollama     # Tests that run without Ollama installed

def test_example():
    pass
```

## Coverage Goals

### Current Status (Epic #571 Complete)

- **Overall**: 96.8% docstring coverage | 916+ tests
- **API Module**: 92% code coverage ✅
- **Services**: 82% code coverage ✅
- **Models**: 90% code coverage ✅
- **CI Gate**: 95% minimum (coverage requirement, enforced on main pushes)

### Coverage Targets by Module

| Module | Target | Current | Status |
|--------|--------|---------|--------|
| api | 80% | 92% | ✅ +12% |
| services | 80% | 82% | ✅ +2% |
| models | 90% | 90% | ✅ Met |
| cli | 80% | 75% | 🔶 -5% |
| tui | 90% | 79% | 🔶 -11% |
| web | 80% | 78% | 🔶 -2% |

See [Coverage Report](coverage-report.md) for detailed metrics by module.

---
