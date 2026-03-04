# Testing Strategy

## Running Tests

```bash
pytest                                          # All tests
pytest --cov=file_organizer --cov-report=html  # With coverage
pytest tests/services/ -v                       # Specific directory
pytest -m "not regression" -x                  # Skip regression tests, stop on first fail
pytest -k "backup or dedup"                     # Filter by name
```

## Test Markers

```python
@pytest.mark.unit          # Unit tests
@pytest.mark.integration   # Integration tests
@pytest.mark.e2e           # End-to-end tests
@pytest.mark.benchmark     # Performance benchmarks
@pytest.mark.ci            # CI-specific tests
@pytest.mark.slow          # Slow tests
@pytest.mark.regression    # Regression tests

def test_example():
    pass
```

## Coverage Goals

- Unit tests: 80%+ coverage (current CI gate: 74% via `--cov-fail-under=74`)
- Integration tests: Key workflows
- CI tests: Pipeline and build validation

---

