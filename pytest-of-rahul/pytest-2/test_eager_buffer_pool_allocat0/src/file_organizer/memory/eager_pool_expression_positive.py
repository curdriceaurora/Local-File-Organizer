
class BufferPool:
    pass

class Owner:
    def __init__(self) -> None:
        self._pools = []
        self._pools.append(BufferPool())
