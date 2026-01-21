# Deduplication CLI Guide

## Overview

The deduplication CLI provides an interactive command-line interface for finding and removing duplicate files using hash-based detection. It supports multiple strategies, safe mode with backups, and both interactive and batch processing modes.

## Installation

The dedupe CLI is part of the File Organizer v2 package. No additional installation is required.

### Optional Dependencies

For progress bars during scanning:

```bash

pip install tqdm

```

## Basic Usage

### Interactive Mode (Default)

Find and remove duplicates interactively:

```bash

python -m file_organizer.cli.dedupe /path/to/directory

```

This will:
1. Scan the directory for duplicate files
2. Display each group of duplicates with metadata
3. Ask you to select which files to keep
4. Create backups before deletion (safe mode)
5. Remove the selected duplicates

### Dry-Run Mode

See what would be removed without actually deleting files:

```bash

python -m file_organizer.cli.dedupe /path/to/directory --dry-run

```

## Selection Strategies

### Manual Selection (Default)

Interactively choose which files to keep for each duplicate group:

```bash

python -m file_organizer.cli.dedupe ~/Documents --strategy manual

```

When prompted:
- Enter file numbers to keep (e.g., `1,3` to keep files 1 and 3)
- Enter `a` to keep all (skip deletion for this group)
- Enter `s` to skip this group entirely

### Automatic Strategies

#### Keep Oldest Files
Automatically keep the file with the oldest modification time:

```bash

python -m file_organizer.cli.dedupe ~/Downloads --strategy oldest

```

#### Keep Newest Files
Automatically keep the file with the newest modification time:

```bash

python -m file_organizer.cli.dedupe ~/Downloads --strategy newest

```

#### Keep Largest Files
Automatically keep the largest file in each group:

```bash

python -m file_organizer.cli.dedupe ~/Videos --strategy largest

```

#### Keep Smallest Files
Automatically keep the smallest file in each group:

```bash

python -m file_organizer.cli.dedupe ~/Documents --strategy smallest

```

### Batch Mode

Apply automatic strategies without per-group confirmation:

```bash

python -m file_organizer.cli.dedupe ~/Downloads --strategy oldest --batch

```

This is useful for processing large numbers of duplicate groups automatically.

## Hash Algorithms

### SHA256 (Default, Recommended)
More secure, slightly slower:

```bash

python -m file_organizer.cli.dedupe ~/Documents --algorithm sha256

```

### MD5 (Faster)
Faster but less secure (suitable for local deduplication):

```bash

python -m file_organizer.cli.dedupe ~/Documents --algorithm md5

```

## Scanning Options

### Non-Recursive Scanning
Only scan the specified directory, not subdirectories:

```bash

python -m file_organizer.cli.dedupe ~/Downloads --no-recursive

```

### Size Filters

#### Minimum File Size
Only consider files larger than a certain size (in bytes):

```bash

# Only scan files larger than 1MB
python -m file_organizer.cli.dedupe ~/Downloads --min-size 1048576

```

#### Maximum File Size
Only consider files smaller than a certain size:

```bash

# Only scan files smaller than 100MB
python -m file_organizer.cli.dedupe ~/Downloads --max-size 104857600

```

#### Combined Size Range

```bash

# Files between 1MB and 100MB
python -m file_organizer.cli.dedupe ~/Downloads \
    --min-size 1048576 \
    --max-size 104857600

```

### File Pattern Filters

#### Include Patterns
Only process files matching specific patterns:

```bash

# Only process image files
python -m file_organizer.cli.dedupe ~/Pictures \
    --include "*.jpg" \
    --include "*.png" \
    --include "*.gif"

```

#### Exclude Patterns
Skip files matching specific patterns:

```bash

# Skip temporary files
python -m file_organizer.cli.dedupe ~/Documents \
    --exclude "*.tmp" \
    --exclude "*.cache"

```

## Safety Features

### Safe Mode (Default)

By default, files are backed up before deletion:

```bash

python -m file_organizer.cli.dedupe ~/Documents

```

Backups are stored in `.file_organizer_backups/` within the scanned directory.

### Disable Safe Mode (Not Recommended)

To skip backup creation (faster but dangerous):

```bash

python -m file_organizer.cli.dedupe ~/Documents --no-safe-mode

```

⚠️ **Warning:** Use with caution! Deleted files cannot be recovered without backups.

## Complete Examples

### Example 1: Clean Up Downloads Folder

Find and remove duplicate downloads, keeping the oldest copies:

```bash

python -m file_organizer.cli.dedupe ~/Downloads \
    --strategy oldest \
    --algorithm md5 \
    --dry-run

```

Review the results, then run without `--dry-run`:

```bash

python -m file_organizer.cli.dedupe ~/Downloads \
    --strategy oldest \
    --algorithm md5

```

### Example 2: Clean Up Large Media Files

Find duplicate videos/images larger than 10MB:

```bash

python -m file_organizer.cli.dedupe ~/Media \
    --min-size 10485760 \
    --include "*.mp4" \
    --include "*.avi" \
    --include "*.mkv" \
    --include "*.jpg" \
    --include "*.png" \
    --strategy largest \
    --batch

```

### Example 3: Interactive Document Cleanup

Manually review and select duplicates in documents:

```bash

python -m file_organizer.cli.dedupe ~/Documents \
    --include "*.pdf" \
    --include "*.docx" \
    --include "*.txt" \
    --strategy manual \
    --verbose

```

### Example 4: Fast Bulk Cleanup

Quickly clean up a large directory with automatic strategy:

```bash

python -m file_organizer.cli.dedupe /data/archive \
    --algorithm md5 \
    --strategy newest \
    --batch \
    --recursive

```

## Command-Line Reference

### Required Arguments

- `directory` - Directory to scan for duplicate files

### Optional Arguments

#### Algorithm Options
- `--algorithm {md5,sha256}` - Hash algorithm (default: sha256)

#### Strategy Options
- `--strategy {manual,oldest,newest,largest,smallest}` - Selection strategy (default: manual)
- `--batch` - Batch mode: apply strategy without per-group confirmation

#### Safety Options
- `--dry-run` - Show what would be removed without deleting
- `--no-safe-mode` - Disable backups (not recommended)

#### Scanning Options
- `--no-recursive` - Don't scan subdirectories
- `--min-size BYTES` - Minimum file size to consider
- `--max-size BYTES` - Maximum file size to consider
- `--include PATTERN` - File patterns to include (can specify multiple times)
- `--exclude PATTERN` - File patterns to exclude (can specify multiple times)

#### Output Options
- `--verbose` - Enable verbose logging

## Understanding the Output

### Configuration Panel
Shows your selected options before scanning:

```

┏━━━━━━━━━━━━━━━━━━━━┓
┃   Configuration    ┃
┗━━━━━━━━━━━━━━━━━━━━┛
Directory:  /path/to/scan
Algorithm:  SHA256
Strategy:   oldest
Recursive:  Yes
Safe Mode:  Enabled
Mode:       LIVE

```

### Duplicate Group Display
For each group of duplicates:

```

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Duplicate Group 1/5            ┃
┃ Hash: abc123def456...          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

#  Path                          Size      Modified              Status
1  /path/to/file1.jpg           2.0 MB    2024-01-15 10:30:45  ✓
2  /path/to/copy_file1.jpg      2.0 MB    2024-01-20 14:22:13

Potential space savings: 2.0 MB

```

The `✓` mark indicates files that will be kept (for automatic strategies).

### Summary Report

At the end, you'll see a summary:

```

┏━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃        Summary           ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛
Duplicate groups found:  5
Total duplicate files:   12
Files removed:           7
Space saved:            15.3 MB

```

## Troubleshooting

### "No duplicate files found"
- Check if you're using the correct directory
- Try using `--recursive` if you want to scan subdirectories
- Verify file permissions (some files may be inaccessible)

### "Permission denied" errors
- Make sure you have read access to all files
- Make sure you have write access to create backups
- Try running with appropriate permissions

### Progress is slow
- Use MD5 instead of SHA256: `--algorithm md5`
- Use size filters to reduce the number of files: `--min-size`
- Consider using batch mode: `--batch`

### Out of memory errors
- The tool uses chunked reading, so this should be rare
- Try processing smaller directories separately
- Use size filters to exclude very large files temporarily

## Backup and Recovery

### Viewing Backups

Backups are stored in:

```

.file_organizer_backups/
├── manifest.json          # Backup metadata
├── file1_20240115_143045.txt
└── file2_20240115_143046.jpg

```

### Restoring Files

To restore a backup manually:
1. Navigate to `.file_organizer_backups/`
2. Find the backup file (timestamp in filename)
3. Copy it back to the original location

The manifest.json file contains the original paths.

## Best Practices

1. **Always use dry-run first**: Test with `--dry-run` before actual deletion
2. **Keep safe mode enabled**: Only disable if you're absolutely sure
3. **Start with small directories**: Test on a small directory first
4. **Review manual mode output**: Even with automatic strategies, review the output
5. **Use appropriate algorithms**: SHA256 for important files, MD5 for quick scans
6. **Combine with filters**: Use size and pattern filters to focus on specific files
7. **Keep backups**: Don't delete backups immediately after deduplication

## Integration with Scripts

You can use the dedupe CLI in scripts:

```python

from file_organizer.cli.dedupe import dedupe_command

# Run with specific arguments
exit_code = dedupe_command([
    "/path/to/directory",
    "--strategy", "oldest",
    "--dry-run"
])

if exit_code == 0:
    print("Deduplication successful")
else:
    print("Deduplication failed")

```

## Performance Tips

1. **Use MD5 for local deduplication**: It's faster and sufficient for local duplicate detection
2. **Filter by size first**: Use `--min-size` to skip small files
3. **Use batch mode**: Skip interactive prompts with `--batch`
4. **Exclude unnecessary patterns**: Use `--exclude` to skip temporary files
5. **Process in stages**: Handle different file types separately

## Safety Checklist

Before running deduplication:
- [ ] I've tested with `--dry-run`
- [ ] Safe mode is enabled (or I have other backups)
- [ ] I've reviewed the output
- [ ] I understand which files will be kept
- [ ] I have enough disk space for backups
- [ ] I'm in the correct directory

## Support

For issues or questions:
1. Check this documentation
2. Run with `--verbose` for detailed logging
3. Review the output carefully
4. Check file permissions
5. Consult the main project documentation
