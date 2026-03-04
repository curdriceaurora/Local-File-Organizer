# Testing Strategy

### Running Tests

```bash
pytest                                          # All tests
pytest --cov=file_organizer --cov-report=html  # With coverage
pytest tests/services/ -v                       # Specific directory
pytest -m "not regression" -x                  # Skip regression, stop on first fail
pytest -k "backup or dedup"                     # Filter by name
```

### Test Markers

```python
@pytest.mark.unit          # Unit tests
@pytest.mark.integration   # Integration tests
@pytest.mark.ci            # CI-specific tests
@pytest.mark.slow          # Slow tests
@pytest.mark.regression    # Regression tests
```

### Coverage Goals

- Unit tests: 80%+ coverage
- Integration tests: Key workflows
- CI tests: Pipeline and build validation

---

