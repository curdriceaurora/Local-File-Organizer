from fastapi import APIRouter, Depends

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.utils import resolve_path

router = APIRouter()


class MoveRequest:
    source: str
    destination: str


def move_files(source: str, destination: str) -> None:
    raise NotImplementedError


@router.post("/move")
def unsafe_move(
    request: MoveRequest,
    settings: ApiSettings = Depends(get_settings),
) -> None:
    _validated_source = resolve_path(request.source, settings.allowed_paths)
    _validated_destination = resolve_path(request.destination, settings.allowed_paths)
    move_files(request.source, request.destination)
