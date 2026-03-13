from fastapi import APIRouter, BackgroundTasks, Depends

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.utils import resolve_path

router = APIRouter()


class OrganizeRequest:
    input_dir: str
    output_dir: str


def run_job(job_id: str, request: OrganizeRequest) -> None:
    raise NotImplementedError


class Organizer:
    def organize(self, *, input_path: str, output_path: str) -> None:
        raise NotImplementedError


organizer = Organizer()


@router.post("/organize")
def unsafe_execute(
    request: OrganizeRequest,
    background_tasks: BackgroundTasks,
    settings: ApiSettings = Depends(get_settings),
) -> None:
    _validated_input = resolve_path(request.input_dir, settings.allowed_paths)
    _validated_output = resolve_path(request.output_dir, settings.allowed_paths)
    background_tasks.add_task(run_job, "job-1", request)
    organizer.organize(input_path=request.input_dir, output_path=request.output_dir)
