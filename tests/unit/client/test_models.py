from datetime import UTC, datetime

from file_organizer.client.models import (
    ConfigResponse,
    DedupeExecuteResponse,
    DedupePreviewResponse,
    DedupeScanResponse,
    DeleteFileResponse,
    FileContentResponse,
    FileInfo,
    FileListResponse,
    HealthResponse,
    JobStatusResponse,
    MoveFileResponse,
    OrganizationError,
    OrganizationResultResponse,
    OrganizeExecuteResponse,
    ScanResponse,
    StorageStatsResponse,
    SystemStatusResponse,
    TokenResponse,
    UserResponse,
)


def test_models_instantiation():
    now = datetime.now(UTC)
    fi = FileInfo(path="test", name="test", size=10, created=now, modified=now, file_type="txt")
    assert fi.size == 10

    hr = HealthResponse(status="ok", readiness="ok", version="1", ollama=True, uptime=10.0)
    assert hr.status == "ok"

    flr = FileListResponse(items=[fi], total=1, skip=0, limit=10)
    assert flr.total == 1

    fcr = FileContentResponse(
        path="test", content="content", encoding="utf-8", truncated=False, size=10
    )
    assert fcr.size == 10

    mfr = MoveFileResponse(source="src", destination="dst", moved=True, dry_run=False)
    assert mfr.moved is True

    dfr = DeleteFileResponse(path="test", deleted=True, dry_run=False)
    assert dfr.deleted is True

    sr = ScanResponse(input_dir="dir", total_files=10, counts={"txt": 10})
    assert sr.total_files == 10

    oe = OrganizationError(file="f", error="err")
    assert oe.file == "f"

    orr = OrganizationResultResponse(
        total_files=1,
        processed_files=1,
        skipped_files=0,
        failed_files=0,
        processing_time=1.0,
        organized_structure={},
        errors=[oe],
    )
    assert orr.total_files == 1

    oer = OrganizeExecuteResponse(status="ok", result=orr)
    assert oer.status == "ok"

    jsr = JobStatusResponse(job_id="1", status="running", created_at=now, updated_at=now)
    assert jsr.status == "running"

    tr = TokenResponse(access_token="acc", refresh_token="ref")
    assert tr.access_token == "acc"

    ur = UserResponse(
        id="1", username="u", email="e", is_active=True, is_admin=False, created_at=now
    )
    assert ur.username == "u"

    ssr = SystemStatusResponse(
        app="a", version="v", environment="e", disk_total=1, disk_used=1, disk_free=0, active_jobs=0
    )
    assert ssr.app == "a"

    cr = ConfigResponse(profile="p", config={}, profiles=[])
    assert cr.profile == "p"

    stsr = StorageStatsResponse(
        total_size=1,
        organized_size=1,
        saved_size=1,
        file_count=1,
        directory_count=1,
        size_by_type={},
        largest_files=[],
    )
    assert stsr.total_size == 1

    dsr = DedupeScanResponse(path="p", duplicates=[], stats={})
    assert dsr.path == "p"

    dpr = DedupePreviewResponse(path="p", preview=[], stats={})
    assert dpr.path == "p"

    der = DedupeExecuteResponse(path="p", removed=[], dry_run=False, stats={})
    assert der.path == "p"
