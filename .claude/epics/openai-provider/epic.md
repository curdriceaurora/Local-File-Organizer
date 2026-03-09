---
name: openai-provider
title: OpenAI-Compatible Provider Tier (Issue #335)
status: completed
created: 2026-03-09T07:25:04Z
updated: 2026-03-09T08:17:48Z
progress: 100%
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/335
---

# Epic: OpenAI-Compatible Provider Tier

## Overview

Add a second model provider alongside Ollama that speaks the OpenAI API format.
Because the `openai` Python SDK accepts any `base_url`, one implementation
covers both cloud (OpenAI, Groq, Together.ai) and local (LM Studio, Ollama's
own OpenAI-compatible endpoint, vLLM) providers.

This completes the "Local First" two-tier positioning:
- **Tier 2** — Ollama (existing, local, zero cloud)
- **Tier 3** — OpenAI-compatible endpoint (user-configured, opt-in)

## Architecture

```
ModelConfig
  └─ provider: "ollama" | "openai"
  └─ api_key, api_base_url (for openai provider)

provider_factory.get_model(config)
  ├─ provider == "ollama" → TextModel / VisionModel (existing)
  └─ provider == "openai" → OpenAITextModel / OpenAIVisionModel (new)

FileOrganizer.organize()
  └─ calls get_model(config) instead of TextModel(config) directly
```

## Provider Coverage via api_base_url

| Provider | base_url | Local? |
|----------|----------|--------|
| OpenAI | https://api.openai.com/v1 | ❌ |
| LM Studio | http://localhost:1234/v1 | ✅ |
| Ollama (OpenAI compat) | http://localhost:11434/v1 | ✅ |
| Groq | https://api.groq.com/openai/v1 | ❌ |
| Together.ai | https://api.together.xyz/v1 | ❌ |

## User-Facing Config

```bash
FO_PROVIDER=openai           # or "ollama" (default)
FO_OPENAI_API_KEY=sk-...
FO_OPENAI_BASE_URL=https://api.openai.com/v1
FO_OPENAI_MODEL=gpt-4o
FO_OPENAI_VISION_MODEL=gpt-4o  # optional, defaults to FO_OPENAI_MODEL
```

## Tasks

- [ ] #680 — ModelConfig provider fields + provider_factory + organizer routing (Stream A)
- [ ] #681 — OpenAITextModel + OpenAIVisionModel implementations (Stream B)
- [ ] #682 — Tests + env var config + optional dependency (Stream C)

## Success Criteria

- `FO_PROVIDER=openai FO_OPENAI_API_KEY=sk-... fo organize ~/Downloads` works end-to-end
- `FO_OPENAI_BASE_URL=http://localhost:1234/v1` works with LM Studio (local, no key needed)
- Ollama path (existing) unchanged — no regression
- `pip install file-organizer[cloud]` installs openai SDK
- Health endpoint reports provider type in status response

## Dependencies

- `provider-resilience` epic (#677 graceful degradation) — merged ✅
- No other blockers
