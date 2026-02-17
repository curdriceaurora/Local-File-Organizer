# Plugin Development Guide

## Overview

Create custom plugins to extend File Organizer functionality through a hook-based system.

## Getting Started

### Create a Plugin

```python
# my_plugin.py
from file_organizer.plugins import Plugin, register_hook

class MyPlugin(Plugin):
    """Custom plugin for File Organizer"""

    def __init__(self):
        super().__init__()
        self.name = "my-plugin"
        self.version = "1.0.0"

    def initialize(self):
        """Called when plugin is loaded"""
        register_hook("on_file_uploaded", self.on_upload)
        register_hook("on_organize_complete", self.on_complete)

    async def on_upload(self, file):
        """Handle file upload"""
        print(f"File uploaded: {file.name}")

    async def on_complete(self, result):
        """Handle organization completion"""
        print(f"Organization complete: {result}")
```

## Plugin Hooks

### Available Hooks

| Hook | Triggered | Parameters |
|------|-----------|-----------|
| `on_file_uploaded` | File uploaded | `file: UploadedFile` |
| `on_organize_start` | Organization begins | `job_id: str` |
| `on_organize_complete` | Organization finishes | `result: OrganizeResult` |
| `on_duplicate_detected` | Duplicates found | `duplicates: List[File]` |
| `on_file_processed` | File processed | `file: File, metadata: Dict` |
| `on_error` | Error occurs | `error: Exception, context: Dict` |

### Hook Implementation

```python
from file_organizer.plugins import register_hook

@register_hook("on_organize_complete")
async def handle_completion(result):
    # Send notification
    send_notification(f"Organized {result.file_count} files")

@register_hook("on_duplicate_detected")
async def handle_duplicates(duplicates):
    # Log duplicates
    for dup in duplicates:
        logger.info(f"Duplicate: {dup.path}")
```

## Custom Methodologies

Create custom file organization methodologies:

```python
from file_organizer.methodologies import BaseMethodology

class CustomMethodology(BaseMethodology):
    """Custom organization methodology"""

    name = "custom"
    description = "My custom methodology"

    def organize(self, file, metadata):
        """Return suggested folder and filename"""
        folder = self.determine_folder(metadata)
        filename = self.generate_filename(file, metadata)
        return {
            "folder": folder,
            "filename": filename,
            "confidence": 0.95
        }

    def determine_folder(self, metadata):
        # Custom logic to determine folder
        pass

    def generate_filename(self, file, metadata):
        # Custom logic to generate filename
        pass
```

## Configuration

### Plugin Configuration File

Create `config/plugins.yaml`:

```yaml
plugins:
  my-plugin:
    enabled: true
    module: my_plugin
    class: MyPlugin
    config:
      option1: value1
      option2: value2

  another-plugin:
    enabled: false
    module: another_plugin
    class: AnotherPlugin
```

### Plugin Settings

```python
class MyPlugin(Plugin):
    def __init__(self, config=None):
        super().__init__()
        self.config = config or {}
        self.timeout = self.config.get("timeout", 30)
        self.enabled = self.config.get("enabled", True)
```

## Plugin Structure

### Directory Layout

```
my_plugin/
├── __init__.py
├── plugin.py
├── config.yaml
├── templates/
│   └── settings.html
├── static/
│   ├── css/
│   └── js/
└── tests/
    └── test_plugin.py
```

### Plugin Metadata

```python
from file_organizer.plugins import Plugin

class MyPlugin(Plugin):
    name = "my-plugin"
    version = "1.0.0"
    author = "Your Name"
    description = "Plugin description"
    dependencies = ["requests>=2.28.0"]

    def get_metadata(self):
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author
        }
```

## API Access

### Access Core Services

```python
from file_organizer.core import FileOrganizer
from file_organizer.db import SessionLocal

class MyPlugin:
    def __init__(self):
        self.core = FileOrganizer()
        self.db = SessionLocal()

    async def process_file(self, file_path):
        result = await self.core.organize_file(file_path)
        return result
```

### Database Access

```python
from file_organizer.models import File, FileMetadata

async def list_recent_files(self, limit=10):
    files = self.db.query(File)\
        .order_by(File.created_at.desc())\
        .limit(limit)\
        .all()
    return files
```

## Testing

### Unit Tests

```python
import pytest
from my_plugin import MyPlugin

@pytest.fixture
def plugin():
    return MyPlugin()

def test_plugin_initialization(plugin):
    assert plugin.name == "my-plugin"

@pytest.mark.asyncio
async def test_on_upload(plugin):
    class MockFile:
        name = "test.txt"
        path = "/tmp/test.txt"

    await plugin.on_upload(MockFile())
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_plugin_integration(app_client):
    # Upload file
    response = await app_client.post(
        "/api/v1/files/upload",
        files={"file": ("test.txt", b"content")}
    )

    # Check plugin was called
    assert response.status_code == 200
```

## Distribution

### Package Plugin

```bash
python setup.py sdist bdist_wheel
```

### Install Plugin

```bash
pip install my-plugin-1.0.0.whl

# Enable in config
# Restart application
```

## Best Practices

### Performance

- Use async/await for I/O operations
- Cache expensive computations
- Avoid blocking operations
- Set reasonable timeouts

### Error Handling

```python
try:
    result = await self.process_file(file)
except Exception as e:
    logger.error(f"Plugin error: {e}")
    raise
```

### Logging

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Plugin initialized")
logger.debug("Processing file: %s", filename)
logger.error("Error processing file: %s", error)
```

## See Also

- [Architecture Guide](architecture.md)
- [Contributing Guide](contributing.md)
