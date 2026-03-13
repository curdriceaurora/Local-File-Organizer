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
