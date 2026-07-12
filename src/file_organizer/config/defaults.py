"""Canonical default model names and Ollama endpoint.

Single source of truth for the recommended text/vision models and the
default Ollama URL, referenced by config schemas, the TUI, the web UI, the
API, and the model registries. Previously these were hardcoded
independently in 15+ places (some self-documented as fragile, e.g.
``core/hardware_profile.py``'s "must match models/registry.py" comment)
with no single point of truth, making a default-model or endpoint change a
repo-wide grep-and-replace — see #1541.
"""

from __future__ import annotations

DEFAULT_TEXT_MODEL = "qwen2.5:3b-instruct-q4_K_M"
DEFAULT_TEXT_MODEL_LARGE = "qwen2.5:7b-instruct-q4_K_M"
DEFAULT_VISION_MODEL = "qwen2.5vl:7b-q4_K_M"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
