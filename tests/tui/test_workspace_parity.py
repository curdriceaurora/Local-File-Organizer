"""Behavioral parity coverage for the connected Textual workspace (#1598)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.config.schema import AppConfig
from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.organize_options import OrganizeOptions
from file_organizer.core.plan import build_plan_from_processed
from file_organizer.core.types import OrganizationResult
from file_organizer.services.text_processor import ProcessedFile
from file_organizer.tui.app import FileOrganizerApp
from file_organizer.tui.file_preview import FilePreviewView
from file_organizer.tui.methodology_view import MethodologyView
from file_organizer.tui.organization_adapter import TUIOrganizationAdapter
from file_organizer.tui.organization_preview import OrganizationPreviewView
from file_organizer.tui.settings_view import SettingsView
from file_organizer.tui.workspace import TUIWorkspace

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _plan(input_root: Path, output_root: Path, options: OrganizeOptions):
    input_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    source = input_root / "report.txt"
    source.write_text("report")
    return build_plan_from_processed(
        input_path=input_root,
        output_path=output_root,
        processed=[
            ProcessedFile(
                file_path=source,
                description="Document",
                folder_name="Documents",
                filename="report",
            )
        ],
        options=options,
        skip_existing=options.skip_existing,
        use_hardlinks=options.use_hardlinks,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )


def test_all_eight_views_share_one_workspace(tmp_path: Path) -> None:
    workspace = TUIWorkspace(tmp_path, tmp_path / "out")

    views = {
        name: FileOrganizerApp._create_view(name, workspace)
        for name in (
            "files",
            "organized",
            "analytics",
            "methodology",
            "audio",
            "history",
            "copilot",
            "settings",
        )
    }

    assert len(views) == 8
    assert all(getattr(view, "_workspace", None) is workspace for view in views.values())


def test_unset_workspace_never_falls_back_to_cwd() -> None:
    workspace = TUIWorkspace()

    files = FilePreviewView(path=None, workspace=workspace)
    organized = OrganizationPreviewView(workspace=workspace)

    assert files._root_path is None
    assert organized._input_dir is None
    assert organized._output_dir is None
    with pytest.raises(DomainError, match="Set explicit source and output") as exc_info:
        workspace.request()
    assert exc_info.value.code == DomainErrorCode.INVALID_REQUEST


def test_root_change_clears_root_bound_lifecycle_state(tmp_path: Path) -> None:
    workspace = TUIWorkspace(
        tmp_path / "first",
        tmp_path / "first-output",
        reviewed_plan=MagicMock(),
        active_job=MagicMock(),
        last_result=OrganizationResult(total_files=12, processed_files=12),
    )

    workspace.set_roots(tmp_path / "second", tmp_path / "second-output")

    assert workspace.reviewed_plan is None
    assert workspace.active_job is None
    assert workspace.last_result is None


def test_config_load_failure_is_retained_as_workspace_error() -> None:
    manager = MagicMock()
    manager.load.side_effect = OSError("config unreadable")

    workspace = TUIWorkspace.from_config(manager)

    assert workspace.active_root is None
    assert workspace.output_root is None
    assert workspace.last_error is not None
    assert workspace.last_error.code == DomainErrorCode.EXECUTION_FAILED
    assert workspace.last_error.message == "config unreadable"


def test_from_config_never_lets_persisted_provider_outrank_environment() -> None:
    """A persisted provider must not become a request-level override on startup.

    ``OrganizationService._resolve_options`` treats an ``OrganizeOptions.text_provider``
    value as the highest-priority source, above ``FO_PROVIDER``. If ``from_config``
    copied ``config.models.framework`` in here, a saved "openai" would silently beat
    ``FO_PROVIDER=ollama`` on every session before the user ever chose anything (#1660).
    """
    config = AppConfig()
    config.models.framework = "openai"
    manager = MagicMock()
    manager.load.return_value = config

    workspace = TUIWorkspace.from_config(manager)

    assert workspace.options.text_provider is None
    assert workspace.options.vision_provider is None


def test_selection_persists_across_file_views(tmp_path: Path) -> None:
    selected = tmp_path / "selected.txt"
    selected.write_text("selected")
    workspace = TUIWorkspace(tmp_path, tmp_path / "out")
    first = FilePreviewView(workspace=workspace)
    first.selection.toggle(selected)
    first._notify_selection()

    second = FilePreviewView(workspace=workspace)

    assert workspace.selected_files == {selected}
    assert second.selection.selected_files == {selected}


def test_selection_paths_expand_user_before_root_filtering() -> None:
    workspace = TUIWorkspace()

    workspace.set_selected_files({Path("~") / "selected.txt"})

    assert workspace.selected_files == {Path.home() / "selected.txt"}


def test_settings_map_losslessly_to_canonical_options(tmp_path: Path) -> None:
    workspace = TUIWorkspace()
    view = SettingsView(workspace=workspace)
    view._input_dir = str(tmp_path / "input")
    view._output_dir = str(tmp_path / "output")
    view._recursive = False
    view._include_hidden = True
    view._skip_existing = False
    view._transfer_mode = "copy"
    view._methodology = "jd"
    view._enable_vision = False
    view._transcribe_audio = True
    view._max_workers = 5
    view._prefetch_depth = 3
    view._text_model = "custom-text"
    view._provider = "openai"
    view._provider_overridden = True

    view._sync_workspace()

    assert workspace.request().options.to_dict() == {
        **OrganizeOptions().to_dict(),
        "recursive": False,
        "include_hidden": True,
        "skip_existing": False,
        "transfer_mode": "copy",
        "methodology": "jd",
        "enable_vision": False,
        "transcribe_audio": True,
        "parallel_workers": 5,
        "prefetch_depth": 3,
        "text_model": "custom-text",
        "text_provider": "openai",
        "vision_provider": "openai",
    }


def test_settings_actions_update_session_options_immediately(tmp_path: Path) -> None:
    workspace = TUIWorkspace(tmp_path, tmp_path / "out")
    view = SettingsView(workspace=workspace)
    view._refresh_panel = MagicMock()
    view._set_status = MagicMock()

    view.action_toggle_recursive()
    view.action_toggle_hidden()
    view.action_toggle_transfer()
    view.action_toggle_skip_existing()
    view.action_toggle_vision()
    view.action_toggle_transcription()
    view.action_cycle_methodology()
    view.action_cycle_text_model()
    view.action_workers_up()
    view.action_prefetch_up()

    options = workspace.options
    assert options.recursive is view._recursive is False
    assert options.include_hidden is view._include_hidden is True
    assert options.skip_existing is view._skip_existing is False
    assert options.effective_transfer_mode.value == view._transfer_mode == "copy"
    assert options.enable_vision is view._enable_vision is False
    assert options.transcribe_audio is view._transcribe_audio is True
    assert options.effective_methodology.value == view._methodology == "para"
    assert options.text_model == view._text_model
    assert options.parallel_workers == view._max_workers == 2
    assert options.prefetch_depth == view._prefetch_depth == 3

    recreated = SettingsView(workspace=workspace)
    assert recreated._recursive is False
    assert recreated._include_hidden is True
    assert recreated._transfer_mode == "copy"
    assert recreated._methodology == "para"


def test_failed_persistence_does_not_block_session_apply(tmp_path: Path) -> None:
    workspace = TUIWorkspace()
    view = SettingsView(workspace=workspace)
    view._input_dir = str(tmp_path / "input")
    view._output_dir = str(tmp_path / "output")
    view._recursive = False
    view._refresh_panel = MagicMock()
    view._set_status = MagicMock()

    with patch(
        "file_organizer.tui.settings_view.save_parallel_runtime_settings",
        side_effect=OSError("read-only config"),
    ):
        view.action_save_settings()

    assert workspace.active_root == tmp_path / "input"
    assert workspace.output_root == tmp_path / "output"
    assert workspace.options.recursive is False
    view._set_status.assert_called_once_with(
        "Session updated; failed to save settings: read-only config"
    )


def test_methodology_action_updates_shared_canonical_state(tmp_path: Path) -> None:
    workspace = TUIWorkspace(tmp_path, tmp_path / "out")
    view = MethodologyView(workspace=workspace)
    view.query_one = MagicMock()
    view._update_preview = MagicMock()

    view.action_set_jd()

    assert workspace.options.effective_methodology.value == "jd"
    view._update_preview.assert_called_once()


def test_selected_file_scope_fails_closed_without_widening(tmp_path: Path) -> None:
    selected = tmp_path / "selected.txt"
    selected.write_text("selected")
    workspace = TUIWorkspace(tmp_path, tmp_path / "out", selected_files={selected})
    service = MagicMock()

    with pytest.raises(DomainError) as exc_info:
        TUIOrganizationAdapter(workspace, service).preview()

    assert exc_info.value.code == DomainErrorCode.OPTIONAL_FEATURE_UNAVAILABLE
    assert exc_info.value.details["selected_files"] == 1
    service.preview.assert_not_called()


def test_previewed_plan_is_the_plan_executed_unchanged(tmp_path: Path) -> None:
    options = OrganizeOptions(
        recursive=False,
        include_hidden=True,
        skip_existing=False,
        transfer_mode="copy",
        methodology="para",
        enable_vision=False,
        transcribe_audio=True,
        parallel_workers=2,
        prefetch_depth=1,
    )
    input_root, output_root = tmp_path / "input", tmp_path / "output"
    plan = _plan(input_root, output_root, options)
    preview_result = OrganizationResult(total_files=1, processed_files=1, plan=plan)
    execute_result = OrganizationResult(total_files=1, processed_files=1, plan=plan)
    service = MagicMock()
    service.preview.return_value = preview_result
    service.execute.return_value = execute_result
    workspace = TUIWorkspace(input_root, output_root, options=options)
    adapter = TUIOrganizationAdapter(workspace, service)

    adapter.preview()
    result = adapter.execute()

    preview_request = service.preview.call_args.args[0]
    execute_request, executed_plan = service.execute.call_args.args
    assert preview_request == execute_request == workspace.request()
    assert executed_plan is plan
    assert workspace.reviewed_plan is plan
    assert workspace.last_result is result
