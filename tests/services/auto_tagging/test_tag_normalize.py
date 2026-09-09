"""Unit tests for tag normalization and canonical validation."""

import logging
import random

import pytest

from file_organizer.services.auto_tagging.tag_normalize import (
    normalize_tag,
    normalize_tags,
    validate_canonical_tags,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


class TestNormalizeTag:
    def test_basic_lowercase_and_trim(self) -> None:
        assert normalize_tag("  Document  ") == "document"
        assert normalize_tag("Invoice-2024") == "invoice-2024"

    def test_separator_collapsing(self) -> None:
        assert normalize_tag("tax_return_2024") == "tax-return-2024"
        assert normalize_tag("bank   statement") == "bank-statement"
        assert normalize_tag("file...name!!data") == "file-name-data"
        assert normalize_tag("a--b---c") == "a-b-c"

    def test_hierarchical_slash_preservation(self) -> None:
        assert normalize_tag("media/audio") == "media/audio"
        assert normalize_tag("project/backend/api") == "project/backend/api"
        assert normalize_tag("media///audio") == "media/audio"
        assert normalize_tag("media/-audio") == "media-audio"
        assert normalize_tag("media-/audio") == "media-audio"

    def test_strip_delimiters(self) -> None:
        assert normalize_tag("-leading-hyphen") == "leading-hyphen"
        assert normalize_tag("trailing-hyphen-") == "trailing-hyphen"
        assert normalize_tag("/leading/slash") == "leading/slash"
        assert normalize_tag("trailing/slash/") == "trailing/slash"
        assert normalize_tag("-/-combo-/-") == "combo"

    def test_non_ascii_dropped_and_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG):
            assert normalize_tag("café") is None
            assert normalize_tag("résumé-2024") is None
            assert normalize_tag("タグ") is None

        assert any("Dropping non-ASCII tag" in record.message for record in caplog.records)

    def test_length_limits(self) -> None:
        # Minimum length is 2
        assert normalize_tag("a") is None
        assert normalize_tag("ab") == "ab"

        # Maximum length is 40
        tag_40 = "a" * 40
        assert normalize_tag(tag_40) == tag_40
        tag_41 = "a" * 41
        assert normalize_tag(tag_41) is None

    def test_invalid_and_empty_inputs(self) -> None:
        assert normalize_tag("") is None
        assert normalize_tag("   ") is None
        assert normalize_tag("---") is None
        assert normalize_tag("///") is None
        assert normalize_tag(123) is None  # type: ignore[arg-type]
        assert normalize_tag(None) is None  # type: ignore[arg-type]


class TestNormalizeTags:
    def test_deduplication_case_insensitive_order_preserved(self) -> None:
        raws = ["Finance", "TAX", "finance", "receipt", "Tax"]
        assert normalize_tags(raws) == ["finance", "tax", "receipt"]

    def test_drops_invalid_and_non_ascii(self) -> None:
        raws = ["valid-tag", "x", "café", "---", "another-tag"]
        assert normalize_tags(raws) == ["valid-tag", "another-tag"]

    def test_truncation_to_max_tags(self) -> None:
        raws = [f"tag-{i}" for i in range(20)]
        assert len(normalize_tags(raws, max_tags=5)) == 5
        assert normalize_tags(raws, max_tags=3) == ["tag-0", "tag-1", "tag-2"]


class TestValidateCanonicalTags:
    def test_valid_canonical_list(self) -> None:
        tags = ["document", "media/audio", "tax-2024"]
        assert validate_canonical_tags(tags) == tags
        assert validate_canonical_tags([]) == []

    def test_rejects_non_list(self) -> None:
        with pytest.raises(ValueError, match="tags must be a list"):
            validate_canonical_tags("tag1,tag2")
        with pytest.raises(ValueError, match="tags must be a list"):
            validate_canonical_tags({"tag1", "tag2"})
        with pytest.raises(ValueError, match="tags must be a list"):
            validate_canonical_tags(None)

    def test_rejects_non_string_element(self) -> None:
        with pytest.raises(ValueError, match="each tag must be a string"):
            validate_canonical_tags(["valid", 123])

    def test_rejects_count_exceeding_max(self) -> None:
        tags = [f"tag-{i}" for i in range(10)]
        with pytest.raises(ValueError, match="tags count exceeds maximum"):
            validate_canonical_tags(tags, max_tags=8)

    def test_rejects_duplicates(self) -> None:
        with pytest.raises(ValueError, match="duplicate tag 'invoice'"):
            validate_canonical_tags(["invoice", "receipt", "invoice"])

    def test_rejects_non_canonical_format(self) -> None:
        with pytest.raises(ValueError, match="not in canonical normalized form"):
            validate_canonical_tags(["Invoice"])  # Uppercase
        with pytest.raises(ValueError, match="not in canonical normalized form"):
            validate_canonical_tags(["tax return"])  # Contains space
        with pytest.raises(ValueError, match="not in canonical normalized form"):
            validate_canonical_tags(["a"])  # Too short
        with pytest.raises(ValueError, match="not in canonical normalized form"):
            validate_canonical_tags(["café"])  # Non-ASCII


class TestNormalizeTagIdempotence:
    """normalize_tag() must be a fixed point on its own output.

    validate_canonical_tags() checks a stored tag against a fresh call to
    normalize_tag() -- if the function weren't idempotent, a tag it just
    generated could fail that check on reload.
    """

    def test_known_regression_cases_are_idempotent(self) -> None:
        cases = [" f-uw2//&/5$h-", "(_e@zv// /k@*"]
        for raw in cases:
            once = normalize_tag(raw)
            assert once is not None
            assert normalize_tag(once) == once

    def test_idempotent_on_random_input(self) -> None:
        rng = random.Random(20260903)
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789/-_. !@#$%^&*() "
        for _ in range(20000):
            raw = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 15)))
            once = normalize_tag(raw)
            if once is None:
                continue
            assert normalize_tag(once) == once, (
                f"normalize_tag not idempotent for {raw!r}: "
                f"first pass {once!r}, second pass {normalize_tag(once)!r}"
            )

    def test_normalize_tag_output_is_always_load_time_valid(self) -> None:
        """Anything normalize_tag() accepts, validate_canonical_tags() must accept back."""
        cases = [" f-uw2//&/5$h-", "(_e@zv// /k@*", "media/-audio", "a--b---c"]
        for raw in cases:
            tag = normalize_tag(raw)
            if tag is not None:
                assert validate_canonical_tags([tag]) == [tag]

    def test_non_convergence_safety_net_logs_and_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Force the collapse loop's pass budget down so the defensive
        non-convergence branch actually executes, rather than relying on
        finding an input that needs an implausible number of real passes."""
        import file_organizer.services.auto_tagging.tag_normalize as tag_normalize_module

        monkeypatch.setattr(tag_normalize_module, "_MAX_COLLAPSE_PASSES", 1)
        with caplog.at_level(logging.DEBUG):
            result = normalize_tag(" f-uw2//&/5$h-")
        assert result is not None
        assert any("did not converge" in record.message for record in caplog.records)
