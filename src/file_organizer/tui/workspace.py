"""Shared state for the connected Textual workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from file_organizer.config.manager import ConfigManager
from file_organizer.core.capabilities import Surface, get_capability_registry
from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.lifecycle import JobSnapshot
from file_organizer.core.organize_options import OrganizeOptions, OrganizeRequest
from file_organizer.core.plan import OrganizationPlan
from file_organizer.core.types import OrganizationResult


@dataclass(slots=True)
class TUIWorkspace:
    """Session state shared by all eight TUI views.

    Empty roots are represented by ``None`` so no workflow silently falls back
    to the process working directory.
    """

    active_root: Path | None = None
    output_root: Path | None = None
    selected_files: set[Path] = field(default_factory=set)
    options: OrganizeOptions = field(default_factory=OrganizeOptions)
    reviewed_plan: OrganizationPlan | None = None
    active_job: JobSnapshot | None = None
    last_result: OrganizationResult | None = None
    last_error: DomainError | None = None

    @classmethod
    def from_config(cls, manager: ConfigManager | None = None) -> TUIWorkspace:
        """Build initial session state from explicit persisted defaults."""
        resolved_manager = manager or ConfigManager()
        try:
            config = resolved_manager.load()
        except Exception as exc:
            workspace = cls()
            workspace.record_error(exc)
            return workspace

        parallel = config.parallel or {}
        workers = parallel.get("max_workers")
        prefetch_depth = parallel.get("prefetch_depth", 2)
        try:
            # text_provider/vision_provider are deliberately left unset here (#1660):
            # a request-level OrganizeOptions field outranks FO_PROVIDER in
            # OrganizationService._resolve_options, so eagerly copying the persisted
            # config.models.framework value in would make it silently beat the
            # environment variable on every session, before the user ever makes an
            # explicit choice. Settings still displays the persisted value (seeded
            # from config, not from these options) and only writes it into session
            # options once the user explicitly cycles the provider control.
            options = OrganizeOptions(
                methodology=config.default_methodology,
                parallel_workers=workers,
                prefetch_depth=prefetch_depth,
                text_model=config.models.text_model,
                vision_model=config.models.vision_model,
            )
        except (TypeError, ValueError):
            options = OrganizeOptions()
        input_dir = config.default_input_dir
        output_dir = config.default_output_dir
        return cls(
            active_root=(
                Path(input_dir) if isinstance(input_dir, (str, Path)) and str(input_dir) else None
            ),
            output_root=(
                Path(output_dir)
                if isinstance(output_dir, (str, Path)) and str(output_dir)
                else None
            ),
            options=options,
        )

    def set_roots(self, input_path: str | Path, output_path: str | Path) -> None:
        """Set explicit workflow roots and invalidate any reviewed plan."""
        source = str(input_path).strip()
        destination = str(output_path).strip()
        active_root = Path(source).expanduser() if source else None
        output_root = Path(destination).expanduser() if destination else None
        roots_changed = (active_root, output_root) != (self.active_root, self.output_root)
        self.active_root = active_root
        self.output_root = output_root
        self.reviewed_plan = None
        if roots_changed:
            self.active_job = None
            self.last_result = None
        self.last_error = None
        if self.active_root is not None:
            self.selected_files = {
                path for path in self.selected_files if path.is_relative_to(self.active_root)
            }
        else:
            self.selected_files.clear()

    def set_options(self, **changes: Any) -> None:
        """Update canonical session options and invalidate the reviewed plan."""
        payload = self.options.to_dict()
        payload.update(changes)
        self.options = OrganizeOptions.from_dict(payload)
        self.reviewed_plan = None
        self.last_error = None

    def set_selected_files(self, paths: set[Path]) -> None:
        """Persist the selected-file context across view switches."""
        self.selected_files = {Path(path).expanduser() for path in paths}
        self.reviewed_plan = None

    def request(self) -> OrganizeRequest:
        """Return the canonical request or an actionable missing-root error."""
        missing = []
        if self.active_root is None:
            missing.append("source")
        if self.output_root is None:
            missing.append("output")
        if missing:
            raise DomainError(
                DomainErrorCode.INVALID_REQUEST,
                f"Set explicit {' and '.join(missing)} directories in Settings before preview.",
                details={"missing": missing, "action": "Open Settings (7)"},
            )
        return OrganizeRequest(
            cast(Path, self.active_root),
            cast(Path, self.output_root),
            self.options,
        )

    def capability_status(self, capability_id: str) -> str:
        """Return the registry-backed TUI support label for a capability."""
        capability = get_capability_registry().get(capability_id)
        support = capability.support_for(Surface.TUI)
        return f"{support.implementation_status.value}/{support.conformance_status.value}"

    def record_error(self, exc: Exception) -> None:
        """Retain a domain failure without changing its meaning."""
        if isinstance(exc, DomainError):
            self.last_error = exc
        else:
            self.last_error = DomainError(
                DomainErrorCode.EXECUTION_FAILED,
                str(exc) or type(exc).__name__,
                details={"error_type": type(exc).__name__},
            )
