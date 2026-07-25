"""Tests for the transport-neutral organization application service."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.organization_service import OrganizationService
from file_organizer.core.organize_options import OrganizeOptions, OrganizeRequest
from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import OrganizationPlan, build_plan_from_processed
from file_organizer.core.types import OrganizationResult
from file_organizer.models.base import ModelConfig, ModelType

pytestmark = [pytest.mark.ci, pytest.mark.unit]

# Executing a plan goes through SafeDir (POSIX dir_fd / O_NOFOLLOW); the Windows
# port is deferred (#264) and CI Full Matrix runs this ci-marked file on Windows.
requires_safedir = pytest.mark.skipif(
    sys.platform == "win32", reason="execute_plan uses SafeDir, which is POSIX-only (#264)"
)


def _service(**kwargs: object) -> OrganizationService:
    return OrganizationService(
        text_model_config=ModelConfig("text-model", ModelType.TEXT),
        vision_model_config=ModelConfig("vision-model", ModelType.VISION),
        **kwargs,  # type: ignore[arg-type]
    )


def _resolved_options(**overrides: object) -> OrganizeOptions:
    values: dict[str, object] = {
        "text_model": "text-model",
        "vision_model": "vision-model",
        "text_provider": "ollama",
        "vision_provider": "ollama",
    }
    values.update(overrides)
    return OrganizeOptions.from_dict(values)


def _empty_plan(tmp_path: Path, options: OrganizeOptions) -> OrganizationPlan:
    input_path = tmp_path / "input"
    input_path.mkdir(exist_ok=True)
    return build_plan_from_processed(
        input_path=input_path,
        output_path=tmp_path / "out",
        processed=[],
        skip_existing=options.skip_existing,
        use_hardlinks=options.use_hardlinks,
        total_files=0,
        skipped_files=0,
        deduplicated_files=0,
        options=options,
    )


def test_scan_obeys_recursive_and_hidden_policy(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "top.txt").write_text("top")
    (tmp_path / ".hidden.txt").write_text("hidden")
    (nested / "deep.jpg").write_bytes(b"image")
    (nested / "clip.mp4").write_bytes(b"video")
    (nested / "voice.mp3").write_bytes(b"audio")
    (nested / "drawing.dxf").write_bytes(b"cad")
    (nested / "archive.unknown").write_bytes(b"other")
    service = _service()

    shallow = service.scan(
        OrganizeRequest(
            tmp_path,
            tmp_path / "out",
            OrganizeOptions(recursive=False, include_hidden=False),
        )
    )
    complete = service.scan(
        OrganizeRequest(
            tmp_path,
            tmp_path / "out",
            OrganizeOptions(recursive=True, include_hidden=True),
        )
    )

    assert [path.name for path in shallow.files] == ["top.txt"]
    assert shallow.counts["text"] == 1
    assert {path.name for path in complete.files} == {
        ".hidden.txt",
        "archive.unknown",
        "clip.mp4",
        "deep.jpg",
        "drawing.dxf",
        "top.txt",
        "voice.mp3",
    }
    assert complete.counts["image"] == 1
    assert complete.counts["video"] == 1
    assert complete.counts["audio"] == 1
    assert complete.counts["cad"] == 1
    assert complete.counts["other"] == 1


def test_scan_excludes_direct_hidden_file_unless_requested(tmp_path: Path) -> None:
    hidden = tmp_path / ".secret.txt"
    hidden.write_text("secret")
    service = _service()

    excluded = service.scan(OrganizeRequest(hidden, tmp_path / "out"))
    included = service.scan(
        OrganizeRequest(
            hidden,
            tmp_path / "out",
            OrganizeOptions(include_hidden=True),
        )
    )

    assert excluded.total_files == 0
    assert included.files == (hidden,)


def test_scan_rejects_missing_input(tmp_path: Path) -> None:
    with pytest.raises(DomainError, match="Input path does not exist") as exc_info:
        _service().scan(OrganizeRequest(tmp_path / "missing", tmp_path / "out"))
    assert exc_info.value.code == DomainErrorCode.NOT_FOUND


def test_preview_persists_resolved_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "top.txt").write_text("top")
    (nested / "deep.txt").write_text("deep")
    monkeypatch.setattr(FileOrganizer, "_init_text_processor", lambda self: None)
    request = OrganizeRequest(
        tmp_path,
        tmp_path / "out",
        OrganizeOptions(
            recursive=False,
            include_hidden=False,
            use_hardlinks=False,
            enable_vision=False,
            parallel_workers=1,
            prefetch_depth=0,
        ),
    )

    result = _service().preview(request)

    assert result.total_files == 1
    assert isinstance(result.plan, OrganizationPlan)
    assert result.plan.options.recursive is False
    assert result.plan.options.text_model == "text-model"
    assert result.plan.options.vision_model == "vision-model"
    assert result.plan.options.prefetch_depth == 0


@requires_safedir
def test_scan_preview_and_execute_share_traversal_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "input"
    nested = input_path / "nested"
    nested.mkdir(parents=True)
    top = input_path / "top.txt"
    top.write_text("top")
    (nested / "deep.txt").write_text("deep")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(FileOrganizer, "_init_text_processor", lambda self: None)
    request = OrganizeRequest(
        input_path,
        tmp_path / "out",
        OrganizeOptions(
            recursive=False,
            use_hardlinks=False,
            enable_vision=False,
        ),
    )
    service = _service()

    scan = service.scan(request)
    preview = service.preview(request)
    assert isinstance(preview.plan, OrganizationPlan)
    result = service.execute(request, preview.plan)

    assert scan.files == (top,)
    assert [operation.source for operation in preview.plan.operations] == [top]
    assert len(result.organized_structure) == 1
    assert preview.plan.operations[0].destination.exists()
    assert all("deep.txt" not in files for files in result.organized_structure.values())


def test_execute_rejects_plan_from_different_options(tmp_path: Path) -> None:
    organizer = MagicMock()
    organizer.organize.return_value.plan = None
    factory = MagicMock(return_value=organizer)
    service = _service(organizer_factory=factory)
    request = OrganizeRequest(tmp_path, tmp_path / "out", OrganizeOptions(use_hardlinks=False))
    plan = MagicMock(spec=OrganizationPlan)
    plan.roots_match.return_value = True
    plan.options = OrganizeOptions(use_hardlinks=True)

    with pytest.raises(DomainError, match="options do not match") as exc_info:
        service.execute(request, plan)
    assert exc_info.value.code == DomainErrorCode.PLAN_MISMATCH


def test_execute_applies_reviewed_plan_with_resolved_options(tmp_path: Path) -> None:
    options = _resolved_options(use_hardlinks=False)
    plan = _empty_plan(tmp_path, options)
    expected = OrganizationResult(plan=plan)
    organizer = MagicMock()
    organizer.execute_plan.return_value = expected
    factory = MagicMock(return_value=organizer)
    service = _service(organizer_factory=factory)
    request = OrganizeRequest(
        tmp_path / "input",
        tmp_path / "out",
        OrganizeOptions(use_hardlinks=False),
    )

    result = service.execute(request, plan)

    assert result is expected
    organizer.execute_plan.assert_called_once_with(plan)
    assert factory.call_args.kwargs["dry_run"] is False
    assert factory.call_args.kwargs["text_model_config"].name == "text-model"


def test_execute_can_build_then_apply_the_preview_plan(tmp_path: Path) -> None:
    options = _resolved_options()
    plan = _empty_plan(tmp_path, options)
    preview_organizer = MagicMock()
    preview_organizer.organize.return_value = OrganizationResult(plan=plan)
    execute_organizer = MagicMock()
    expected = OrganizationResult(plan=plan)
    execute_organizer.execute_plan.return_value = expected
    factory = MagicMock(side_effect=[preview_organizer, execute_organizer])
    service = _service(organizer_factory=factory)
    request = OrganizeRequest(tmp_path / "input", tmp_path / "out")

    assert service.execute(request) is expected
    preview_organizer.organize.assert_called_once()
    execute_organizer.execute_plan.assert_called_once_with(plan)


def test_execute_rejects_missing_preview_plan(tmp_path: Path) -> None:
    organizer = MagicMock()
    organizer.organize.return_value = OrganizationResult(plan=None)
    service = _service(organizer_factory=MagicMock(return_value=organizer))
    request = OrganizeRequest(tmp_path, tmp_path / "out")

    with pytest.raises(DomainError, match="did not produce an executable plan") as exc_info:
        service.execute(request)
    assert exc_info.value.code == DomainErrorCode.EXECUTION_FAILED


def test_execute_rejects_plan_from_different_roots(tmp_path: Path) -> None:
    plan = _empty_plan(tmp_path, _resolved_options())

    with pytest.raises(DomainError, match="roots do not match") as exc_info:
        _service().execute(OrganizeRequest(tmp_path / "other", tmp_path / "out"), plan)
    assert exc_info.value.code == DomainErrorCode.PLAN_MISMATCH


def test_service_resolves_missing_model_dependencies() -> None:
    text_config = ModelConfig("default-text", ModelType.TEXT)
    vision_config = ModelConfig("default-vision", ModelType.VISION)

    with patch(
        "file_organizer.config.provider_env.get_model_configs",
        return_value=(text_config, vision_config),
    ):
        service = OrganizationService()

    assert service._text_model_config is text_config
    assert service._vision_model_config is vision_config
