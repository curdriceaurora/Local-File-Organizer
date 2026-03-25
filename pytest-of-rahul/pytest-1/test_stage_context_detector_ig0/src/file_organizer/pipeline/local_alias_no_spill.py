def importer() -> None:
    from file_organizer.interfaces.pipeline import StageContext as SC
    sc: SC
def unrelated(sc: object) -> None:
    object.__setattr__(sc, 'category', 'x')
