"""Shared fixtures and helpers for daemon tests."""

from __future__ import annotations

import os
from contextlib import contextmanager


@contextmanager
def wired_pipe(daemon):
    """Create a non-blocking self-pipe wired to a DaemonService instance.

    Sets ``daemon._sig_wakeup_r`` and ``daemon._sig_wakeup_w`` and yields
    ``(read_fd, write_fd)``.  Closes both fds on exit.
    """
    r, w = os.pipe()
    os.set_blocking(r, False)
    os.set_blocking(w, False)
    daemon._sig_wakeup_r = r
    daemon._sig_wakeup_w = w
    try:
        yield r, w
    finally:
        os.close(r)
        os.close(w)
