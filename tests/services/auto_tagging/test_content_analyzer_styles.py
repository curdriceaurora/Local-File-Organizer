"""Tests for auto-tagging styles, custom prompts, and SFX categorization (#64).

Marked ci so branch coverage counts toward the diff-coverage gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.auto_tagging.content_analyzer import (
    STYLE_PRESETS,
    ContentTagAnalyzer,
)
from file_organizer.services.auto_tagging.tag_recommender import TagRecommender

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestContentAnalyzerStylesAndPrompts:
    """Test style presets and prompt guidance in ContentTagAnalyzer."""

    def test_presets_exist(self) -> None:
        assert "sfx" in STYLE_PRESETS
        assert "audio" in STYLE_PRESETS
        assert "code" in STYLE_PRESETS
        assert "hierarchical" in STYLE_PRESETS
        assert "descriptive" in STYLE_PRESETS

    def test_sfx_style_tags_sound_effects(self, tmp_path: Path) -> None:
        analyzer = ContentTagAnalyzer()
        sfx_file = tmp_path / "laser_blaster_oneshot.wav"
        sfx_file.write_bytes(b"RIFF....WAVEfmt ")

        tags = analyzer.analyze_file(sfx_file, style="sfx")
        assert "sfx" in tags
        assert "laser" in tags
        assert "blaster" in tags
        assert "oneshot" in tags

    def test_sfx_style_extracts_keywords_on_audio_file(self, tmp_path: Path) -> None:
        analyzer = ContentTagAnalyzer()
        sfx_file = tmp_path / "explosion_deep_sub.mp3"
        sfx_file.write_bytes(b"\xff\xfb\x90\x44")

        keywords = analyzer.extract_keywords(sfx_file, top_n=5, style="sfx")
        kw_names = [k for k, _ in keywords]
        assert "explosion" in kw_names or "sub" in kw_names

    def test_hierarchical_style_tags(self, tmp_path: Path) -> None:
        analyzer = ContentTagAnalyzer()
        f = tmp_path / "soundbanks" / "sci_fi_laser.wav"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"data")

        tags = analyzer.analyze_file(f, style="hierarchical")
        assert any("soundbanks" in t for t in tags)
        assert any("type-wav" in t for t in tags)

    def test_descriptive_style_tags(self, tmp_path: Path) -> None:
        analyzer = ContentTagAnalyzer()
        f = tmp_path / "cinematic_orchestral_soundtrack.mp3"
        f.write_bytes(b"data")

        tags = analyzer.analyze_file(f, style="descriptive")
        assert "cinematic" in tags
        assert "orchestral" in tags
        assert "soundtrack" in tags

    def test_custom_prompt_extracts_candidate_tags(self, tmp_path: Path) -> None:
        analyzer = ContentTagAnalyzer()
        f = tmp_path / "ambience_rain_storm.wav"
        f.write_bytes(b"data")

        prompt = "Tag this sound library with mood dark, horror, cinematic"
        tags = analyzer.analyze_file(f, custom_prompt=prompt)
        assert "dark" in tags
        assert "horror" in tags
        assert "cinematic" in tags

    def test_custom_prompt_skips_genre_emotion_and_matches_stem(self, tmp_path: Path) -> None:
        analyzer = ContentTagAnalyzer()
        f = tmp_path / "ambient_drone.wav"
        f.write_bytes(b"data")

        prompt = "Group by genre and emotion, especially ambient drone"
        tags = analyzer._extract_prompt_tags(f, prompt)
        assert "genre" not in tags
        assert "emotion" not in tags
        assert "ambient" in tags
        assert "drone" in tags

    def test_extract_keywords_boosts_preset_and_prompt_keywords_on_text(
        self, tmp_path: Path
    ) -> None:
        analyzer = ContentTagAnalyzer()
        f = tmp_path / "service.py"
        f.write_text(
            "backend service router database pipeline and custom controller logic.",
            encoding="utf-8",
        )

        keywords = analyzer.extract_keywords(
            f,
            top_n=5,
            style="code",
            custom_prompt="pipeline and router",
        )
        kw_names = [k for k, _ in keywords]
        assert any(k in kw_names for k in ("backend", "service", "pipeline", "router"))


class TestTagRecommenderStyleForwarding:
    """Test TagRecommender threading of style and prompt."""

    def test_batch_recommend_threads_style_and_prompt(self, tmp_path: Path) -> None:
        analyzer = ContentTagAnalyzer()
        recommender = TagRecommender(content_analyzer=analyzer)

        f1 = tmp_path / "laser_shot.wav"
        f2 = tmp_path / "explosion_heavy.wav"
        f1.write_bytes(b"riff")
        f2.write_bytes(b"riff")

        results = recommender.batch_recommend(
            [f1, f2],
            top_n=5,
            style="sfx",
            prompt="arcade, retro",
        )

        assert f1 in results
        assert f2 in results
        suggs_1 = [s.tag for s in results[f1].suggestions]
        suggs_2 = [s.tag for s in results[f2].suggestions]

        assert any(t in ("sfx", "laser", "arcade", "retro") for t in suggs_1)
        assert any(t in ("sfx", "explosion", "arcade", "retro") for t in suggs_2)
