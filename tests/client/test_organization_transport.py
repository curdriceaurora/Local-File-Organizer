"""Tests for lossless organization payload transport in official SDKs."""

from __future__ import annotations

import pytest

from file_organizer.client._organization import organization_request_payload
from file_organizer.client.models import OrganizationOptionsPayload, OrganizationPlanPayload

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def _options() -> OrganizationOptionsPayload:
    return OrganizationOptionsPayload(
        recursive=False,
        include_hidden=True,
        skip_existing=False,
        transfer_mode="copy",
        methodology="para",
        enable_vision=False,
        transcribe_audio=True,
        max_transcribe_seconds=42.5,
        whisper_model="base",
        parallel_workers=3,
        prefetch_depth=4,
        text_model="text-custom",
        vision_model="vision-custom",
        text_provider="openai",
        vision_provider="openai",
    )


def _plan() -> OrganizationPlanPayload:
    return OrganizationPlanPayload(
        plan_id="plan-1",
        schema_version=3,
        input_path="/workspace/in",
        output_path="/workspace/out",
        created_at="2026-07-21T12:00:00+00:00",
        skip_existing=False,
        use_hardlinks=False,
        total_files=0,
        processed_files=0,
        skipped_files=0,
        failed_files=0,
        deduplicated_files=0,
        options=_options(),
        operations=[],
        errors=[],
        metadata={"source": "sdk-test"},
    )


def test_payload_preserves_options_plan_and_idempotency_key() -> None:
    options = _options()
    plan = _plan()

    payload = organization_request_payload(
        "/workspace/in",
        "/workspace/out",
        options=options,
        plan=plan,
        dry_run=False,
        run_in_background=True,
        skip_existing=None,
        use_hardlinks=None,
        idempotency_key="request-123",
    )

    assert payload["options"] == options.model_dump(mode="json")
    assert payload["plan"] == plan.model_dump(mode="json")
    assert payload["idempotency_key"] == "request-123"
    assert "skip_existing" not in payload
    assert "use_hardlinks" not in payload


def test_plan_model_round_trips_schema_three_options_without_loss() -> None:
    plan = _plan()

    restored = OrganizationPlanPayload.model_validate(plan.model_dump(mode="json"))

    assert restored == plan
    assert restored.options == _options()
