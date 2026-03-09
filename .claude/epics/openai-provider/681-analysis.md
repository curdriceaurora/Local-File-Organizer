---
issue: 681
title: "OpenAITextModel + OpenAIVisionModel implementations"
analyzed: 2026-03-09T07:26:09Z
estimated_hours: 4
parallelization_factor: 1.0
---

# Analysis: Issue #681

## Can run in parallel with #680 since it only creates new files.
## Needs ModelConfig.api_key + api_base_url fields from #680 before integrating.

### New files
- `src/file_organizer/models/openai_text_model.py`
- `src/file_organizer/models/openai_vision_model.py`

## Risk: Low — new files only, no changes to existing code
