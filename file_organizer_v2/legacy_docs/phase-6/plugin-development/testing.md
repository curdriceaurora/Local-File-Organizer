# Testing Plugins

## Why Dedicated Plugin Tests

Plugin code has high variation and external dependencies. A dedicated test layer catches integration regressions without touching core organizer code.

## PluginTestCase Usage

```python
from file_organizer.plugins.sdk import PluginTestCase

class TestMyPlugin(PluginTestCase):
    def test_file_creation(self) -> None:
        path = self.create_test_file("input/sample.txt", "hello")
        self.assert_file_exists(path)
```

## Recommended Coverage

- Lifecycle transitions (`on_load`, `on_enable`, `on_disable`, `on_unload`)
- Hook callback behavior for valid/invalid payloads
- SDK client error handling paths
- Filesystem permission boundaries for plugin outputs

## Pitfalls

- Avoid non-deterministic network calls in unit tests.
- Use temporary directories, never hard-coded system paths.
- Test both successful and failed webhook delivery paths.
