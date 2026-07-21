"""Golden conformance expectations for the direct-service oracle (#1605).

Every expectation below is written from canonical service semantics — the
transport-neutral :class:`OrganizationService` contract — and verified against
the :class:`~tests.conformance.driver.DirectServiceDriver`.  Adapter drivers
(#1595-#1598) must reproduce these normalized outputs byte for byte; the
scenarios deliberately cover the known cross-surface divergence classes:
recursion/hidden traversal, collision policy, duplicate handling, symlink
exclusion, transfer mode, stale-plan recovery, and option persistence.

Transfer-mode and methodology expectations cover today's canonical behavior;
#1602 extends them (canonical transfer contract, PARA/Johnny Decimal
remapping) and #1604 extends jobs/recovery, without changing this oracle.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.core.plan import OrganizationPlan
from file_organizer.history.models import Operation, OperationType
from tests.conformance.conftest import ConformanceContext
from tests.conformance.corpus import FIXED_MTIME_NS, get_case, materialize_case
from tests.conformance.driver import DirectServiceDriver, OrganizationConformanceDriver
from tests.conformance.normalize import (
    normalize_audit_events,
    normalize_job_events,
    normalize_path,
    normalize_plan,
)

pytestmark = [pytest.mark.conformance]

requires_symlinks = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink fixtures require POSIX semantics"
)


def _ok(envelope: dict) -> dict:
    assert envelope["outcome"] == "ok", envelope
    return envelope


def _operation_routes(envelope: dict) -> list[tuple[str, str, str, str]]:
    """Project plan operations onto (source, destination, status, collision)."""
    return [
        (op["source"], op["destination"], op["status"], op["collision_action"])
        for op in envelope["plan"]["operations"]
    ]


def test_direct_driver_satisfies_protocol(conformance: ConformanceContext) -> None:
    assert isinstance(conformance.driver, OrganizationConformanceDriver)
    assert conformance.driver.name == "direct-service"


def test_corpus_materialization_is_deterministic(tmp_path: Path) -> None:
    case = get_case("nested-mixed")
    first, second = tmp_path / "first", tmp_path / "second"
    for root in (first, second):
        materialize_case(case, root / "input", root / "output")

    for spec in case.files:
        left, right = first / "input" / spec.path, second / "input" / spec.path
        assert left.read_bytes() == right.read_bytes() == spec.content
        assert left.stat().st_mtime_ns == right.stat().st_mtime_ns == spec.mtime_ns


@pytest.mark.parametrize(
    ("case_id", "options", "expected_files"),
    [
        (
            "flat-documents",
            {},
            ["<input>/alpha.txt", "<input>/bravo.md", "<input>/ledger.csv"],
        ),
        (
            "nested-mixed",
            {"recursive": False},
            ["<input>/top.txt"],
        ),
        (
            "nested-mixed",
            {"recursive": True},
            [
                "<input>/cad/part.dxf",
                "<input>/docs/deep/inner.md",
                "<input>/docs/report.pdf",
                "<input>/media/clip.mp4",
                "<input>/media/photo.jpg",
                "<input>/media/song.mp3",
                "<input>/misc/data.zzz",
                "<input>/top.txt",
            ],
        ),
        (
            "hidden-entries",
            {"recursive": True, "include_hidden": False},
            ["<input>/nested/plain.md", "<input>/visible.txt"],
        ),
        (
            "hidden-entries",
            {"recursive": True, "include_hidden": True},
            [
                "<input>/.hidden.txt",
                "<input>/.hiddendir/inside.txt",
                "<input>/nested/.dotfile.md",
                "<input>/nested/plain.md",
                "<input>/visible.txt",
            ],
        ),
        (
            "hidden-entries",
            {"recursive": False, "include_hidden": True},
            ["<input>/.hidden.txt", "<input>/visible.txt"],
        ),
        (
            "hidden-entries",
            {"recursive": False, "include_hidden": False},
            ["<input>/visible.txt"],
        ),
    ],
)
def test_traversal_policy_goldens(
    conformance: ConformanceContext,
    case_id: str,
    options: dict,
    expected_files: list[str],
) -> None:
    conformance.stage(case_id)

    envelope = _ok(conformance.driver.scan(conformance.request(**options)))

    assert envelope["scan"]["files"] == expected_files
    assert envelope["scan"]["total_files"] == len(expected_files)


def test_scan_counts_golden(conformance: ConformanceContext) -> None:
    conformance.stage("nested-mixed")

    envelope = _ok(conformance.driver.scan(conformance.request()))

    assert envelope["scan"]["counts"] == {
        "audio": 1,
        "cad": 1,
        "image": 1,
        "other": 1,
        "text": 3,
        "video": 1,
    }


def test_preview_sources_match_scan(conformance: ConformanceContext) -> None:
    """Recursion policy must affect scan and preview identically (#1603)."""
    conformance.stage("nested-mixed")
    request = conformance.request(recursive=False, use_hardlinks=False)

    scan = _ok(conformance.driver.scan(request))["scan"]
    preview = _ok(conformance.driver.preview(request))

    assert [op["source"] for op in preview["plan"]["operations"]] == scan["files"]
    assert preview["plan"]["counts"]["total_files"] == scan["total_files"]


def test_media_routing_golden(conformance: ConformanceContext) -> None:
    """Optional media routes through canonical policy on pinned metadata."""
    conformance.stage("media-optional")

    envelope = _ok(conformance.driver.preview(conformance.request(use_hardlinks=False)))

    assert _operation_routes(envelope) == [
        ("<input>/clip.mp4", "<output>/Short_Clips/clip.mp4", "ready", "create"),
        ("<input>/movie.mkv", "<output>/Videos/2026/movie.mkv", "ready", "create"),
        (
            "<input>/photo_older.png",
            "<output>/Images/2020/photo_older.png",
            "ready",
            "create",
        ),
        (
            "<input>/photo_recent.jpg",
            "<output>/Images/2026/photo_recent.jpg",
            "ready",
            "create",
        ),
        (
            "<input>/song.mp3",
            "<output>/Rock/Fixture Artist/Fixture Album/00 - Fixture Song.mp3",
            "ready",
            "create",
        ),
        ("<input>/widget.step", "<output>/CAD/widget.step", "ready", "create"),
    ]
    assert envelope["plan"]["counts"] == {
        "total_files": 7,
        "processed_files": 6,
        "skipped_files": 1,  # data.zzz has no supported handler
        "failed_files": 0,
        "deduplicated_files": 0,
    }


def test_plan_is_deterministic_and_round_trips(conformance: ConformanceContext) -> None:
    """Two previews and a serialization round-trip must normalize identically."""
    conformance.stage("nested-mixed")
    request = conformance.request(use_hardlinks=False)

    first = _ok(conformance.driver.preview(request))
    second = _ok(conformance.driver.preview(request))

    assert first["plan"] == second["plan"]

    payload = json.loads(json.dumps(first["plan_payload"], sort_keys=True))
    revived = OrganizationPlan.from_dict(payload)

    assert normalize_plan(revived, conformance.input_root, conformance.output_root) == first["plan"]


def test_plan_normalization_preserves_execution_order_and_full_fingerprint(
    conformance: ConformanceContext,
) -> None:
    """Normalization must not erase behavior used by reviewed-plan execution."""
    conformance.stage("flat-documents")
    preview = _ok(conformance.driver.preview(conformance.request(use_hardlinks=False)))
    plan = OrganizationPlan.from_dict(preview["plan_payload"])

    assert [
        operation["fingerprint"]["mtime_ns"] for operation in preview["plan"]["operations"]
    ] == [FIXED_MTIME_NS] * 3

    expected_reversed_sources = [
        operation["source"] for operation in reversed(preview["plan"]["operations"])
    ]
    plan.operations.reverse()

    assert [
        operation["source"]
        for operation in normalize_plan(plan, conformance.input_root, conformance.output_root)[
            "operations"
        ]
    ] == expected_reversed_sources


def test_normalize_path_prefers_nested_output_root(tmp_path: Path) -> None:
    """The common ``input/organized_output`` layout keeps output identity."""
    input_root = tmp_path / "input"
    output_root = input_root / "organized_output"

    assert (
        normalize_path(output_root / "Documents" / "alpha.txt", input_root, output_root)
        == "<output>/Documents/alpha.txt"
    )
    assert normalize_path(input_root / "alpha.txt", input_root, output_root) == "<input>/alpha.txt"


def test_audit_normalization_preserves_recorded_order(tmp_path: Path) -> None:
    """An adapter cannot pass conformance after reordering audit events."""
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    operations = [
        Operation(
            operation_type=OperationType.COPY,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_path=input_root / "bravo.txt",
            destination_path=output_root / "Documents" / "bravo.txt",
        ),
        Operation(
            operation_type=OperationType.COPY,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_path=input_root / "alpha.txt",
            destination_path=output_root / "Documents" / "alpha.txt",
        ),
    ]

    assert [
        event["source"] for event in normalize_audit_events(operations, input_root, output_root)
    ] == ["<input>/bravo.txt", "<input>/alpha.txt"]


def test_resolved_options_are_persisted(conformance: ConformanceContext) -> None:
    """A serialized plan carries every behavior-affecting option (#1603)."""
    conformance.stage("flat-documents")

    envelope = _ok(conformance.driver.preview(conformance.request(use_hardlinks=False)))

    assert envelope["plan"]["options"] == {
        "recursive": True,
        "include_hidden": False,
        "skip_existing": True,
        "use_hardlinks": False,
        "enable_vision": True,
        "transcribe_audio": False,
        "max_transcribe_seconds": 600.0,
        "whisper_model": "tiny",
        "parallel_workers": None,
        "prefetch_depth": 2,
        "text_model": "conformance-text",
        "vision_model": "conformance-vision",
        "text_provider": "ollama",
        "vision_provider": "ollama",
    }
    assert envelope["plan"]["schema_version"] == 2


def test_collision_skip_existing_golden(conformance: ConformanceContext) -> None:
    conformance.stage("collision-stems")

    envelope = _ok(
        conformance.driver.preview(conformance.request(use_hardlinks=False, skip_existing=True))
    )

    assert _operation_routes(envelope) == [
        (
            "<input>/archive/summary.txt",
            "<output>/Documents/summary.txt",
            "skipped",
            "skip_existing",
        ),
        ("<input>/notes/draft.txt", "<output>/Documents/draft.txt", "ready", "create"),
        (
            "<input>/old/draft.txt",
            "<output>/Documents/draft_1.txt",
            "ready",
            "rename_with_counter",
        ),
        (
            "<input>/reports/summary.txt",
            "<output>/Documents/summary.txt",
            "skipped",
            "skip_existing",
        ),
    ]
    assert envelope["plan"]["counts"]["processed_files"] == 2
    assert envelope["plan"]["counts"]["skipped_files"] == 2


def test_collision_rename_with_counter_golden(conformance: ConformanceContext) -> None:
    conformance.stage("collision-stems")

    envelope = _ok(
        conformance.driver.preview(conformance.request(use_hardlinks=False, skip_existing=False))
    )

    assert _operation_routes(envelope) == [
        (
            "<input>/archive/summary.txt",
            "<output>/Documents/summary_1.txt",
            "ready",
            "rename_with_counter",
        ),
        ("<input>/notes/draft.txt", "<output>/Documents/draft.txt", "ready", "create"),
        (
            "<input>/old/draft.txt",
            "<output>/Documents/draft_1.txt",
            "ready",
            "rename_with_counter",
        ),
        (
            "<input>/reports/summary.txt",
            "<output>/Documents/summary_2.txt",
            "ready",
            "rename_with_counter",
        ),
    ]
    assert envelope["plan"]["counts"]["processed_files"] == 4


def test_duplicate_content_golden(conformance: ConformanceContext) -> None:
    """Content dedup keeps the lexicographically first source of each hash."""
    conformance.stage("duplicate-content")

    envelope = _ok(conformance.driver.preview(conformance.request(use_hardlinks=False)))

    assert _operation_routes(envelope) == [
        ("<input>/copy/two.txt", "<output>/Documents/two.txt", "ready", "create"),
        ("<input>/unique.txt", "<output>/Documents/unique.txt", "ready", "create"),
    ]
    assert envelope["plan"]["counts"] == {
        "total_files": 3,
        "processed_files": 2,
        "skipped_files": 0,
        "failed_files": 0,
        "deduplicated_files": 1,
    }
    fingerprints = [op["fingerprint"] for op in envelope["plan"]["operations"]]
    assert all(fp is not None and fp["sha256"] for fp in fingerprints)


@requires_symlinks
def test_symlinks_are_excluded(conformance: ConformanceContext) -> None:
    """Symlinked files and directories never enter scan, plan, or execution."""
    conformance.stage("symlink-entries")
    request = conformance.request(recursive=True, include_hidden=True, use_hardlinks=False)

    scan = _ok(conformance.driver.scan(request))["scan"]
    preview = _ok(conformance.driver.preview(request))

    assert scan["files"] == ["<input>/real.txt"]
    assert [op["source"] for op in preview["plan"]["operations"]] == ["<input>/real.txt"]


def test_execute_applies_previewed_plan_golden(conformance: ConformanceContext) -> None:
    conformance.stage("flat-documents")
    request = conformance.request(use_hardlinks=False)
    preview = _ok(conformance.driver.preview(request))

    envelope = _ok(conformance.driver.execute(request, preview["plan_payload"]))

    assert envelope["result"] == {
        "counts": {
            "total_files": 3,
            "processed_files": 3,
            "skipped_files": 0,
            "failed_files": 0,
            "deduplicated_files": 0,
        },
        "organized_structure": {
            "Documents": ["alpha.txt", "bravo.md"],
            "Spreadsheets": ["ledger.csv"],
        },
        "errors": [],
    }
    assert envelope["audit_events"] == [
        {
            "operation_type": "copy",
            "status": "completed",
            "source": "<input>/alpha.txt",
            "destination": "<output>/Documents/alpha.txt",
            "collision_action": "create",
            "folder": "Documents",
        },
        {
            "operation_type": "copy",
            "status": "completed",
            "source": "<input>/bravo.md",
            "destination": "<output>/Documents/bravo.md",
            "collision_action": "create",
            "folder": "Documents",
        },
        {
            "operation_type": "copy",
            "status": "completed",
            "source": "<input>/ledger.csv",
            "destination": "<output>/Spreadsheets/ledger.csv",
            "collision_action": "create",
            "folder": "Spreadsheets",
        },
    ]
    organized = sorted(
        path.relative_to(conformance.output_root).as_posix()
        for path in conformance.output_root.rglob("*")
        if path.is_file()
    )
    assert organized == [
        "Documents/alpha.txt",
        "Documents/bravo.md",
        "Spreadsheets/ledger.csv",
    ]
    assert (conformance.output_root / "Documents" / "alpha.txt").read_bytes() == b"alpha body\n"


def test_execute_without_payload_matches_previewed_execution(
    conformance: ConformanceContext,
) -> None:
    """Build-and-apply must equal the preview-review-apply flow."""
    conformance.stage("flat-documents")
    request = conformance.request(use_hardlinks=False)

    envelope = _ok(conformance.driver.execute(request))

    assert envelope["result"]["organized_structure"] == {
        "Documents": ["alpha.txt", "bravo.md"],
        "Spreadsheets": ["ledger.csv"],
    }


def test_stale_source_is_rejected_without_mutation(
    conformance: ConformanceContext,
) -> None:
    """A source changed after preview blocks execution before any write."""
    conformance.stage("flat-documents")
    request = conformance.request(use_hardlinks=False)
    preview = _ok(conformance.driver.preview(request))
    changed = conformance.input_root / "alpha.txt"
    changed.write_bytes(b"alpha body CHANGED\n")
    os.utime(changed, ns=(FIXED_MTIME_NS + 10**9, FIXED_MTIME_NS + 10**9))

    envelope = conformance.driver.execute(request, preview["plan_payload"])

    assert envelope["outcome"] == "error"
    assert envelope["error"]["error_type"] == "PlanValidationError"
    assert envelope["error"]["conflicts"] == [
        {"conflict_type": "source_changed", "path": "<input>/alpha.txt"}
    ]
    assert list(conformance.output_root.rglob("*")) == []


def test_plan_roots_mismatch_rejected(conformance: ConformanceContext, tmp_path: Path) -> None:
    conformance.stage("flat-documents")
    request = conformance.request(use_hardlinks=False)
    preview = _ok(conformance.driver.preview(request))
    other_input = tmp_path / "elsewhere"
    other_input.mkdir()
    foreign = ConformanceContext(
        input_root=other_input,
        output_root=conformance.output_root,
        driver=conformance.driver,
    )

    envelope = conformance.driver.execute(
        foreign.request(use_hardlinks=False), preview["plan_payload"]
    )

    assert envelope["outcome"] == "error"
    assert envelope["error"]["error_type"] == "ValueError"
    assert "roots do not match" in envelope["error"]["message"]


def test_plan_options_mismatch_rejected(conformance: ConformanceContext) -> None:
    conformance.stage("flat-documents")
    preview = _ok(conformance.driver.preview(conformance.request(use_hardlinks=False)))

    envelope = conformance.driver.execute(
        conformance.request(use_hardlinks=False, include_hidden=True),
        preview["plan_payload"],
    )

    assert envelope["outcome"] == "error"
    assert envelope["error"]["error_type"] == "ValueError"
    assert "options do not match" in envelope["error"]["message"]


def test_transfer_mode_hardlink_golden(conformance: ConformanceContext) -> None:
    """``use_hardlinks`` selects the plan-wide operation type (#1602 extends)."""
    conformance.stage("flat-documents")
    request = conformance.request(use_hardlinks=True)
    preview = _ok(conformance.driver.preview(request))

    assert {op["operation_type"] for op in preview["plan"]["operations"]} == {"hardlink"}

    envelope = _ok(conformance.driver.execute(request, preview["plan_payload"]))

    assert {event["operation_type"] for event in envelope["audit_events"]} == {"hardlink"}
    if sys.platform != "win32":
        source_stat = (conformance.input_root / "alpha.txt").stat()
        destination_stat = (conformance.output_root / "Documents" / "alpha.txt").stat()
        assert (source_stat.st_dev, source_stat.st_ino) == (
            destination_stat.st_dev,
            destination_stat.st_ino,
        )


def test_missing_input_is_rejected(conformance: ConformanceContext) -> None:
    envelope = conformance.driver.scan(conformance.request())

    assert envelope["outcome"] == "error"
    assert envelope["error"]["error_type"] == "ValueError"
    assert envelope["error"]["message"] == "Input path does not exist: <input>"


def test_methodology_seed_golden(conformance: ConformanceContext) -> None:
    """Canonical routing for the methodology tree today; #1602 will extend
    these expectations when PARA/Johnny Decimal remapping becomes canonical."""
    conformance.stage("methodology-seed")

    envelope = _ok(conformance.driver.preview(conformance.request(use_hardlinks=False)))

    assert _operation_routes(envelope) == [
        (
            "<input>/archive/2020/notes.md",
            "<output>/Documents/notes.md",
            "ready",
            "create",
        ),
        (
            "<input>/areas/finance/budget.csv",
            "<output>/Spreadsheets/budget.csv",
            "ready",
            "create",
        ),
        (
            "<input>/projects/alpha/plan.txt",
            "<output>/Documents/plan.txt",
            "ready",
            "create",
        ),
        (
            "<input>/resources/reading/paper.pdf",
            "<output>/PDFs/paper.pdf",
            "ready",
            "create",
        ),
    ]


def test_job_event_normalization_is_stable() -> None:
    """Provisional job-event contract: order preserved, volatile keys dropped.

    #1604 replaces this with the canonical job/recovery lifecycle schema.
    """
    events = [
        {"state": "queued", "job_id": "abc", "timestamp": "2026-01-01T00:00:00Z"},
        {"state": "running", "job_id": "abc", "duration": 1.5},
        {
            "state": "completed",
            "job_id": "abc",
            "created_at": "x",
            "capability": "organize",
        },
    ]

    assert normalize_job_events(events) == [
        {"state": "queued"},
        {"state": "running"},
        {"capability": "organize", "state": "completed"},
    ]


def test_driver_workspaces_are_isolated(tmp_path: Path) -> None:
    """Audit databases never leak outside the driver's workspace."""
    workspace = tmp_path / "ws"
    driver = DirectServiceDriver(workspace)
    context = ConformanceContext(
        input_root=tmp_path / "input", output_root=tmp_path / "output", driver=driver
    )
    context.stage("flat-documents")

    _ok(driver.execute(context.request(use_hardlinks=False)))

    databases = sorted(path.name for path in workspace.glob("*.db"))
    assert databases == ["audit-1.db"]
