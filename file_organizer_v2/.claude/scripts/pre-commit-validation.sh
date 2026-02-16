#!/usr/bin/env bash
# Pre-commit validation script
# Runs linting and tests to ensure code quality before commit.

# Exit on any error
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting pre-commit validation...${NC}"

# Check for dependencies
for cmd in ruff pytest; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}Error: $cmd is not installed or not in PATH.${NC}"
        exit 1
    fi
done

# 1. Linting
echo -e "\n${GREEN}[1/2] Running Linting (Ruff)...${NC}"
# Check the specific modules we modified and general source
ruff check src/file_organizer/parallel tests/parallel

# 2. Testing
echo -e "\n${GREEN}[2/2] Running Tests (Pytest)...${NC}"
# Run the relevant test suites
pytest tests/parallel tests/ci/test_ruff_lint.py tests/watcher/test_queue.py

echo -e "\n${GREEN}Validation successful! Ready to commit.${NC}"
