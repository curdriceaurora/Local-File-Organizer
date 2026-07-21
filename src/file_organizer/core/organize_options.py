"""Canonical, transport-neutral organization request contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from file_organizer._compat import StrEnum

ModelProvider = Literal["ollama", "openai", "llama_cpp", "mlx", "claude"]


class TransferMode(StrEnum):
    """Canonical filesystem transfer behavior supported by organization."""

    COPY = "copy"
    HARDLINK = "hardlink"


class OrganizationMethodology(StrEnum):
    """Canonical destination-layout policies supported by organization."""

    NONE = "none"
    PARA = "para"
    JOHNNY_DECIMAL = "jd"


def _resolve_transfer_mode(
    transfer_mode: TransferMode | str | None,
    use_hardlinks: bool | None,
) -> TransferMode:
    """Normalize canonical and legacy transfer selectors into one mode."""
    if use_hardlinks is not None and not isinstance(use_hardlinks, bool):
        raise ValueError("use_hardlinks must be a boolean or None")
    if transfer_mode is None:
        return TransferMode.HARDLINK if use_hardlinks is not False else TransferMode.COPY
    try:
        resolved = TransferMode(transfer_mode)
    except (TypeError, ValueError) as exc:
        if str(transfer_mode) == "move":
            raise ValueError(
                "transfer_mode 'move' is not supported; use 'copy' or 'hardlink'"
            ) from exc
        raise ValueError("transfer_mode must be 'copy' or 'hardlink'") from exc
    if use_hardlinks is not None and use_hardlinks != (resolved == TransferMode.HARDLINK):
        raise ValueError("use_hardlinks conflicts with transfer_mode")
    return resolved


def _resolve_methodology(
    methodology: OrganizationMethodology | str,
) -> OrganizationMethodology:
    """Normalize and validate the destination-layout methodology."""
    try:
        return OrganizationMethodology(methodology)
    except (TypeError, ValueError) as exc:
        raise ValueError("methodology must be 'none', 'para', or 'jd'") from exc


@dataclass(frozen=True, slots=True)
class OrganizeOptions:
    """Behavior-affecting options shared by every organization surface.

    ``transfer_mode`` is the canonical selector. ``use_hardlinks`` remains an
    input-only compatibility alias for callers that have not migrated yet;
    :meth:`to_dict` emits only ``transfer_mode``. True move is deliberately
    unsupported until crash-safe source deletion and cross-device recovery are
    specified by the lifecycle contract.
    """

    recursive: bool = True
    include_hidden: bool = False
    skip_existing: bool = True
    transfer_mode: TransferMode | str | None = None
    use_hardlinks: bool | None = None
    methodology: OrganizationMethodology | str = OrganizationMethodology.NONE
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
        transfer_mode = _resolve_transfer_mode(self.transfer_mode, self.use_hardlinks)
        methodology = _resolve_methodology(self.methodology)
        object.__setattr__(self, "transfer_mode", transfer_mode)
        object.__setattr__(self, "use_hardlinks", transfer_mode == TransferMode.HARDLINK)
        object.__setattr__(self, "methodology", methodology)

        for field_name in (
            "recursive",
            "include_hidden",
            "skip_existing",
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
        """Return the stable canonical representation without legacy aliases."""
        data = asdict(self)
        data.pop("use_hardlinks")
        data["transfer_mode"] = self.effective_transfer_mode.value
        data["methodology"] = self.effective_methodology.value
        return data

    @property
    def effective_transfer_mode(self) -> TransferMode:
        """Return the validated canonical transfer mode."""
        return cast(TransferMode, self.transfer_mode)

    @property
    def effective_methodology(self) -> OrganizationMethodology:
        """Return the validated canonical methodology."""
        return cast(OrganizationMethodology, self.methodology)

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
