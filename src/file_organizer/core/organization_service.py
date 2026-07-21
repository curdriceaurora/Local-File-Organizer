"""Direct application service for canonical organization behavior."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from file_organizer.core import file_ops
from file_organizer.core.organize_options import (
    OrganizeOptions,
    OrganizeRequest,
    TransferMode,
)
from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import OrganizationPlan
from file_organizer.core.types import (
    AUDIO_EXTENSIONS,
    CAD_EXTENSIONS,
    IMAGE_EXTENSIONS,
    TEXT_EXTENSIONS,
    VIDEO_EXTENSIONS,
    OrganizationResult,
)
from file_organizer.models.base import ModelConfig


@dataclass(frozen=True, slots=True)
class OrganizationScan:
    """Deterministic direct-service scan result."""

    input_path: Path
    files: tuple[Path, ...]
    counts: dict[str, int]

    @property
    def total_files(self) -> int:
        """Return the number of eligible files."""
        return len(self.files)


OrganizerFactory = Callable[..., FileOrganizer]


class OrganizationService:
    """Transport-neutral entry point for scan, preview, and execution."""

    def __init__(
        self,
        *,
        text_model_config: ModelConfig | None = None,
        vision_model_config: ModelConfig | None = None,
        organizer_factory: OrganizerFactory = FileOrganizer,
    ) -> None:
        """Initialize the service with optional model and organizer dependencies."""
        if text_model_config is None or vision_model_config is None:
            from file_organizer.config.provider_env import get_model_configs

            default_text, default_vision = get_model_configs()
            text_model_config = text_model_config or default_text
            vision_model_config = vision_model_config or default_vision
        self._text_model_config = text_model_config
        self._vision_model_config = vision_model_config
        self._organizer_factory = organizer_factory

    def scan(self, request: OrganizeRequest) -> OrganizationScan:
        """Collect exactly the files that preview and execution will consume."""
        if not request.input_path.exists():
            raise ValueError(f"Input path does not exist: {request.input_path}")
        files = tuple(
            file_ops.collect_files(
                request.input_path,
                recursive=request.options.recursive,
                include_hidden=request.options.include_hidden,
            )
        )
        counts = dict.fromkeys(("text", "image", "video", "audio", "cad", "other"), 0)
        for path in files:
            extension = path.suffix.lower()
            if extension in TEXT_EXTENSIONS:
                counts["text"] += 1
            elif extension in IMAGE_EXTENSIONS:
                counts["image"] += 1
            elif extension in VIDEO_EXTENSIONS:
                counts["video"] += 1
            elif extension in AUDIO_EXTENSIONS:
                counts["audio"] += 1
            elif extension in CAD_EXTENSIONS:
                counts["cad"] += 1
            else:
                counts["other"] += 1
        return OrganizationScan(request.input_path, files, counts)

    def preview(self, request: OrganizeRequest) -> OrganizationResult:
        """Build a canonical executable plan without mutating the filesystem."""
        organizer = self._create_organizer(self._resolve_options(request.options), dry_run=True)
        return organizer.organize(
            request.input_path,
            request.output_path,
            skip_existing=request.options.skip_existing,
        )

    def execute(
        self,
        request: OrganizeRequest,
        plan: OrganizationPlan | None = None,
    ) -> OrganizationResult:
        """Apply a reviewed plan, or build and apply one through the same contract."""
        if plan is None:
            preview = self.preview(request)
            if not isinstance(preview.plan, OrganizationPlan):
                raise RuntimeError("Organization preview did not produce an executable plan.")
            plan = preview.plan
        if not plan.roots_match(request.input_path, request.output_path):
            raise ValueError("Organization plan roots do not match request paths.")
        resolved_options = self._resolve_options(request.options)
        if plan.options != resolved_options:
            raise ValueError("Organization plan options do not match request options.")
        return self._create_organizer(resolved_options, dry_run=False).execute_plan(plan)

    def _resolve_options(self, options: OrganizeOptions) -> OrganizeOptions:
        """Resolve configured model defaults into reproducible plan values."""
        return replace(
            options,
            text_model=options.text_model or self._text_model_config.name,
            vision_model=options.vision_model or self._vision_model_config.name,
            text_provider=options.text_provider or self._text_model_config.provider,
            vision_provider=options.vision_provider or self._vision_model_config.provider,
        )

    def _create_organizer(self, options: OrganizeOptions, *, dry_run: bool) -> FileOrganizer:
        """Map canonical options into the existing domain orchestrator."""
        text_model_config = replace(
            self._text_model_config,
            name=options.text_model or self._text_model_config.name,
            provider=options.text_provider or self._text_model_config.provider,
        )
        vision_model_config = replace(
            self._vision_model_config,
            name=options.vision_model or self._vision_model_config.name,
            provider=options.vision_provider or self._vision_model_config.provider,
        )
        return self._organizer_factory(
            text_model_config=text_model_config,
            vision_model_config=vision_model_config,
            dry_run=dry_run,
            use_hardlinks=options.effective_transfer_mode == TransferMode.HARDLINK,
            parallel_workers=options.parallel_workers,
            prefetch_depth=options.prefetch_depth,
            enable_vision=options.enable_vision,
            transcribe_audio=options.transcribe_audio,
            max_transcribe_seconds=options.max_transcribe_seconds,
            whisper_model=options.whisper_model,
            recursive=options.recursive,
            include_hidden=options.include_hidden,
            organize_options=options,
        )
