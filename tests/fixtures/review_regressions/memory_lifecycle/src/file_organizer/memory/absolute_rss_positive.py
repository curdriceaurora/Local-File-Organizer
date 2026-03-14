"""Positive fixture: absolute RSS used directly in an assignment (no baseline subtraction)."""

import psutil


def compute_batch_size(process: psutil.Process) -> int:
    # BAD: rss used as an absolute value — should be delta from baseline
    current_rss = process.memory_info().rss
    if current_rss > 500 * 1024 * 1024:
        return 8
    return 32
