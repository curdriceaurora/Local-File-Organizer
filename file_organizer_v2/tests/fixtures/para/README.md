# PARA Test Fixtures

This directory contains test fixtures for PARA methodology testing.

## Structure

- `sample_files/` - Sample files for different PARA categories
- `project_files/` - Example project files with deadlines
- `area_files/` - Example ongoing responsibility files
- `resource_files/` - Example reference material files
- `archive_files/` - Example archived files

## Usage

These fixtures are used by:
- `tests/methodologies/para/test_para_system.py`
- `tests/methodologies/para/test_para_integration.py`

## Creating Test Files

Test files are created dynamically in tests using `tmp_path` fixtures.
This directory is reserved for static reference files if needed.
