#!/usr/bin/env bash
set -e

# Automation script to bump version, generate changelog, and push release tag

if [ -z "$1" ]; then
    echo "Usage: ./scripts/release.sh <major|minor|patch>"
    exit 1
fi

BUMP_PART=$1

# 1. Bump version across files
echo "Bumping version ($BUMP_PART)..."
python scripts/release.py bump "$BUMP_PART"

# 2. Get the new version
NEW_VER=$(grep -m 1 '^version = ' pyproject.toml | cut -d '"' -f 2)
echo "New version is $NEW_VER"

# 3. Generate changelog (assume previous tag exists, or handle if not)
PREV_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
if [ -n "$PREV_TAG" ]; then
    echo "Generating changelog from $PREV_TAG to HEAD..."
    CHANGELOG=$(python scripts/release.py changelog "$PREV_TAG" HEAD)
else
    echo "No previous tags found. First release."
    CHANGELOG="Initial release."
fi

# We could append this to CHANGELOG.md, but keeping it simple for now
# user can manually verify or we just commit the bumped version specs.

# 4. Commit and tag
git add pyproject.toml src/file_organizer/version.py src/file_organizer/__init__.py
git commit -m "chore(release): bump version to $NEW_VER"
git tag -a "v$NEW_VER" -m "Release v$NEW_VER" -m "$CHANGELOG"

echo "Done! Run 'git push origin main --tags' to publish the release."
