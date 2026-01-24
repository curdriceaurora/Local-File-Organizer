#!/bin/bash
# Migration script for Python 3.9+ compatibility
# Converts union operator syntax (X | Y) to typing.Union
# Date: 2026-01-24

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Python 3.9 Migration Script ===${NC}"
echo "This script will convert union operator syntax to typing.Union"
echo ""

# Check if pyupgrade is installed
if ! command -v pyupgrade &> /dev/null; then
    echo -e "${YELLOW}pyupgrade not found. Installing...${NC}"
    pip install pyupgrade
fi

# Backup current state
echo -e "${GREEN}Step 1: Creating backup...${NC}"
git diff > migration_backup.diff
if [ -s migration_backup.diff ]; then
    echo -e "${YELLOW}Warning: Uncommitted changes detected. Backup saved to migration_backup.diff${NC}"
    echo "Commit or stash changes before continuing? (y/n)"
    read -r response
    if [[ "$response" != "y" ]]; then
        echo "Aborting migration."
        exit 1
    fi
fi

# Run pyupgrade
echo -e "${GREEN}Step 2: Converting union syntax with pyupgrade...${NC}"
find src/file_organizer -name "*.py" -type f -exec pyupgrade --py39-plus {} \;

echo -e "${GREEN}Step 3: Checking results...${NC}"
git diff --stat

# Count changes
union_changes=$(git diff | grep -c "Union\[" || true)
optional_changes=$(git diff | grep -c "Optional\[" || true)

echo ""
echo -e "${GREEN}Conversion complete!${NC}"
echo "  - Union imports added/updated: ~$union_changes"
echo "  - Optional usage updated: ~$optional_changes"
echo ""

# Ask to review
echo -e "${YELLOW}Review changes with: git diff${NC}"
echo -e "${YELLOW}To undo: git checkout .${NC}"
echo ""

# Optional: Update pyproject.toml
echo "Update pyproject.toml requires-python to >=3.9? (y/n)"
read -r update_config
if [[ "$update_config" == "y" ]]; then
    echo -e "${GREEN}Step 4: Updating pyproject.toml...${NC}"
    sed -i.bak 's/requires-python = ">=3.12"/requires-python = ">=3.9"/' pyproject.toml
    sed -i.bak 's/Programming Language :: Python :: 3.12/Programming Language :: Python :: 3.9\", \"Programming Language :: Python :: 3.10\", \"Programming Language :: Python :: 3.11\", \"Programming Language :: Python :: 3.12/' pyproject.toml
    echo "pyproject.toml updated (backup: pyproject.toml.bak)"
fi

# Run tests
echo ""
echo "Run tests now? (y/n)"
read -r run_tests
if [[ "$run_tests" == "y" ]]; then
    echo -e "${GREEN}Step 5: Running tests...${NC}"
    python -m pytest tests/ -v || echo -e "${RED}Some tests failed. Review and fix.${NC}"
fi

# Run type checking
echo ""
echo "Run mypy type checking? (y/n)"
read -r run_mypy
if [[ "$run_mypy" == "y" ]]; then
    echo -e "${GREEN}Step 6: Running mypy...${NC}"
    python -m mypy src/file_organizer --strict || echo -e "${YELLOW}Type checking found issues. Review and fix.${NC}"
fi

echo ""
echo -e "${GREEN}=== Migration Complete ===${NC}"
echo "Next steps:"
echo "  1. Review changes: git diff"
echo "  2. Test manually: python demo.py --sample"
echo "  3. Commit changes: git commit -am 'feat: Add Python 3.9+ compatibility'"
echo "  4. Update documentation: README.md, CLAUDE.md"
echo ""
echo -e "${YELLOW}See PYTHON_VERSION_MIGRATION_ANALYSIS.md for full details${NC}"
