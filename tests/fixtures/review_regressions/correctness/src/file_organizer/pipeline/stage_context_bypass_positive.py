from file_organizer.interfaces.pipeline import StageContext


def bypass_validated_fields(context: StageContext, category: str, filename: str) -> None:
    object.__setattr__(context, "category", category)
    object.__setattr__(context, "filename", filename)
