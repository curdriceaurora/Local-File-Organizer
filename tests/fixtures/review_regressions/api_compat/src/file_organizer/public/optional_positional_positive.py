class FileOrganizer:
    def __init__(
        self,
        dry_run=True,
        prefetch_depth=2,
        no_prefetch=False,
    ):
        self.dry_run = dry_run
        self.prefetch_depth = prefetch_depth
        self.no_prefetch = no_prefetch
