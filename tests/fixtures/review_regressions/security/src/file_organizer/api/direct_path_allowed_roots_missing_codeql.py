from pathlib import Path

from fastapi import APIRouter, Depends

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

router = APIRouter()


@router.get("/search")
def unsafe_search_roots(
    settings: ApiSettings = Depends(get_settings),
) -> list[Path]:
    return [Path(root).resolve() for root in settings.allowed_paths]
