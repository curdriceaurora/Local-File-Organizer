---
created: 2026-03-08T23:57:34Z
last_updated: 2026-03-09T07:37:36Z
version: 1.1
author: Claude Code PM System
---

# System Patterns

> **Anti-patterns to avoid when implementing**: `.claude/rules/feature-generation-patterns.md`
> Covers: F1 missing error handling, F2 type annotations, F3 thread safety,
> F4 security (auth tokens, path traversal), F5 hardcoded values, F8 wrong abstraction layer.

## Architecture Style

**Privacy-first, plugin-extensible, event-driven monolith** with clear service layer separation.

## Core Patterns

### 1. Service Layer Pattern

Business logic lives in `services/`, never in route handlers or CLI commands.

```python
# Route delegates to service
@router.post("/organize")
async def organize(request: ..., svc: OrganizeService = Depends(...)):
    return await svc.organize(request)

# Service owns logic
class OrganizeService:
    async def organize(self, request) -> OrganizeResult:
        ...
```

### 2. Fallback Chain Pattern

Used throughout for optional dependencies (ffprobe → OpenCV → filesystem-only):

```python
def extract(self, path):
    if self._try_ffprobe(path, metadata):
        return metadata
    if self._try_opencv(path, metadata):
        return metadata
    return metadata  # filesystem baseline
```

### 3. Event Bus (Loose Coupling)

`events/` module provides publish/subscribe for decoupled components:

```python
event_bus.publish(FileOrganizedEvent(path=path, destination=dest))
# Listeners (analytics, history, plugins) react independently
```

### 4. Plugin Architecture

`plugins/` provides a marketplace with hot-loadable plugins following `PluginBase` interface:

```python
class MyPlugin(PluginBase):
    def get_metadata(self) -> PluginMetadata: ...
    def execute(self, context: PluginContext) -> PluginResult: ...
```

### 5. Context Manager Resources

All model/session resources use context managers:

```python
with VisionProcessor() as processor:
    result = processor.process_file(path)
# Guaranteed cleanup via __exit__
```

### 6. Dataclass-Based DTOs

All data transfer between layers uses `@dataclass`, not dicts:

```python
@dataclass
class ProcessedImage:
    file_path: Path
    description: str
    folder_name: str
    # ...
```

## AI Integration Pattern

```
User Request
    ↓
Service Layer
    ↓
Model Manager (manages lifecycle, device selection)
    ↓
Model Wrapper (AudioTranscriber / VisionModel / TextModel)
    ↓
Ollama / faster-whisper (local inference)
```

## Configuration Pattern

All paths and settings flow through `ConfigManager` — never hardcoded:

```python
from file_organizer.config import ConfigManager
trash = ConfigManager.get_path("trash")  # ✅
trash = Path("~/.config/file-organizer/trash")  # ❌
```

## Testing Patterns

- **Unit tests**: Mock all external dependencies (Ollama, PIL, ffprobe, cv2)
- **Fixtures**: `mock_text_model`, `mock_ollama`, `tmp_path` for hermetic isolation
- **Integration tests**: Marked `@pytest.mark.integration`, skipped in PR CI
- **Smoke tests**: Marked `@pytest.mark.smoke`, fastest subset
- **CI tests**: Marked `@pytest.mark.ci`, run in PR CI (no coverage gate)

## Error Handling Pattern

```python
def process_file(path: Path) -> ProcessResult:
    try:
        content = self.reader.read(path)
    except FileNotFoundError:
        logger.warning("File not found: %s", path)
        return ProcessResult(success=False, error=f"Not found: {path}")
    except PermissionError as e:
        raise ProcessingError(f"Cannot read {path}") from e
    return self._analyze(content)
```

## Methodology Strategy Pattern

Organization strategies are interchangeable:

```python
class PARAStrategy(OrganizationStrategy):
    def categorize(self, metadata: FileMetadata) -> str: ...

class JohnnyDecimalStrategy(OrganizationStrategy):
    def categorize(self, metadata: FileMetadata) -> str: ...
```

## Provider Factory Pattern (In Progress — Issue #335)

Models are selected via a provider factory rather than direct instantiation, enabling
Ollama and OpenAI-compatible endpoints (LM Studio, Groq, etc.) to be swapped via config:

```python
# ModelConfig drives provider selection
config = ModelConfig(provider="openai", api_base_url="http://localhost:1234/v1", api_key="lm-studio")

# Factory returns correct implementation
model = provider_factory.get_model(config)
# provider == "ollama"  → TextModel / VisionModel (existing)
# provider == "openai"  → OpenAITextModel / OpenAIVisionModel (new)

# Organizer uses factory instead of direct construction
class FileOrganizer:
    def organize(self, ...):
        model = provider_factory.get_model(self.config)
        ...
```

Key files (planned):
- `src/file_organizer/models/base.py` — add `provider`, `api_key`, `api_base_url` to `ModelConfig`
- `src/file_organizer/models/provider_factory.py` — new factory module
- `src/file_organizer/models/openai_text_model.py` — new OpenAI wrapper
- `src/file_organizer/models/openai_vision_model.py` — new OpenAI wrapper
