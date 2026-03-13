from file_organizer.interfaces.pipeline import StageContext


def assign_validated_fields(context: StageContext, category: str, filename: str) -> None:
    context.category = category
    context.filename = filename
