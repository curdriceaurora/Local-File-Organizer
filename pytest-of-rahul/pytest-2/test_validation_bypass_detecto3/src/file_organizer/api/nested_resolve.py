from fastapi import APIRouter
router = APIRouter()
def resolve_path(v, allowed): return v
class Req:
    input_dir: str
class Settings:
    allowed_paths: list = []
class Organizer:
    def organize(self, *, input_path): pass
organizer = Organizer()
@router.post('/x')
def handler(request: Req, settings: Settings) -> None:
    def _validate():
        return resolve_path(request.input_dir, settings.allowed_paths)
    organizer.organize(input_path=request.input_dir)
