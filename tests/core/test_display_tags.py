"""Tests for display show_summary tags formatting (#1760)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.core.display import show_summary
from file_organizer.core.plan import (
    CollisionAction,
    OrganizationOperation,
    OrganizationOperationStatus,
    OrganizationOperationType,
    OrganizationPlan,
)
from file_organizer.core.types import OrganizationResult

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_show_summary_displays_tags_suffix(tmp_path: Path) -> None:
    console = MagicMock()
    plan = OrganizationPlan(
        plan_id="plan-1",
        schema_version=3,
        input_path=str(tmp_path),
        output_path=str(tmp_path / "out"),
        created_at="2026-09-03T00:00:00Z",
        skip_existing=False,
        use_hardlinks=False,
        total_files=2,
        processed_files=2,
        skipped_files=0,
        failed_files=0,
        deduplicated_files=0,
        operations=[
            OrganizationOperation(
                operation_id="op1",
                source_path=str(tmp_path / "invoice.pdf"),
                destination_path=str(tmp_path / "out/finances/invoice.pdf"),
                operation_type=OrganizationOperationType.COPY,
                collision_action=CollisionAction.CREATE,
                status=OrganizationOperationStatus.READY,
                folder_name="finances",
                file_name="invoice.pdf",
                tags=["finance", "invoice", "october"],
            ),
            OrganizationOperation(
                operation_id="op2",
                source_path=str(tmp_path / "notes.txt"),
                destination_path=str(tmp_path / "out/notes/notes.txt"),
                operation_type=OrganizationOperationType.COPY,
                collision_action=CollisionAction.CREATE,
                status=OrganizationOperationStatus.READY,
                folder_name="notes",
                file_name="notes.txt",
                tags=[],
            ),
        ],
    )
    result = OrganizationResult(
        total_files=2,
        processed_files=2,
        organized_structure={
            "finances": ["invoice.pdf"],
            "notes": ["notes.txt"],
        },
        plan=plan,
    )

    show_summary(console, result, tmp_path / "out", dry_run=False)

    printed_lines = [str(call[0][0]) for call in console.print.call_args_list if call[0]]
    all_printed = "\n".join(printed_lines)

    assert "invoice.pdf [dim](finance, invoice, october)[/dim]" in all_printed
    assert "notes.txt" in all_printed
    assert "notes.txt [dim]" not in all_printed


def test_show_summary_with_none_plan_renders_without_suffix(tmp_path: Path) -> None:
    console = MagicMock()
    result = OrganizationResult(
        total_files=1,
        processed_files=1,
        organized_structure={
            "documents": ["doc.txt"],
        },
        plan=None,
    )

    show_summary(console, result, tmp_path / "out", dry_run=True)

    printed_lines = [str(call[0][0]) for call in console.print.call_args_list if call[0]]
    all_printed = "\n".join(printed_lines)

    assert "doc.txt" in all_printed
    assert "doc.txt [dim]" not in all_printed
    assert "DRY RUN" in all_printed
