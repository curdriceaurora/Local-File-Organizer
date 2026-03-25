import pathlib
from fastapi import APIRouter
router = APIRouter()
@router.get('/x')
def unsafe_attr(path: str) -> str:
    return str(pathlib.Path(path))
