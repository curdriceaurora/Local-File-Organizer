"""Tests for file_organizer.client.models — Pydantic API response models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
_NOW_STR = "2026-01-15T10:30:00Z"


def _file_info_data(**overrides):
    """Return a minimal valid dict for FileInfo."""
    base = {
        "path": "/tmp/test.txt",
        "name": "test.txt",
        "size": 1024,
        "created": _NOW_STR,
        "modified": _NOW_STR,
        "file_type": "text",
    }
    base.update(overrides)
    return base


def _org_result_data(**overrides):
    """Return a minimal valid dict for OrganizationResultResponse."""
    base = {
        "total_files": 10,
        "processed_files": 8,
        "skipped_files": 1,
        "failed_files": 1,
        "processing_time": 2.5,
        "organized_structure": {"Documents": ["a.txt", "b.pdf"]},
        "errors": [{"file": "c.bin", "error": "unsupported"}],
    }
    base.update(overrides)
    return base


# ===================================================================
# HealthResponse
# ===================================================================


@pytest.mark.unit
class TestHealthResponse:
    def test_valid_construction(self):
        resp = HealthResponse(
            status="ok",
            version="2.0.0",
            environment="production",
            timestamp="2026-01-15T10:30:00Z",
        )
        assert resp.status == "ok"
        assert resp.version == "2.0.0"
        assert resp.environment == "production"
        assert resp.timestamp == "2026-01-15T10:30:00Z"

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            HealthResponse(status="ok", version="2.0.0", environment="prod")

    def test_serialization_roundtrip(self):
        data = {
            "status": "ok",
            "version": "1.0",
            "environment": "dev",
            "timestamp": "now",
        }
        resp = HealthResponse(**data)
        dumped = resp.model_dump()
        assert dumped == data


# ===================================================================
# FileInfo
# ===================================================================


@pytest.mark.unit
class TestFileInfo:
    def test_valid_construction(self):
        fi = FileInfo(**_file_info_data())
        assert fi.path == "/tmp/test.txt"
        assert fi.name == "test.txt"
        assert fi.size == 1024
        assert fi.file_type == "text"
        assert fi.mime_type is None

    def test_optional_mime_type(self):
        fi = FileInfo(**_file_info_data(mime_type="text/plain"))
        assert fi.mime_type == "text/plain"

    def test_datetime_parsing(self):
        fi = FileInfo(**_file_info_data())
        assert isinstance(fi.created, datetime)
        assert isinstance(fi.modified, datetime)

    def test_datetime_from_iso_string(self):
        fi = FileInfo(**_file_info_data(created="2025-06-01T12:00:00Z"))
        assert fi.created.year == 2025
        assert fi.created.month == 6

    def test_missing_required_field(self):
        data = _file_info_data()
        del data["name"]
        with pytest.raises(ValidationError):
            FileInfo(**data)

    def test_invalid_size_type(self):
        with pytest.raises(ValidationError):
            FileInfo(**_file_info_data(size="not_a_number"))


# ===================================================================
# FileListResponse
# ===================================================================


@pytest.mark.unit
class TestFileListResponse:
    def test_valid_construction(self):
        resp = FileListResponse(
            items=[FileInfo(**_file_info_data())],
            total=1,
            skip=0,
            limit=20,
        )
        assert len(resp.items) == 1
        assert resp.total == 1
        assert resp.skip == 0
        assert resp.limit == 20

    def test_empty_items(self):
        resp = FileListResponse(items=[], total=0, skip=0, limit=20)
        assert resp.items == []
        assert resp.total == 0

    def test_nested_file_info_from_dict(self):
        resp = FileListResponse(
            items=[_file_info_data(), _file_info_data(name="b.txt")],
            total=2,
            skip=0,
            limit=20,
        )
        assert len(resp.items) == 2
        assert resp.items[1].name == "b.txt"

    def test_missing_items_raises(self):
        with pytest.raises(ValidationError):
            FileListResponse(total=0, skip=0, limit=20)


# ===================================================================
# FileContentResponse
# ===================================================================


@pytest.mark.unit
class TestFileContentResponse:
    def test_valid_construction(self):
        resp = FileContentResponse(
            path="/tmp/f.txt",
            content="hello",
            encoding="utf-8",
            truncated=False,
            size=5,
        )
        assert resp.path == "/tmp/f.txt"
        assert resp.content == "hello"
        assert resp.encoding == "utf-8"
        assert resp.truncated is False
        assert resp.size == 5
        assert resp.mime_type is None

    def test_with_mime_type(self):
        resp = FileContentResponse(
            path="/p",
            content="x",
            encoding="utf-8",
            truncated=True,
            size=1,
            mime_type="application/json",
        )
        assert resp.mime_type == "application/json"
        assert resp.truncated is True


# ===================================================================
# MoveFileResponse
# ===================================================================


@pytest.mark.unit
class TestMoveFileResponse:
    def test_valid_construction(self):
        resp = MoveFileResponse(
            source="/a/b.txt",
            destination="/c/b.txt",
            moved=True,
            dry_run=False,
        )
        assert resp.source == "/a/b.txt"
        assert resp.destination == "/c/b.txt"
        assert resp.moved is True
        assert resp.dry_run is False

    def test_dry_run(self):
        resp = MoveFileResponse(
            source="s", destination="d", moved=False, dry_run=True
        )
        assert resp.dry_run is True
        assert resp.moved is False


# ===================================================================
# DeleteFileResponse
# ===================================================================


@pytest.mark.unit
class TestDeleteFileResponse:
    def test_valid_construction(self):
        resp = DeleteFileResponse(path="/x", deleted=True, dry_run=False)
        assert resp.path == "/x"
        assert resp.deleted is True
        assert resp.dry_run is False
        assert resp.trashed_path is None

    def test_with_trashed_path(self):
        resp = DeleteFileResponse(
            path="/x", deleted=True, dry_run=False, trashed_path="/trash/x"
        )
        assert resp.trashed_path == "/trash/x"

    def test_dry_run_not_deleted(self):
        resp = DeleteFileResponse(path="/x", deleted=False, dry_run=True)
        assert resp.deleted is False
        assert resp.dry_run is True


# ===================================================================
# ScanResponse
# ===================================================================


@pytest.mark.unit
class TestScanResponse:
    def test_valid_construction(self):
        resp = ScanResponse(
            input_dir="/home/user/docs",
            total_files=42,
            counts={"pdf": 10, "txt": 32},
        )
        assert resp.input_dir == "/home/user/docs"
        assert resp.total_files == 42
        assert resp.counts == {"pdf": 10, "txt": 32}

    def test_empty_counts(self):
        resp = ScanResponse(input_dir="/d", total_files=0, counts={})
        assert resp.counts == {}


# ===================================================================
# OrganizationError
# ===================================================================


@pytest.mark.unit
class TestOrganizationError:
    def test_valid_construction(self):
        err = OrganizationError(file="bad.bin", error="unsupported format")
        assert err.file == "bad.bin"
        assert err.error == "unsupported format"

    def test_missing_field(self):
        with pytest.raises(ValidationError):
            OrganizationError(file="bad.bin")


# ===================================================================
# OrganizationResultResponse
# ===================================================================


@pytest.mark.unit
class TestOrganizationResultResponse:
    def test_valid_construction(self):
        resp = OrganizationResultResponse(**_org_result_data())
        assert resp.total_files == 10
        assert resp.processed_files == 8
        assert resp.skipped_files == 1
        assert resp.failed_files == 1
        assert resp.processing_time == 2.5
        assert "Documents" in resp.organized_structure
        assert len(resp.errors) == 1
        assert resp.errors[0].file == "c.bin"

    def test_empty_errors(self):
        resp = OrganizationResultResponse(**_org_result_data(errors=[]))
        assert resp.errors == []

    def test_nested_error_from_dict(self):
        resp = OrganizationResultResponse(**_org_result_data())
        assert isinstance(resp.errors[0], OrganizationError)


# ===================================================================
# OrganizeExecuteResponse
# ===================================================================


@pytest.mark.unit
class TestOrganizeExecuteResponse:
    def test_minimal(self):
        resp = OrganizeExecuteResponse(status="completed")
        assert resp.status == "completed"
        assert resp.job_id is None
        assert resp.result is None
        assert resp.error is None

    def test_with_job_id(self):
        resp = OrganizeExecuteResponse(status="queued", job_id="abc-123")
        assert resp.job_id == "abc-123"

    def test_with_result(self):
        resp = OrganizeExecuteResponse(
            status="completed",
            result=_org_result_data(),
        )
        assert resp.result is not None
        assert isinstance(resp.result, OrganizationResultResponse)
        assert resp.result.total_files == 10

    def test_with_error(self):
        resp = OrganizeExecuteResponse(status="failed", error="disk full")
        assert resp.error == "disk full"


# ===================================================================
# JobStatusResponse
# ===================================================================


@pytest.mark.unit
class TestJobStatusResponse:
    def test_valid_construction(self):
        resp = JobStatusResponse(
            job_id="j-1",
            status="running",
            created_at=_NOW_STR,
            updated_at=_NOW_STR,
        )
        assert resp.job_id == "j-1"
        assert resp.status == "running"
        assert isinstance(resp.created_at, datetime)
        assert isinstance(resp.updated_at, datetime)
        assert resp.result is None
        assert resp.error is None

    def test_with_result_and_error(self):
        resp = JobStatusResponse(
            job_id="j-2",
            status="failed",
            created_at=_NOW_STR,
            updated_at=_NOW_STR,
            result=_org_result_data(),
            error="partial failure",
        )
        assert resp.result is not None
        assert resp.error == "partial failure"


# ===================================================================
# TokenResponse
# ===================================================================


@pytest.mark.unit
class TestTokenResponse:
    def test_valid_construction(self):
        resp = TokenResponse(
            access_token="acc-tok",
            refresh_token="ref-tok",
        )
        assert resp.access_token == "acc-tok"
        assert resp.refresh_token == "ref-tok"
        assert resp.token_type == "bearer"

    def test_custom_token_type(self):
        resp = TokenResponse(
            access_token="a", refresh_token="r", token_type="mac"
        )
        assert resp.token_type == "mac"

    def test_default_token_type(self):
        resp = TokenResponse(access_token="a", refresh_token="r")
        assert resp.token_type == "bearer"


# ===================================================================
# UserResponse
# ===================================================================


@pytest.mark.unit
class TestUserResponse:
    def test_valid_construction(self):
        resp = UserResponse(
            id="u-1",
            username="alice",
            email="alice@example.com",
            is_active=True,
            is_admin=False,
            created_at=_NOW_STR,
        )
        assert resp.id == "u-1"
        assert resp.username == "alice"
        assert resp.email == "alice@example.com"
        assert resp.full_name is None
        assert resp.is_active is True
        assert resp.is_admin is False
        assert isinstance(resp.created_at, datetime)
        assert resp.last_login is None

    def test_with_optional_fields(self):
        resp = UserResponse(
            id="u-2",
            username="bob",
            email="bob@example.com",
            full_name="Bob Smith",
            is_active=False,
            is_admin=True,
            created_at=_NOW_STR,
            last_login=_NOW_STR,
        )
        assert resp.full_name == "Bob Smith"
        assert resp.last_login is not None
        assert isinstance(resp.last_login, datetime)


# ===================================================================
# SystemStatusResponse
# ===================================================================


@pytest.mark.unit
class TestSystemStatusResponse:
    def test_valid_construction(self):
        resp = SystemStatusResponse(
            app="file-organizer",
            version="2.0.0",
            environment="production",
            disk_total=500_000_000_000,
            disk_used=200_000_000_000,
            disk_free=300_000_000_000,
            active_jobs=3,
        )
        assert resp.app == "file-organizer"
        assert resp.version == "2.0.0"
        assert resp.disk_total == 500_000_000_000
        assert resp.disk_free == 300_000_000_000
        assert resp.active_jobs == 3


# ===================================================================
# ConfigResponse
# ===================================================================


@pytest.mark.unit
class TestConfigResponse:
    def test_valid_construction(self):
        resp = ConfigResponse(
            profile="default",
            config={"key": "value", "nested": {"a": 1}},
            profiles=["default", "work"],
        )
        assert resp.profile == "default"
        assert resp.config["key"] == "value"
        assert resp.profiles == ["default", "work"]

    def test_empty_config(self):
        resp = ConfigResponse(profile="empty", config={}, profiles=[])
        assert resp.config == {}
        assert resp.profiles == []


# ===================================================================
# StorageStatsResponse
# ===================================================================


@pytest.mark.unit
class TestStorageStatsResponse:
    def test_valid_construction(self):
        fi_data = _file_info_data(size=999_999)
        resp = StorageStatsResponse(
            total_size=10_000,
            organized_size=8_000,
            saved_size=2_000,
            file_count=100,
            directory_count=10,
            size_by_type={"pdf": 5000, "txt": 3000},
            largest_files=[fi_data],
        )
        assert resp.total_size == 10_000
        assert resp.organized_size == 8_000
        assert resp.saved_size == 2_000
        assert resp.file_count == 100
        assert resp.directory_count == 10
        assert resp.size_by_type == {"pdf": 5000, "txt": 3000}
        assert len(resp.largest_files) == 1
        assert isinstance(resp.largest_files[0], FileInfo)
        assert resp.largest_files[0].size == 999_999

    def test_empty_largest_files(self):
        resp = StorageStatsResponse(
            total_size=0,
            organized_size=0,
            saved_size=0,
            file_count=0,
            directory_count=0,
            size_by_type={},
            largest_files=[],
        )
        assert resp.largest_files == []


# ===================================================================
# DedupeScanResponse
# ===================================================================


@pytest.mark.unit
class TestDedupeScanResponse:
    def test_valid_construction(self):
        resp = DedupeScanResponse(
            path="/scan",
            duplicates=[{"hash": "abc", "files": ["/a", "/b"]}],
            stats={"total": 100, "duplicates": 5},
        )
        assert resp.path == "/scan"
        assert len(resp.duplicates) == 1
        assert resp.stats["total"] == 100

    def test_no_duplicates(self):
        resp = DedupeScanResponse(path="/p", duplicates=[], stats={})
        assert resp.duplicates == []


# ===================================================================
# DedupePreviewResponse
# ===================================================================


@pytest.mark.unit
class TestDedupePreviewResponse:
    def test_valid_construction(self):
        resp = DedupePreviewResponse(
            path="/preview",
            preview=[{"action": "delete", "file": "/a"}],
            stats={"would_remove": 3},
        )
        assert resp.path == "/preview"
        assert len(resp.preview) == 1
        assert resp.stats["would_remove"] == 3


# ===================================================================
# DedupeExecuteResponse
# ===================================================================


@pytest.mark.unit
class TestDedupeExecuteResponse:
    def test_valid_construction(self):
        resp = DedupeExecuteResponse(
            path="/exec",
            removed=["/a", "/b"],
            dry_run=False,
            stats={"removed": 2},
        )
        assert resp.path == "/exec"
        assert resp.removed == ["/a", "/b"]
        assert resp.dry_run is False
        assert resp.stats["removed"] == 2

    def test_dry_run(self):
        resp = DedupeExecuteResponse(
            path="/exec", removed=[], dry_run=True, stats={"removed": 0}
        )
        assert resp.dry_run is True
        assert resp.removed == []


# ===================================================================
# Cross-cutting: model_dump / model_validate roundtrips
# ===================================================================


@pytest.mark.unit
class TestSerializationRoundtrips:
    """Ensure every model can roundtrip through model_dump / model_validate."""

    def test_health_response_roundtrip(self):
        data = {"status": "ok", "version": "1", "environment": "d", "timestamp": "t"}
        assert HealthResponse.model_validate(data).model_dump() == data

    def test_file_info_roundtrip(self):
        obj = FileInfo(**_file_info_data())
        rebuilt = FileInfo.model_validate(obj.model_dump())
        assert rebuilt.path == obj.path
        assert rebuilt.size == obj.size

    def test_organization_result_roundtrip(self):
        obj = OrganizationResultResponse(**_org_result_data())
        dumped = obj.model_dump()
        rebuilt = OrganizationResultResponse.model_validate(dumped)
        assert rebuilt.total_files == obj.total_files
        assert rebuilt.errors[0].file == "c.bin"

    def test_user_response_roundtrip(self):
        obj = UserResponse(
            id="u",
            username="u",
            email="e@e.com",
            is_active=True,
            is_admin=False,
            created_at=_NOW_STR,
        )
        rebuilt = UserResponse.model_validate(obj.model_dump())
        assert rebuilt.username == "u"

    def test_storage_stats_roundtrip(self):
        obj = StorageStatsResponse(
            total_size=1,
            organized_size=1,
            saved_size=0,
            file_count=1,
            directory_count=1,
            size_by_type={},
            largest_files=[_file_info_data()],
        )
        rebuilt = StorageStatsResponse.model_validate(obj.model_dump())
        assert rebuilt.file_count == 1
        assert len(rebuilt.largest_files) == 1
