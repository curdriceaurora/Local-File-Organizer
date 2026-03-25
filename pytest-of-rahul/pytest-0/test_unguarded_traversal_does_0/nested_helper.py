from pathlib import Path
def outer(root: Path) -> None:
    for p in root.rglob('*.txt'):
        _ = p
    def helper(x: Path) -> None:
        if x.is_symlink():
            return
        if x.name.startswith('.'):
            return
