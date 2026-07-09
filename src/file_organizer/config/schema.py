"""Configuration schema for File Organizer.

Defines the top-level AppConfig and ModelPreset dataclasses that provide
a unified configuration interface across all modules.

Field-level bounds (temperature, max_tokens, …) are validated by
``SetupWizard.validate_config`` (construct-then-validate, returning
user-facing error messages) rather than raising in ``__post_init__`` — see
WP-3.2 / #1230. This module owns the schema-version constants and the plain
dataclass shape; ``ConfigManager`` owns version-compatibility (migration-safe
fallback) and atomic persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Schema-version constants. ``CURRENT_SCHEMA_VERSION`` is what new configs are
# written as; ``SUPPORTED_SCHEMA_VERSIONS`` is the set ConfigManager will load
# without falling back to defaults. It is derived from CURRENT_SCHEMA_VERSION so
# the two cannot drift; extend it explicitly (e.g.
# ``frozenset({CURRENT_SCHEMA_VERSION, "1.0"})``) once a migration exists.
CURRENT_SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({CURRENT_SCHEMA_VERSION})


@dataclass
class ModelPreset:
    """Preset configuration for AI models.

    Args:
        text_model: Ollama model name for text processing.
        vision_model: Ollama model name for vision processing.
        temperature: Generation temperature (0.0-1.0).
        max_tokens: Maximum tokens for generation.
        device: Device for inference (auto, cpu, cuda, mps, metal).
        framework: Inference framework (ollama, llama_cpp, mlx).
    """

    text_model: str = "qwen2.5:3b-instruct-q4_K_M"
    vision_model: str = "qwen2.5vl:7b-q4_K_M"
    temperature: float = 0.5
    max_tokens: int = 3000
    device: str = "auto"
    framework: str = "ollama"


@dataclass
class UpdateSettings:
    """Auto-update preferences.

    Args:
        check_on_startup: Check for updates when the app launches.
        interval_hours: Minimum hours between update checks.
        include_prereleases: Include pre-release versions.
        repo: GitHub repository used for update checks.
    """

    check_on_startup: bool = True
    interval_hours: int = 24
    include_prereleases: bool = False
    repo: str = "curdriceaurora/Local-File-Organizer"


@dataclass
class AppConfig:
    """Top-level application configuration.

    All fields have defaults so ``AppConfig()`` works standalone.
    Module-specific configs are optional and only loaded when their
    feature is used.

    Args:
        profile_name: Name of this configuration profile.
        version: Configuration schema version.
        default_methodology: Default organization methodology (none, para, jd).
        default_input_dir: Default source directory pre-filled for organize runs
            (empty string means "unset — prompt each run").
        default_output_dir: Default destination directory pre-filled for organize
            runs (empty string means "unset — prompt each run").
        setup_completed: Whether the guided setup wizard has been completed.
        setup_deferred: Whether the user has chosen to finish guided setup later.
        models: AI model preset configuration.
        updates: Auto-update preferences.
        watcher: Watcher module config overrides.
        daemon: Daemon module config overrides.
        parallel: Parallel processing config overrides.
        pipeline: Pipeline config overrides.
        events: Event system config overrides.
        deploy: Deployment config overrides.
        para: PARA methodology config overrides.
        johnny_decimal: Johnny Decimal config overrides.
    """

    profile_name: str = "default"
    version: str = CURRENT_SCHEMA_VERSION
    default_methodology: str = "none"
    default_input_dir: str = ""
    default_output_dir: str = ""
    setup_completed: bool = False
    setup_deferred: bool = False
    models: ModelPreset = field(default_factory=ModelPreset)
    updates: UpdateSettings = field(default_factory=UpdateSettings)

    # Module-specific config overrides stored as dicts.
    # Delegated to module config constructors by ConfigManager.
    watcher: dict[str, Any] | None = None
    daemon: dict[str, Any] | None = None
    parallel: dict[str, Any] | None = None
    pipeline: dict[str, Any] | None = None
    events: dict[str, Any] | None = None
    deploy: dict[str, Any] | None = None
    para: dict[str, Any] | None = None
    johnny_decimal: dict[str, Any] | None = None
