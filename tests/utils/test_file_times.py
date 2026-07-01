"""Tests for cross-platform file time helpers."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from file_organizer.utils.file_times import creation_timestamp

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_creation_timestamp_prefers_birthtime() -> None:
    stat_like = SimpleNamespace(st_birthtime=123.4, st_ctime=999.0, st_mtime=111.0)
    assert creation_timestamp(stat_like) == 123.4


def test_creation_timestamp_uses_windows_ctime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "nt", raising=False)
    stat_like = SimpleNamespace(st_ctime=456.7, st_mtime=222.0)
    assert creation_timestamp(stat_like) == 456.7


def test_creation_timestamp_uses_mtime_on_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "posix", raising=False)
    stat_like = SimpleNamespace(st_mtime=333.8)
    assert creation_timestamp(stat_like) == 333.8
