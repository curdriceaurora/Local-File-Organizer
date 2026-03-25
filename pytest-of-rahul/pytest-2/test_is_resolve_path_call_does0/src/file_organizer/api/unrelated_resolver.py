from fastapi import APIRouter
router = APIRouter()
class PathHelper:
    def resolve_path(self, v, allowed): return v
class Req:
    input_dir: str
class Settings:
    allowed_paths: list = []
class Organizer:
    def organize(self, *, input_path): pass
helper = PathHelper()
organizer = Organizer()
@router.post('/x')
def handler(request: Req, settings: Settings) -> None:
    _v = helper.resolve_path(request.input_dir, settings.allowed_paths)
    organizer.organize(input_path=request.input_dir)
