---
issue: 680
title: "ModelConfig provider fields + provider_factory + organizer routing"
analyzed: 2026-03-09T07:26:09Z
estimated_hours: 3
parallelization_factor: 1.0
---

# Analysis: Issue #680

## Streams

### Stream A: ModelConfig + factory (can start immediately)
- `src/file_organizer/models/base.py` — add provider, api_key, api_base_url fields
- `src/file_organizer/models/provider_factory.py` — new file
- `src/file_organizer/models/__init__.py` — export factory

### Stream B: Organizer routing (after Stream A)
- `src/file_organizer/core/organizer.py` — use factory instead of direct model construction

## Risk: Low — additive changes, Ollama default preserves existing behavior
