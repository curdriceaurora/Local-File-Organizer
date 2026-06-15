"""WP-3.2 config schema-version + atomic/migration-safe writes (#1230).

Per the chosen design, field-level bounds stay in ``SetupWizard.validate_config``
(construct-then-validate). This module's contribution is:

- schema-version constants (``CURRENT_SCHEMA_VERSION`` / ``SUPPORTED_SCHEMA_VERSIONS``)
- ``ConfigManager`` atomic writes (no truncated/corrupt file on a mid-write crash)
- migration-safe loads: an unsupported on-disk schema version (or malformed
  data) falls back to defaults *without clobbering the file* (F6).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.config.manager import ConfigManager, UnsupportedConfigVersionError
from file_organizer.config.schema import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    AppConfig,
    ModelPreset,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# --------------------------------------------------------------------------- #
# Schema-version constants
# --------------------------------------------------------------------------- #


def test_schema_version_constants() -> None:
    assert CURRENT_SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS
    assert AppConfig().version == CURRENT_SCHEMA_VERSION


def test_schema_does_not_raise_on_unusual_values() -> None:
    """Non-raising design: the schema stays a plain dataclass so the wizard's
    construct-then-validate flow (and the web layer's broader methodology
    vocabulary) keep working."""
    cfg = AppConfig(default_methodology="content_based")
    assert cfg.default_methodology == "content_based"
    preset = ModelPreset(temperature=-0.1, max_tokens=0)  # validated by the wizard, not here
    assert preset.temperature == -0.1


# --------------------------------------------------------------------------- #
# ConfigManager atomic writes
# --------------------------------------------------------------------------- #


def test_save_load_roundtrip(tmp_path: Path) -> None:
    cm = ConfigManager(config_dir=tmp_path)
    cfg = AppConfig(
        profile_name="work",
        default_methodology="para",
        models=ModelPreset(temperature=0.7, device="cuda"),
    )
    cm.save(cfg)
    loaded = cm.load("work")
    assert loaded.default_methodology == "para"
    assert loaded.models.temperature == 0.7
    assert loaded.models.device == "cuda"


def test_save_is_atomic_no_temp_leftover(tmp_path: Path) -> None:
    """Atomic save replaces in place and leaves no temp file behind."""
    cm = ConfigManager(config_dir=tmp_path)
    cm.save(AppConfig(profile_name="default"))
    assert [p.name for p in tmp_path.iterdir()] == ["config.yaml"]


def test_delete_profile_atomic(tmp_path: Path) -> None:
    cm = ConfigManager(config_dir=tmp_path)
    cm.save(AppConfig(profile_name="default"))
    cm.save(AppConfig(profile_name="work"))

    assert cm.delete_profile("work") is True
    assert cm.list_profiles() == ["default"]
    assert [p.name for p in tmp_path.iterdir()] == ["config.yaml"]


# --------------------------------------------------------------------------- #
# Migration-safe loads (F6)
# --------------------------------------------------------------------------- #


def test_load_unsupported_version_falls_back_without_touching_disk(tmp_path: Path) -> None:
    """An unsupported schema version falls back to defaults and leaves the file
    byte-for-byte untouched so it can be migrated rather than clobbered."""
    cm = ConfigManager(config_dir=tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "profiles:\n  default:\n    version: '99.0'\n    default_methodology: para\n",
        encoding="utf-8",
    )
    before = config_path.read_bytes()

    cfg = cm.load("default")

    assert cfg.version == CURRENT_SCHEMA_VERSION  # defaults, not the on-disk profile
    assert cfg.default_methodology == "none"
    assert config_path.read_bytes() == before  # untouched on disk


def test_load_supported_version_parses_normally(tmp_path: Path) -> None:
    cm = ConfigManager(config_dir=tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "profiles:\n  default:\n    version: '1.0'\n    default_methodology: para\n",
        encoding="utf-8",
    )
    cfg = cm.load("default")
    assert cfg.default_methodology == "para"


def test_load_float_version_normalized(tmp_path: Path) -> None:
    """A YAML-parsed float version (``version: 1.0`` unquoted) is normalized via
    str() and still recognized as supported."""
    cm = ConfigManager(config_dir=tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "profiles:\n  default:\n    version: 1.0\n    default_methodology: jd\n",
        encoding="utf-8",
    )
    cfg = cm.load("default")
    assert cfg.default_methodology == "jd"
    # Normalized to a str, not left as the YAML-parsed float 1.0.
    assert cfg.version == CURRENT_SCHEMA_VERSION
    assert isinstance(cfg.version, str)


# --------------------------------------------------------------------------- #
# Save-side guard for unsupported versions (#1276)
# --------------------------------------------------------------------------- #


def _write_unsupported_profile(config_path: Path) -> bytes:
    config_path.write_text(
        "profiles:\n  default:\n    version: '99.0'\n    default_methodology: para\n",
        encoding="utf-8",
    )
    return config_path.read_bytes()


def test_save_refuses_to_overwrite_unsupported_version(tmp_path: Path) -> None:
    """A load-mutate-save on an unsupported-version profile is refused so the
    incompatible file is not clobbered with defaults (#1276)."""
    cm = ConfigManager(config_dir=tmp_path)
    config_path = tmp_path / "config.yaml"
    before = _write_unsupported_profile(config_path)

    cfg = cm.load("default")  # read-side: returns defaults, file untouched
    cfg.default_methodology = "jd"

    with pytest.raises(UnsupportedConfigVersionError):
        cm.save(cfg, "default")
    assert config_path.read_bytes() == before  # not clobbered


def test_save_force_overwrites_unsupported_version(tmp_path: Path) -> None:
    """force=True performs the deliberate migration/overwrite."""
    cm = ConfigManager(config_dir=tmp_path)
    config_path = tmp_path / "config.yaml"
    _write_unsupported_profile(config_path)

    cfg = cm.load("default")
    cm.save(cfg, "default", force=True)

    reloaded = cm.load("default")
    assert reloaded.version == CURRENT_SCHEMA_VERSION  # now a supported version


def test_save_new_profile_not_blocked(tmp_path: Path) -> None:
    """The guard only fires when overwriting an existing unsupported profile —
    saving a brand-new profile alongside it is allowed."""
    cm = ConfigManager(config_dir=tmp_path)
    config_path = tmp_path / "config.yaml"
    _write_unsupported_profile(config_path)

    cm.save(AppConfig(profile_name="fresh"), "fresh")
    assert "fresh" in cm.list_profiles()
