class PipelineOrchestrator:
    def __init__(
        self,
        config,
        injected_flag,
        stages=None,
        prefetch_depth=2,
    ):
        self.config = config
        self.injected_flag = injected_flag
        self.stages = stages
        self.prefetch_depth = prefetch_depth
