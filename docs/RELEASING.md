# Releasing

The GitHub Release must be created by `.github/workflows/build.yml`. Do not
hand-create or publish a release from GitHub's compare UI for a version whose
tag has already been pushed; that path can publish source archives without the
artifact-bearing Linux binaries or the CHANGELOG-sourced notes.

## Release Cut

1. Start from an up-to-date `main`.
2. Run `python scripts/cut_release.py X.Y.Z`.
3. Fill in the generated `CHANGELOG.md` section.
4. Run the normal test and release validation checks.
5. Commit the version and changelog changes.
6. Create and push the annotated tag printed by `cut_release.py`.
7. Wait for `.github/workflows/build.yml` to create the draft GitHub Release.
8. Inspect the draft release assets and notes before publishing.

## Ownership

- `build.yml` owns the GitHub Release and attaches release assets.
- `release.yml` owns PyPI publishing.
- `scripts/extract_changelog.py` supplies curated release notes from
  `CHANGELOG.md`.
- `scripts/bump_version.py --check` verifies version touchpoints before tagging.

If a release needs to be retried after publishing to PyPI, cut a new patch
version. PyPI does not allow re-uploading the same version.
