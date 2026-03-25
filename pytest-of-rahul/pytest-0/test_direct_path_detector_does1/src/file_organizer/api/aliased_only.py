from pathlib import Path as P
from fastapi import APIRouter
router = APIRouter()
@router.get('/x')
def view(path: str) -> str:
    return str(P(path))
