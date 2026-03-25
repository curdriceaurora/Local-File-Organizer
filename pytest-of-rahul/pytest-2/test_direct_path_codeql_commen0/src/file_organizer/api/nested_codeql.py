from pathlib import Path
from fastapi import APIRouter
router = APIRouter()
@router.get('/x')
def handler(path: str) -> str:
    def _inner() -> str:
        # codeql[py/path-injection]
        return str(Path(path))
    return _inner()
