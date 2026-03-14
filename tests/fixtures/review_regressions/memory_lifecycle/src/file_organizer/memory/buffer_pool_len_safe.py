"""Safe fixture: len() used outside pool contexts — not flagged."""


def compute_checksum(data: bytearray) -> int:
    """len() used here is fine — not in a pool-related function or class."""
    return len(data)


class DataProcessor:
    def process(self, buf: bytearray) -> bool:
        # len() inside a non-pool class is fine
        return len(buf) > 0
