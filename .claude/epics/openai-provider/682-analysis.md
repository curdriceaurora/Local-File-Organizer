---
issue: 682
title: "Env var config, optional dep, tests, health endpoint"
analyzed: 2026-03-09T07:26:09Z
estimated_hours: 3
parallelization_factor: 1.0
---

# Analysis: Issue #682

## Sequential — must come after #680 and #681 are both merged.

### Files
- `pyproject.toml` — optional [cloud] dep
- `src/file_organizer/api/service_facade.py` — provider in health response
- `tests/unit/models/test_openai_text_model.py` — new
- `tests/unit/models/test_openai_vision_model.py` — new
- Config loader for FO_PROVIDER, FO_OPENAI_* env vars

## Risk: Low — additive only
