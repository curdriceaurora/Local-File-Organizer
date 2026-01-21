#!/usr/bin/env python3
"""Debug single file processing to see AI responses."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from file_organizer.services import TextProcessor
from loguru import logger

# Configure logging to DEBUG level
logger.remove()
logger.add(sys.stderr, level="DEBUG", format="<level>{level: <8}</level> | {message}")

def main():
    # Create a simple test file
    test_file = Path("/tmp/test_api_doc.md")
    test_file.write_text("""
# REST API Documentation

## Authentication
All API requests require an API key in the header.

## Endpoints

### GET /api/users
Returns a list of all users in the system.

### POST /api/users
Create a new user account.
""".strip())

    print("=" * 80)
    print("DEBUGGING SINGLE FILE PROCESSING")
    print("=" * 80)
    print(f"File: {test_file}")
    print("=" * 80)

    with TextProcessor() as processor:
        result = processor.process_file(test_file)

        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)
        print(f"Folder: {result.folder_name}")
        print(f"Filename: {result.filename}")
        print(f"Description: {result.description[:100]}...")

    # Cleanup
    test_file.unlink()

if __name__ == "__main__":
    main()
