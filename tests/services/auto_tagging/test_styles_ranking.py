"""Unit and integration tests for ScoredTag and rank_tag_candidates in styles.py."""

from __future__ import annotations

import pytest

from file_organizer.services.auto_tagging.styles import (
    CODE_LANG_VOCAB,
    SFX_VOCAB,
    STYLE_PRESETS,
    ScoredTag,
    normalize_tag_prompt,
    rank_tag_candidates,
    validate_tag_style,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit, pytest.mark.integration]


class TestScoredTag:
    def test_initialization(self) -> None:
        tag = ScoredTag(tag="python", score=0.8, sources=("filename",))
        assert tag.tag == "python"
        assert tag.score == 0.8
        assert tag.sources == ("filename",)

    def test_sources_conversion(self) -> None:
        tag = ScoredTag(tag="python", score=1.0, sources=["filename", "directory"])  # type: ignore[arg-type]
        assert tag.sources == ("filename", "directory")

    def test_type_validation_tag(self) -> None:
        with pytest.raises(TypeError, match="tag must be a string"):
            ScoredTag(tag=123, score=1.0, sources=("filename",))  # type: ignore[arg-type]

    def test_type_validation_score(self) -> None:
        with pytest.raises(TypeError, match="score must be numeric"):
            ScoredTag(tag="py", score="1.0", sources=("filename",))  # type: ignore[arg-type]

    def test_immutability(self) -> None:
        tag = ScoredTag(tag="python", score=0.8, sources=("filename",))
        with pytest.raises(AttributeError):
            tag.score = 1.0  # type: ignore[misc]


class TestRankTagCandidates:
    def test_empty_candidates(self) -> None:
        assert rank_tag_candidates([]) == []

    def test_all_invalid_candidates_dropped(self) -> None:
        candidates = [
            ScoredTag(tag="", score=1.0, sources=("filename",)),
            ScoredTag(tag="a", score=1.0, sources=("filename",)),  # length < 2
            ScoredTag(tag="!@#$", score=1.0, sources=("filename",)),
            ScoredTag(tag="café", score=1.0, sources=("filename",)),  # non-ASCII
            ScoredTag(tag="a" * 41, score=1.0, sources=("filename",)),  # length > 40
        ]
        assert rank_tag_candidates(candidates) == []

    def test_normalization_and_deduplication_merge(self) -> None:
        candidates = [
            ScoredTag(tag="My_Report", score=0.6, sources=("directory",)),
            ScoredTag(tag="my-report", score=1.0, sources=("filename",)),
        ]
        ranked = rank_tag_candidates(candidates)
        assert len(ranked) == 1
        assert ranked[0].tag == "my-report"
        assert ranked[0].score == 1.0
        assert ranked[0].sources == ("directory", "filename")

    def test_deterministic_tie_breaking(self) -> None:
        candidates = [
            ScoredTag(tag="zebra", score=0.5, sources=("filename",)),
            ScoredTag(tag="apple", score=0.5, sources=("filename",)),
            ScoredTag(tag="banana", score=0.8, sources=("filename",)),
        ]
        ranked = rank_tag_candidates(candidates)
        assert [r.tag for r in ranked] == ["banana", "apple", "zebra"]

    def test_top_n_limiting(self) -> None:
        candidates = [
            ScoredTag(tag="one", score=0.9, sources=("filename",)),
            ScoredTag(tag="two", score=0.8, sources=("filename",)),
            ScoredTag(tag="three", score=0.7, sources=("filename",)),
        ]
        assert len(rank_tag_candidates(candidates, top_n=2)) == 2
        assert len(rank_tag_candidates(candidates, top_n=None)) == 3

    def test_prompt_boost_matches_existing_candidate(self) -> None:
        candidates = [
            ScoredTag(tag="finance", score=0.6, sources=("filename",)),
            ScoredTag(tag="report", score=0.6, sources=("directory",)),
        ]
        ranked = rank_tag_candidates(candidates, prompt="Focus on finance!")
        # finance should receive 1.5x boost: 0.6 * 1.5 = 0.9
        assert ranked[0].tag == "finance"
        assert ranked[0].score == pytest.approx(0.9)
        assert "prompt" in ranked[0].sources
        assert ranked[1].tag == "report"
        assert ranked[1].score == pytest.approx(0.6)

    def test_prompt_cannot_invent_unrelated_tags(self) -> None:
        candidates = [
            ScoredTag(tag="invoice", score=0.6, sources=("filename",)),
        ]
        ranked = rank_tag_candidates(candidates, prompt="space galaxy rocket")
        assert len(ranked) == 1
        assert ranked[0].tag == "invoice"

    def test_prompt_token_filters_stopwords_and_short_tokens(self) -> None:
        candidates = [
            ScoredTag(tag="the", score=0.6, sources=("filename",)),
            ScoredTag(tag="code", score=0.6, sources=("filename",)),
        ]
        stop_words = {"the"}
        ranked = rank_tag_candidates(candidates, prompt="the a code", stop_words=stop_words)
        code_tag = next(r for r in ranked if r.tag == "code")
        assert code_tag.score == pytest.approx(0.9)  # boosted
        the_tag = next(r for r in ranked if r.tag == "the")
        assert the_tag.score == pytest.approx(0.6)  # not boosted

    def test_sfx_and_audio_style_boost(self) -> None:
        sample_sfx = next(iter(SFX_VOCAB))
        candidates = [
            ScoredTag(tag=sample_sfx, score=0.5, sources=("filename",)),
            ScoredTag(tag="other", score=0.5, sources=("filename",)),
        ]
        # Test "sfx"
        ranked_sfx = rank_tag_candidates(candidates, style="sfx")
        assert ranked_sfx[0].tag == sample_sfx
        assert ranked_sfx[0].score == pytest.approx(1.0)
        assert "style" in ranked_sfx[0].sources

        # Test "audio" alias behaves identically
        ranked_audio = rank_tag_candidates(candidates, style="audio")
        assert ranked_audio[0].tag == sample_sfx
        assert ranked_audio[0].score == pytest.approx(1.0)
        assert "style" in ranked_audio[0].sources

    def test_code_style_boost_and_compound_tag(self) -> None:
        candidates = [
            ScoredTag(tag="py", score=0.8, sources=("extension",)),
            ScoredTag(tag="python", score=0.7, sources=("content",)),
            ScoredTag(tag="unrelated", score=0.5, sources=("filename",)),
        ]
        ranked = rank_tag_candidates(candidates, style="code")
        tags = {r.tag: r for r in ranked}

        # Extension and lang names in CODE_LANG_VOCAB get 2x boost
        assert tags["py"].score == pytest.approx(1.6)
        assert "style" in tags["py"].sources
        assert tags["python"].score == pytest.approx(1.4)
        assert "style" in tags["python"].sources

        # Compound lang/<ext> emitted
        assert "lang/py" in tags
        assert tags["lang/py"].sources == ("style",)
        assert tags["lang/py"].score == pytest.approx(tags["py"].score)

    def test_descriptive_style_boosts_only_structural_long_tags(self) -> None:
        candidates = [
            # Long structural tag (> 6 chars) -> boosted 1.2x
            ScoredTag(tag="quarterly", score=0.6, sources=("filename",)),
            # Short structural tag (<= 6 chars) -> NOT boosted
            ScoredTag(tag="short", score=0.6, sources=("filename",)),
            # Long content tag (> 6 chars) -> NOT boosted (avoids double-boosting)
            ScoredTag(tag="financials", score=0.6, sources=("content",)),
        ]
        ranked = rank_tag_candidates(candidates, style="descriptive")
        tags = {r.tag: r for r in ranked}
        assert tags["quarterly"].score == pytest.approx(0.72)
        assert "style" in tags["quarterly"].sources
        assert tags["short"].score == pytest.approx(0.6)
        assert "style" not in tags["short"].sources
        assert tags["financials"].score == pytest.approx(0.6)
        assert "style" not in tags["financials"].sources

    def test_hierarchical_compound_tags(self) -> None:
        candidates = [
            ScoredTag(tag="image", score=0.8, sources=("extension",)),
            ScoredTag(tag="nature", score=0.7, sources=("directory",)),
            ScoredTag(tag="sunset", score=0.6, sources=("content",)),
        ]
        ranked = rank_tag_candidates(candidates, style="hierarchical")
        tags = {r.tag: r for r in ranked}
        assert "image/nature" in tags
        assert tags["image/nature"].score == pytest.approx(0.8)
        assert tags["image/nature"].sources == ("style",)
        assert "image/sunset" in tags
        assert tags["image/sunset"].score == pytest.approx(0.8)
        assert tags["image/sunset"].sources == ("style",)

    def test_compound_merges_with_existing_if_duplicate(self) -> None:
        candidates = [
            ScoredTag(tag="image", score=0.8, sources=("extension",)),
            ScoredTag(tag="nature", score=0.7, sources=("directory",)),
            ScoredTag(tag="image/nature", score=0.5, sources=("filename",)),
        ]
        ranked = rank_tag_candidates(candidates, style="hierarchical")
        comp = next(r for r in ranked if r.tag == "image/nature")
        assert comp.score == pytest.approx(0.8)
        assert "filename" in comp.sources
        assert "style" in comp.sources

    def test_validation_helpers_coverage(self) -> None:
        # Additional coverage for validation functions to guarantee 100% floor
        assert "py" in CODE_LANG_VOCAB
        validate_tag_style(None)
        for s in STYLE_PRESETS:
            validate_tag_style(s)
        with pytest.raises(ValueError):
            validate_tag_style("unknown")
        with pytest.raises(ValueError):
            validate_tag_style(42)  # type: ignore[arg-type]

        assert normalize_tag_prompt(None) is None
        assert normalize_tag_prompt("   ") is None
        assert normalize_tag_prompt("hello") == "hello"
        with pytest.raises(ValueError):
            normalize_tag_prompt(42)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            normalize_tag_prompt("a" * 501)

    def test_whitespace_only_prompt_does_not_boost(self) -> None:
        candidates = [ScoredTag(tag="report", score=0.6, sources=("filename",))]
        ranked = rank_tag_candidates(candidates, prompt="   ")
        assert len(ranked) == 1
        assert ranked[0].score == pytest.approx(0.6)
        assert "prompt" not in ranked[0].sources

    def test_boost_with_preexisting_sources(self) -> None:
        # Candidate already has "style" and "prompt"
        candidates = [
            ScoredTag(tag="ambient", score=0.5, sources=("style", "prompt")),
            ScoredTag(tag="python", score=0.5, sources=("style", "prompt")),
            ScoredTag(tag="landscape", score=0.5, sources=("filename", "style")),
        ]
        ranked_sfx = rank_tag_candidates(candidates, style="sfx", prompt="ambient")
        ambient = next(r for r in ranked_sfx if r.tag == "ambient")
        assert ambient.sources.count("style") == 1
        assert ambient.sources.count("prompt") == 1

        ranked_code = rank_tag_candidates(candidates, style="code")
        py_tag = next(r for r in ranked_code if r.tag == "python")
        assert py_tag.sources.count("style") == 1

        ranked_desc = rank_tag_candidates(candidates, style="descriptive")
        land_tag = next(r for r in ranked_desc if r.tag == "landscape")
        assert land_tag.sources.count("style") == 1

    def test_hierarchical_long_compound_rejected(self) -> None:
        # cat + sub > 40 chars -> normalize_tag returns None
        cat = "a" * 25
        sub = "b" * 25
        candidates = [
            ScoredTag(tag=cat, score=0.8, sources=("extension",)),
            ScoredTag(tag=sub, score=0.6, sources=("directory",)),
        ]
        ranked = rank_tag_candidates(candidates, style="hierarchical")
        # No compound candidate should be created
        assert all("/" not in r.tag for r in ranked)
