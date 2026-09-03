"""Tests for canonical organization request options."""

from pathlib import Path

import pytest

from file_organizer.core.organize_options import (
    OrganizationMethodology,
    OrganizeOptions,
    OrganizeRequest,
    TransferMode,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def test_options_defaults_round_trip() -> None:
    options = OrganizeOptions()

    assert OrganizeOptions.from_dict(options.to_dict()) == options
    assert options.recursive is True
    assert options.include_hidden is False
    assert options.skip_existing is True
    assert options.effective_transfer_mode == TransferMode.HARDLINK
    assert options.effective_methodology == OrganizationMethodology.NONE
    assert "use_hardlinks" not in options.to_dict()


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
        ({"transfer_mode": "move"}, "move.*not supported"),
        ({"transfer_mode": "rename"}, "transfer_mode"),
        ({"methodology": "folders"}, "methodology"),
        (
            {"transfer_mode": "copy", "use_hardlinks": True},
            "conflicts with transfer_mode",
        ),
        ({"future_option": True}, "unknown organization option"),
        ({"generate_tags": "yes"}, "generate_tags"),
        ({"tag_style": "invalid", "generate_tags": True}, "Invalid tag_style"),
        (
            {"tag_prompt": "a" * 501, "generate_tags": True},
            "tag_prompt exceeds maximum length",
        ),
        (
            {"tag_style": "descriptive", "generate_tags": False},
            "require generate_tags=True",
        ),
        (
            {"tag_prompt": "some prompt", "generate_tags": False},
            "require generate_tags=True",
        ),
    ],
)
def test_options_reject_invalid_values(values: dict[str, object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        OrganizeOptions.from_dict(values)


def test_tag_options_round_trip() -> None:
    options = OrganizeOptions(
        generate_tags=True,
        tag_style="descriptive",
        tag_prompt="focus on genres",
    )
    assert OrganizeOptions.from_dict(options.to_dict()) == options
    assert options.generate_tags is True
    assert options.tag_style == "descriptive"
    assert options.tag_prompt == "focus on genres"


def test_tag_prompt_empty_string_normalizes_to_none() -> None:
    options = OrganizeOptions(generate_tags=True, tag_prompt="   ")
    assert options.tag_prompt is None
    assert OrganizeOptions(generate_tags=False, tag_prompt="").tag_prompt is None


def test_request_normalizes_path_like_values() -> None:
    request = OrganizeRequest("input", "output")  # type: ignore[arg-type]

    assert request.input_path == Path("input")
    assert request.output_path == Path("output")


def test_legacy_hardlink_selector_migrates_to_canonical_transfer_mode() -> None:
    options = OrganizeOptions.from_dict({"use_hardlinks": False, "methodology": "para"})

    assert options.effective_transfer_mode == TransferMode.COPY
    assert options.effective_methodology == OrganizationMethodology.PARA
    assert options.to_dict()["transfer_mode"] == "copy"
    assert "use_hardlinks" not in options.to_dict()
