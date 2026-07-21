"""Tests for canonical organization request options."""

from pathlib import Path

import pytest

from file_organizer.core.organize_options import OrganizeOptions, OrganizeRequest

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def test_options_defaults_round_trip() -> None:
    options = OrganizeOptions()

    assert OrganizeOptions.from_dict(options.to_dict()) == options
    assert options.recursive is True
    assert options.include_hidden is False
    assert options.skip_existing is True


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"parallel_workers": 0}, "parallel_workers"),
        ({"prefetch_depth": -1}, "prefetch_depth"),
        ({"max_transcribe_seconds": -1}, "max_transcribe_seconds"),
        ({"whisper_model": " "}, "whisper_model"),
        ({"text_model": ""}, "text_model"),
        ({"vision_provider": "unknown"}, "vision_provider"),
        ({"recursive": "yes"}, "recursive"),
        ({"prefetch_depth": True}, "prefetch_depth"),
        ({"future_option": True}, "unknown organization option"),
    ],
)
def test_options_reject_invalid_values(values: dict[str, object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        OrganizeOptions.from_dict(values)


def test_request_normalizes_path_like_values() -> None:
    request = OrganizeRequest("input", "output")  # type: ignore[arg-type]

    assert request.input_path == Path("input")
    assert request.output_path == Path("output")
