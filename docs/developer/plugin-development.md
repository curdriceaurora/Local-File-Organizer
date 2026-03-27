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

## Complete Example

Here's a production-ready plugin that automatically tags images based on EXIF metadata:

```python
"""EXIF-based image tagger plugin."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from file_organizer.plugins import Plugin, PluginMetadata
from file_organizer.plugins.sdk import hook


class ExifImageTaggerPlugin(Plugin):
    """Automatically tags images with EXIF-derived metadata."""

    name = "exif_image_tagger"
    version = "1.0.0"
    allowed_paths: list = []

    def on_load(self) -> None:
        """Handle plugin load event."""
        return None

    def on_enable(self) -> None:
        """Handle plugin enable event and configure settings."""
        self.include_camera_model = self.config.get("include_camera_model", True)
        self.include_location = self.config.get("include_location", True)
        self.date_format = self.config.get("date_format", "%Y-%m-%d")

    def on_disable(self) -> None:
        """Handle plugin disable event."""
        return None

    def on_unload(self) -> None:
        """Handle plugin unload event."""
        return None

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="exif_image_tagger",
            version="1.0.0",
            author="File Organizer Team",
            description="Automatically tags images based on EXIF metadata.",
            dependencies=("pillow>=10.0.0",),
        )

    @hook("file.organized", priority=10)
    def on_file_organized(self, payload: dict[str, Any]) -> dict[str, object]:
        """Extract EXIF data and add tags to organized image files."""
        destination = payload.get("destination_path")
        if not isinstance(destination, str) or not destination:
            return {"tagged": False, "reason": "missing destination_path"}

        target = Path(destination)
        if not target.exists():
            return {"tagged": False, "reason": "destination file missing"}

        # Only process image files
        if target.suffix.lower() not in {".jpg", ".jpeg", ".tiff", ".png"}:
            return {"tagged": False, "reason": "not an image file"}

        tags = self._extract_exif_tags(target)
        if not tags:
            return {"tagged": False, "reason": "no EXIF data found"}

        # Store tags in payload for downstream plugins/processing
        payload["tags"] = tags
        return {"tagged": True, "tags": tags, "tag_count": len(tags)}

    def _extract_exif_tags(self, image_path: Path) -> list[str]:
        """Extract relevant tags from image EXIF data."""
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS
        except ImportError:
            return []

        tags: list[str] = []

        try:
            with Image.open(image_path) as img:
                exif_data = img.getexif()
                if not exif_data:
                    return tags

                # Extract camera model
                if self.include_camera_model:
                    model = exif_data.get(272)  # Model tag
                    if model:
                        tags.append(f"camera:{model.strip()}")

                # Extract date taken
                date_taken = exif_data.get(36867)  # DateTimeOriginal
                if date_taken:
                    try:
                        dt = datetime.strptime(date_taken, "%Y:%m:%d %H:%M:%S")
                        tags.append(f"date:{dt.strftime(self.date_format)}")
                        tags.append(f"year:{dt.year}")
                    except ValueError:
                        pass

                # Extract location (GPS data)
                if self.include_location:
                    gps_info = exif_data.get(34853)  # GPSInfo
                    if gps_info:
                        tags.append("location:geotagged")

        except Exception:
            # Silently handle any PIL errors
            pass

        return tags
```

### Plugin Configuration

Create `config/plugins.yaml` to configure the plugin:

```yaml
plugins:
  exif_image_tagger:
    enabled: true
    config:
      include_camera_model: true
      include_location: true
      date_format: "%Y-%m-%d"
```

### Key Features

This example demonstrates:

- **Lifecycle Methods**: Proper implementation of `on_load`, `on_enable`, `on_disable`, and `on_unload`
- **Hook Registration**: Using `@hook` decorator with priority for event handling
- **Configuration**: Reading plugin config with sensible defaults
- **Error Handling**: Graceful handling of missing EXIF data and import errors
- **Metadata**: Complete `PluginMetadata` with dependencies
- **Type Safety**: Type hints and validation for payload data
- **Real-world Logic**: Extracting and processing EXIF data from images

## Plugin Directory Structure

Every plugin must follow a standard directory structure with a `plugin.json` manifest file:

```text
my_plugin/
├── plugin.json          # Required: Plugin manifest
├── plugin.py            # Plugin implementation (entry_point)
├── __init__.py          # Optional: Package initialization
├── requirements.txt     # Optional: Python dependencies
├── README.md            # Optional: Documentation
└── tests/               # Optional: Test files
    └── test_plugin.py
```

### Minimal Example

The simplest plugin requires only two files:

```text
hello_world/
├── plugin.json
└── plugin.py
```

### Complete Example Structure

For production plugins, use this structure:

```text
exif_image_tagger/
├── plugin.json
├── plugin.py
├── __init__.py
├── requirements.txt
├── README.md
├── config/
│   └── defaults.yaml
└── tests/
    ├── __init__.py
    └── test_exif_tagger.py
```

## Plugin Manifest (plugin.json)

The `plugin.json` file is **required** and defines plugin metadata, dependencies, and entry point.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique plugin identifier (lowercase, underscores) |
| `version` | string | Semantic version (e.g., "1.0.0") |
| `author` | string | Plugin author name or organization |
| `description` | string | Brief description of plugin functionality |
| `entry_point` | string | Python file containing plugin class (e.g., "plugin.py") |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `license` | string | `"MIT"` | Plugin license identifier |
| `homepage` | string | `null` | URL to plugin homepage or repository |
| `dependencies` | array | `[]` | List of Python package dependencies |
| `min_organizer_version` | string | `"2.0.0"` | Minimum File Organizer version required |
| `max_organizer_version` | string | `null` | Maximum compatible File Organizer version |
| `allowed_paths` | array | `[]` | List of filesystem paths plugin can access |

### Minimal Manifest Example

```json
{
    "name": "hello_world",
    "version": "1.0.0",
    "author": "Your Name",
    "description": "A simple hello world plugin.",
    "entry_point": "plugin.py"
}
```

### Complete Manifest Example

```json
{
    "name": "exif_image_tagger",
    "version": "1.2.0",
    "author": "File Organizer Team",
    "description": "Automatically tags images based on EXIF metadata.",
    "entry_point": "plugin.py",
    "license": "MIT",
    "homepage": "https://github.com/yourorg/exif-tagger",
    "dependencies": [
        "pillow>=10.0.0",
        "piexif>=1.1.3"
    ],
    "min_organizer_version": "2.0.0",
    "max_organizer_version": "3.0.0",
    "allowed_paths": [
        "/Users/shared/photos",
        "/mnt/nas/media"
    ]
}
```

### Naming Conventions

- **Plugin name**: Use lowercase with underscores (e.g., `exif_image_tagger`, not `ExifImageTagger`)
- **Entry point**: Typically `plugin.py`, but can be any Python file
- **Dependencies**: Use pip-style version specifiers (e.g., `"pillow>=10.0.0,<11.0.0"`)

### Version Compatibility

Specify version constraints to ensure compatibility:

```json
{
    "min_organizer_version": "2.1.0",
    "max_organizer_version": "2.9.99",
    "dependencies": [
        "requests>=2.28.0,<3.0.0",
        "pyyaml~=6.0"
    ]
}
```

**Version specifiers:**
- `>=2.0.0` - Minimum version
- `<3.0.0` - Maximum version (exclusive)
- `~=6.0` - Compatible release (>= 6.0, < 7.0)
- `==1.2.3` - Exact version (not recommended)

### Security: Allowed Paths

Restrict plugin filesystem access using `allowed_paths`:

```json
{
    "allowed_paths": [
        "/Users/shared/uploads",
        "/mnt/storage/organized"
    ]
}
```

The plugin sandbox will enforce these restrictions, preventing access to other directories.

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

```text
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

class MyPlugin:
    def __init__(self):
        self.core = FileOrganizer()

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

### Using PluginTestCase

The SDK provides `PluginTestCase` for testing plugins with isolated filesystem helpers:

```python
"""Tests for EXIF Image Tagger Plugin."""

from __future__ import annotations

from pathlib import Path

from file_organizer.plugins.sdk.testing import PluginTestCase

from exif_image_tagger import ExifImageTaggerPlugin


class TestExifImageTaggerPlugin(PluginTestCase):
    """Test suite for ExifImageTaggerPlugin using SDK test utilities."""

    def setUp(self) -> None:
        """Set up test fixtures with isolated filesystem."""
        super().setUp()
        self.plugin = ExifImageTaggerPlugin()
        self.plugin.on_enable()

    def test_handles_non_image_files(self) -> None:
        """Test that plugin skips non-image files."""
        # Create test text file using SDK helper
        test_file = self.create_test_file("document.txt", "Hello, world!")
        self.assert_file_exists(test_file)

        payload = {"destination_path": str(test_file)}
        result = self.plugin.on_file_organized(payload)

        self.assertFalse(result["tagged"])
        self.assertEqual(result["reason"], "not an image file")

    def test_handles_missing_destination(self) -> None:
        """Test that plugin handles missing destination_path gracefully."""
        payload = {}
        result = self.plugin.on_file_organized(payload)

        self.assertFalse(result["tagged"])
        self.assertEqual(result["reason"], "missing destination_path")

    def test_handles_nonexistent_file(self) -> None:
        """Test that plugin handles nonexistent files."""
        nonexistent = self.test_dir / "missing.jpg"
        self.assert_file_not_exists(nonexistent)

        payload = {"destination_path": str(nonexistent)}
        result = self.plugin.on_file_organized(payload)

        self.assertFalse(result["tagged"])
        self.assertEqual(result["reason"], "destination file missing")

    def test_processes_image_without_exif(self) -> None:
        """Test that plugin handles images without EXIF data."""
        # Create minimal PNG file without EXIF data
        image_file = self.create_test_file("test_images/photo.png", "")

        # Write minimal valid PNG header
        with open(image_file, "wb") as f:
            # PNG signature
            f.write(b"\x89PNG\r\n\x1a\n")
            # Minimal IHDR chunk for 1x1 image
            f.write(b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01")
            f.write(b"\x08\x02\x00\x00\x00\x90wS\xde")
            # IEND chunk
            f.write(b"\x00\x00\x00\x00IEND\xaeB`\x82")

        self.assert_file_exists(image_file)

        payload = {"destination_path": str(image_file)}
        result = self.plugin.on_file_organized(payload)

        # Should not tag images without EXIF data
        self.assertFalse(result["tagged"])
        self.assertEqual(result["reason"], "no EXIF data found")
```

**Key Features:**

- **Isolated Testing**: Each test gets a fresh temporary directory via `self.test_dir`
- **File Fixtures**: Use `create_test_file()` to create test files with proper paths
- **Path Assertions**: Use `assert_file_exists()` and `assert_file_not_exists()` for verification
- **Automatic Cleanup**: Temporary directories are cleaned up after each test
- **Real Filesystem**: Tests run against actual files, not mocks

### Integration Tests

```python
@pytest.mark.asyncio
async def test_plugin_integration(app_client):
    # List files (path= is optional; omit to list home directory)
    response = await app_client.get(
        "/api/v1/files",
        params={"path": "/test-dir"}
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
