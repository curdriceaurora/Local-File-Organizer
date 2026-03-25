import file_organizer.api.utils as utils
from fastapi import APIRouter
router = APIRouter()
class Req:
    input_dir: str
class Settings:
    allowed_paths: list = []
class Organizer:
    def organize(self, *, input_path): pass
organizer = Organizer()
@router.post('/x')
def handler(request: Req, settings: Settings) -> None:
    _v = utils.resolve_path(request.input_dir, settings.allowed_paths)
    organizer.organize(input_path=request.input_dir)
