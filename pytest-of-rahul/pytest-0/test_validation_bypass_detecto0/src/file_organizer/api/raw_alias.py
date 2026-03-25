from fastapi import APIRouter
router = APIRouter()
def resolve_path(value: str, allowed: list[str]) -> str:
    return value
class Req:
    input_dir: str
class Settings:
    allowed_paths: list[str] = []
class Organizer:
    def organize(self, *, input_path: str) -> None:
        pass
organizer = Organizer()
@router.post('/x')
def unsafe(request: Req, settings: Settings) -> None:
    _ = str(resolve_path(request.input_dir, settings.allowed_paths))
    raw_input = request.input_dir
    organizer.organize(input_path=raw_input)
