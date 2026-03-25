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
    user_path = resolve_path(request.input_dir, settings.allowed_paths)
    user_path = request.input_dir
    user_path = resolve_path(request.input_dir, settings.allowed_paths)
    organizer.organize(input_path=user_path)
