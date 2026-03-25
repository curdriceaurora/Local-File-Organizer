from file_organizer.interfaces.pipeline import StageContext
def producer() -> None:
    ctx: StageContext
def unrelated() -> None:
    object.__setattr__(ctx, 'category', 'x')
