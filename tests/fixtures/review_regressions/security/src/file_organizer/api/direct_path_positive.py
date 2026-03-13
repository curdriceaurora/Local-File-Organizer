from pathlib import Path

from fastapi import APIRouter, Depends

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

router = APIRouter()


@router.get("/files")
def unsafe_lookup(
    path: str,
    settings: ApiSettings = Depends(get_settings),
) -> str:
    target = Path(path)
    return str(target)
