class ModelManager:
    def __init__(self) -> None:
        self._active_models: dict[str, object] = {}

    def broken_swap(self, model_type: str, new_model_id: str, new_model: object | None) -> None:
        selected_model: str = new_model_id
        if new_model is None:
            self._active_models[model_type] = selected_model
            return
        self._active_models[model_type] = new_model
        fallback_model = "fallback-id"
        self._active_models["fallback"] = fallback_model
