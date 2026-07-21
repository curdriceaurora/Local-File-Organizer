"""Canonical, transport-neutral organization request contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

ModelProvider = Literal["ollama", "openai", "llama_cpp", "mlx", "claude"]


@dataclass(frozen=True, slots=True)
class OrganizeOptions:
    """Behavior-affecting options shared by every organization surface.

    ``use_hardlinks`` is the existing transfer selector.  Parity slice #1602
    will replace it with the canonical transfer-mode contract while retaining
    plan compatibility.
    """

    recursive: bool = True
    include_hidden: bool = False
    skip_existing: bool = True
    use_hardlinks: bool = True
    enable_vision: bool = True
    transcribe_audio: bool = False
    max_transcribe_seconds: float | None = 600.0
    whisper_model: str = "tiny"
    parallel_workers: int | None = None
    prefetch_depth: int = 2
    text_model: str | None = None
    vision_model: str | None = None
    text_provider: ModelProvider | None = None
    vision_provider: ModelProvider | None = None

    def __post_init__(self) -> None:
        """Reject invalid combinations before filesystem or model work starts."""
        for field_name in (
            "recursive",
            "include_hidden",
            "skip_existing",
            "use_hardlinks",
            "enable_vision",
            "transcribe_audio",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be a boolean")
        if isinstance(self.parallel_workers, bool) or (
            self.parallel_workers is not None and not isinstance(self.parallel_workers, int)
        ):
            raise ValueError("parallel_workers must be an integer or None")
        if isinstance(self.prefetch_depth, bool) or not isinstance(self.prefetch_depth, int):
            raise ValueError("prefetch_depth must be an integer")
        if isinstance(self.max_transcribe_seconds, bool) or (
            self.max_transcribe_seconds is not None
            and not isinstance(self.max_transcribe_seconds, (int, float))
        ):
            raise ValueError("max_transcribe_seconds must be a number or None")
        if self.parallel_workers is not None and self.parallel_workers < 1:
            raise ValueError("parallel_workers must be at least 1 or None")
        if self.prefetch_depth < 0:
            raise ValueError("prefetch_depth must be at least 0")
        if self.max_transcribe_seconds is not None and self.max_transcribe_seconds < 0:
            raise ValueError("max_transcribe_seconds must be at least 0 or None")
        if not isinstance(self.whisper_model, str) or not self.whisper_model.strip():
            raise ValueError("whisper_model must not be empty")
        if self.text_model is not None and (
            not isinstance(self.text_model, str) or not self.text_model.strip()
        ):
            raise ValueError("text_model must not be empty when provided")
        if self.vision_model is not None and (
            not isinstance(self.vision_model, str) or not self.vision_model.strip()
        ):
            raise ValueError("vision_model must not be empty when provided")
        supported_providers = {"ollama", "openai", "llama_cpp", "mlx", "claude"}
        for field_name in ("text_provider", "vision_provider"):
            provider = getattr(self, field_name)
            if provider is not None and provider not in supported_providers:
                raise ValueError(f"{field_name} is not a supported model provider")

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OrganizeOptions:
        """Parse an options payload, applying defaults for omitted fields."""
        if not isinstance(data, Mapping):
            raise ValueError("organization options must be an object")
        known_fields = set(cls.__dataclass_fields__)
        unknown_fields = set(data) - known_fields
        if unknown_fields:
            names = ", ".join(sorted(str(field) for field in unknown_fields))
            raise ValueError(f"unknown organization option fields: {names}")
        return cls(**dict(data))


@dataclass(frozen=True, slots=True)
class OrganizeRequest:
    """Canonical request consumed by the direct organization service."""

    input_path: Path
    output_path: Path
    options: OrganizeOptions = OrganizeOptions()

    def __post_init__(self) -> None:
        """Normalize path-like values without resolving untrusted filesystem state."""
        if not isinstance(self.options, OrganizeOptions):
            raise ValueError("options must be an OrganizeOptions instance")
        object.__setattr__(self, "input_path", Path(self.input_path))
        object.__setattr__(self, "output_path", Path(self.output_path))
