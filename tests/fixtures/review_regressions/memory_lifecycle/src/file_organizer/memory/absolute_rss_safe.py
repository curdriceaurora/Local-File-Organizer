"""Safe fixture: RSS used as a delta (subtracted from baseline)."""

import psutil


def compute_batch_size(process: psutil.Process, baseline_rss: int) -> int:
    # GOOD: delta from baseline, not absolute value
    rss_delta = process.memory_info().rss - baseline_rss
    if rss_delta > 100 * 1024 * 1024:
        return 8
    return 32
