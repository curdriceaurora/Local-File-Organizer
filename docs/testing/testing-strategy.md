# Testing Strategy

## Running Tests

```bash
pytest                                          # Full test suite
pytest --cov=file_organizer --cov-report=html  # With coverage
pytest tests/services/ -v                       # Specific directory
pytest -m smoke -x                              # Fast smoke suite (pre-commit validation, deterministic)
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
@pytest.mark.benchmark     # Performance benchmarks
@pytest.mark.ci            # CI-specific tests
@pytest.mark.slow          # Slow tests
@pytest.mark.regression    # Regression tests (full suite only)

def test_example():
    pass
```

## Coverage Goals

- Unit tests: 80%+ coverage (current CI gate: 74% via `--cov-fail-under=74`)
- Integration tests: Key workflows
- CI tests: Pipeline and build validation

---

