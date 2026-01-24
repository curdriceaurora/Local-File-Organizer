# Johnny Decimal Test Fixtures

This directory contains test fixtures for Johnny Decimal numbering system testing.

## Structure

- `sample_scheme/` - Example numbering schemes
- `organized_files/` - Example files with Johnny Decimal numbers
- `unorganized_files/` - Example files to be numbered

## Usage

These fixtures are used by:
- `tests/methodologies/johnny_decimal/test_system.py`
- `tests/methodologies/johnny_decimal/test_johnny_decimal_integration.py`

## Johnny Decimal Format

Files should follow the format:
- Area: `10 Finance/`
- Category: `10.01 Budgets/`
- ID: `10.01.001 Q1 Budget.xlsx`

## Creating Test Files

Test files are created dynamically in tests using `tmp_path` fixtures.
This directory is reserved for static reference files if needed.
