"""Canonical organization adapter for the Textual workspace."""

from __future__ import annotations

from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.organization_service import OrganizationScan, OrganizationService
from file_organizer.core.organize_options import OrganizeRequest
from file_organizer.core.plan import OrganizationPlan
from file_organizer.core.types import OrganizationResult
from file_organizer.tui.workspace import TUIWorkspace


class TUIOrganizationAdapter:
    """Map shared TUI state onto the transport-neutral organization service."""

    def __init__(
        self,
        workspace: TUIWorkspace,
        service: OrganizationService | None = None,
    ) -> None:
        """Bind a session workspace to one canonical service instance."""
        self.workspace = workspace
        self.service = service or OrganizationService()

    def scan(self) -> OrganizationScan:
        """Scan the active root using the exact options visible in the TUI."""
        return self.service.scan(self.request())

    def preview(self) -> OrganizationResult:
        """Build and retain the canonical executable plan for confirmation."""
        try:
            result = self.service.preview(self.request())
            if not isinstance(result.plan, OrganizationPlan):
                raise DomainError(
                    DomainErrorCode.EXECUTION_FAILED,
                    "Organization preview did not produce an executable plan.",
                )
        except Exception as exc:
            self.workspace.record_error(exc)
            raise
        self.workspace.reviewed_plan = result.plan
        self.workspace.last_error = None
        return result

    def execute(self, plan: OrganizationPlan | None = None) -> OrganizationResult:
        """Execute the reviewed plan unchanged through the canonical service."""
        reviewed_plan = plan or self.workspace.reviewed_plan
        if reviewed_plan is None:
            error = DomainError(
                DomainErrorCode.INVALID_REQUEST,
                "Refresh and review an organization plan before applying it.",
            )
            self.workspace.record_error(error)
            raise error
        try:
            result = self.service.execute(self.request(), reviewed_plan)
        except Exception as exc:
            self.workspace.record_error(exc)
            raise
        self.workspace.reviewed_plan = reviewed_plan
        self.workspace.last_result = result
        self.workspace.last_error = None
        return result

    def request(self) -> OrganizeRequest:
        """Resolve the supported TUI scope without silently widening selection."""
        if self.workspace.selected_files:
            raise DomainError(
                DomainErrorCode.OPTIONAL_FEATURE_UNAVAILABLE,
                "Selected-file-only organization is not supported by the canonical service; "
                "clear the selection to organize the active root.",
                details={
                    "feature": "selected-file-scope",
                    "selected_files": len(self.workspace.selected_files),
                },
            )
        return self.workspace.request()
