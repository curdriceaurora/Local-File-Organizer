---
issue: 335
title: "Feature Request: Add OpenAI API Support"
epic: phase-3-feature-expansion
analyzed: 2026-02-22T19:41:20Z
estimated_hours: 7
parallelization_factor: 1.75
---

# Parallel Work Analysis: Issue #335

## Overview

Add an `OpenAITextModel` class that implements `BaseModel` using the `openai` Python package, supporting any OpenAI-compatible endpoint (OpenAI, Azure, local proxies like LM Studio). Requires adding `api_key` and `base_url` fields to `ModelConfig`, creating the new provider class, updating exports, and adding comprehensive tests.

Existing pattern (`TextModel` → Ollama) is the template. The new class follows the same `initialize()` / `generate()` / `generate_streaming()` / `cleanup()` contract.

---

## Parallel Streams

### Stream A: Implementation
**Scope**: `ModelConfig` field additions + `OpenAITextModel` class + export updates + optional config/CLI wiring.

**Files**:
- `src/file_organizer/models/base.py` — add `api_key: str | None = None`, `base_url: str | None = None` to `ModelConfig`
- `src/file_organizer/models/openai_model.py` — new file: `OpenAITextModel(BaseModel)`
- `src/file_organizer/models/__init__.py` — export `OpenAITextModel`
- `pyproject.toml` — add `openai` to optional `[project.optional-dependencies]` under a new `[openai]` extra

**Agent Type**: general-purpose
**Can Start**: immediately
**Estimated Hours**: 4
**Dependencies**: none

### Stream B: Tests
**Scope**: Unit tests for `OpenAITextModel` using mocked `openai.OpenAI` client. Tests can be written against the agreed interface before Stream A is merged.

**Files**:
- `tests/models/test_openai_model.py` — new file

**Agent Type**: general-purpose
**Can Start**: immediately (uses mocks — no real OpenAI dependency needed)
**Estimated Hours**: 3
**Dependencies**: none (coordinates on `ModelConfig` field names and class interface)

---

## Coordination Points

### Agreed Interface (Stream B must mock this)

```python
# ModelConfig additions (Stream A touches base.py)
api_key: str | None = None
base_url: str | None = None   # e.g. "https://api.openai.com/v1"

# OpenAITextModel(BaseModel) — new file
class OpenAITextModel(BaseModel):
    def initialize(self) -> None: ...
    def generate(self, prompt: str, **kwargs: Any) -> str: ...
    def generate_streaming(self, prompt: str, **kwargs: Any): ...  # generator
    def cleanup(self) -> None: ...
```

### Shared Files
- `src/file_organizer/models/base.py` — only Stream A modifies this
- `src/file_organizer/models/__init__.py` — only Stream A modifies this
- `tests/models/test_openai_model.py` — only Stream B

**No file conflicts** between streams.

---

## Conflict Risk Assessment
- **Low Risk**: Streams work on non-overlapping files
- Stream B mocks the `openai` client so no real API calls needed

---

## Parallelization Strategy

**Recommended Approach**: parallel

Launch Streams A and B simultaneously. B mocks `openai.OpenAI` so it is independent of A's runtime.

After both complete: verify imports work (`python3 -c "from file_organizer.models import OpenAITextModel"`) and run all new tests.

---

## Expected Timeline

With parallel execution:
- Wall time: ~4 hours
- Total work: 7 hours
- Efficiency gain: 43%

Without parallel execution:
- Wall time: 7 hours

---

## Implementation Notes

### OpenAITextModel design

```python
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

class OpenAITextModel(BaseModel):
    def initialize(self) -> None:
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,   # None → uses OpenAI default
        )
        self._initialized = True

    def generate(self, prompt: str, **kwargs: Any) -> str:
        response = self.client.chat.completions.create(
            model=self.config.name,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        return response.choices[0].message.content or ""
```

### Privacy warning
Document clearly in docstring and README that using cloud models breaks the privacy-first architecture. Users opt in explicitly via `api_key`.

### pyproject.toml optional dependency
```toml
[project.optional-dependencies]
openai = ["openai>=1.0.0"]
```
