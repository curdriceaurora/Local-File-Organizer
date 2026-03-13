class ModelManager:
    def __init__(self) -> None:
        self._active_models: dict[str, object] = {}

    def safe_swap(self, model_type: str, new_model: object | None) -> None:
        if new_model is None:
            self._active_models.pop(model_type, None)
            return
        self._active_models[model_type] = new_model
