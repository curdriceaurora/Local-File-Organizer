from file_organizer.interfaces.pipeline import StageContext


def assign_validated_fields(context: StageContext, category: str, filename: str) -> None:
    context.category = category
    context.filename = filename


class CategorizedThing:
    def __init__(self, category: str) -> None:
        # Deliberate direct setattr for a non-StageContext object: this locks in
        # the safe fixture case where the detector must not overreach.
        object.__setattr__(self, "category", category)
