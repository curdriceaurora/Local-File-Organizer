from pathlib import Path
from fastapi import APIRouter
router = APIRouter()
@router.get('/x')
def unsafe(path: str) -> str:
    # codeql[py/path-injection]
    return str(Path(path))
