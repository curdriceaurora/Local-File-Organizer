from fastapi import APIRouter
router = APIRouter()
@router.get('/y')
def view2(path: str) -> str:
    return str(Path(path))
