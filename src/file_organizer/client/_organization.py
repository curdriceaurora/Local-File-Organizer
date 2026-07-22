"""Shared organization request serialization for official SDK clients."""

from __future__ import annotations

from typing import Any

from file_organizer.client.models import OrganizationOptionsPayload, OrganizationPlanPayload


def organization_request_payload(
    input_dir: str,
    output_dir: str,
    *,
    options: OrganizationOptionsPayload | None,
    plan: OrganizationPlanPayload | None,
    dry_run: bool,
    run_in_background: bool,
    skip_existing: bool | None,
    use_hardlinks: bool | None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Build one lossless payload shared by synchronous and asynchronous clients."""
    payload: dict[str, Any] = {
        "input_dir": input_dir,
        "output_dir": output_dir,
        "dry_run": dry_run,
        "run_in_background": run_in_background,
    }
    if options is not None:
        payload["options"] = options.model_dump(mode="json")
    if plan is not None:
        payload["plan"] = plan.model_dump(mode="json")
    if skip_existing is not None:
        payload["skip_existing"] = skip_existing
    if use_hardlinks is not None:
        payload["use_hardlinks"] = use_hardlinks
    if idempotency_key is not None:
        payload["idempotency_key"] = idempotency_key
    return payload
