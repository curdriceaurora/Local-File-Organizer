from fastapi import APIRouter, BackgroundTasks, Depends

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.utils import resolve_path

router = APIRouter()


class OrganizeRequest:
    input_dir: str
    output_dir: str

    def model_copy(self, *, update: dict[str, str]) -> "OrganizeRequest":
        raise NotImplementedError


def run_job(job_id: str, request: OrganizeRequest) -> None:
    raise NotImplementedError


def preview_job(request: OrganizeRequest) -> None:
    raise NotImplementedError


class ScanRequest:
    path: str


class Organizer:
    def organize(self, *, input_path: str, output_path: str) -> None:
        raise NotImplementedError


organizer = Organizer()


@router.post("/organize")
def safe_execute(
    request: OrganizeRequest,
    background_tasks: BackgroundTasks,
    settings: ApiSettings = Depends(get_settings),
) -> None:
    input_path = resolve_path(request.input_dir, settings.allowed_paths)
    output_path = resolve_path(request.output_dir, settings.allowed_paths)
    safe_request = request.model_copy(
        update={"input_dir": str(input_path), "output_dir": str(output_path)}
    )
    background_tasks.add_task(run_job, "job-1", safe_request)
    organizer.organize(input_path=str(input_path), output_path=str(output_path))


@router.post("/organize-preview")
def safe_preview(
    request: OrganizeRequest,
    background_tasks: BackgroundTasks,
    settings: ApiSettings = Depends(get_settings),
) -> None:
    # preview_job intentionally receives the raw request before validation so this
    # fixture exercises the detector's "before validation" boundary.
    background_tasks.add_task(preview_job, request)
    input_path = resolve_path(request.input_dir, settings.allowed_paths)
    output_path = resolve_path(request.output_dir, settings.allowed_paths)
    _scan_request = ScanRequest(path=request.input_dir)
    safe_request = request.model_copy(
        update={"input_dir": str(input_path), "output_dir": str(output_path)}
    )
    # run_job and organizer.organize use the sanitized copies/aliases, not the raw
    # request fields, which is the safe post-validation pattern this fixture locks in.
    background_tasks.add_task(run_job, "job-2", safe_request)
    organizer.organize(input_path=str(input_path), output_path=str(output_path))
