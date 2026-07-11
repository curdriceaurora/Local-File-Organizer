"""CI guardrail: hardcoded version stamps must match file_organizer.version.__version__.

version.py is the single source of truth for the package version, but a
handful of other files also carry their own copy of it (doc "**Version**:
X.Y.Z" stamps, the Windows desktop manifest's assembly version). Nothing
enforced agreement between them, so they drifted independently across past
release cycles (see #1540). This test fails CI the moment a stamp
disagrees, instead of relying on someone noticing in review.

Reuses ``scripts/bump_version.py``'s ``TOUCHPOINTS`` list (and each
touchpoint's ``expected()`` formatter) so the set of tracked files and their
expected values can't drift between the script and this test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from bump_version import TOUCHPOINTS, Touchpoint  # noqa: E402

from file_organizer.version import __version__  # noqa: E402

pytestmark = pytest.mark.ci


@pytest.mark.parametrize(
    "touchpoint", TOUCHPOINTS, ids=[str(tp.path.relative_to(REPO_ROOT)) for tp in TOUCHPOINTS]
)
def test_version_stamp_matches_source_of_truth(touchpoint: Touchpoint) -> None:
    """Every tracked version stamp must equal __version__ (via its formatter)."""
    text = touchpoint.path.read_text(encoding="utf-8")
    match = touchpoint.pattern.search(text)
    assert match is not None, f"{touchpoint.path}: no version stamp found"

    stamped = match.group("version")
    expected = touchpoint.expected(__version__)
    assert stamped == expected, (
        f"{touchpoint.path.relative_to(REPO_ROOT)} stamps version {stamped!r}, but "
        f"file_organizer.version.__version__ is {__version__!r} (expected {expected!r}). "
        "Run `python scripts/bump_version.py` to fix."
    )
