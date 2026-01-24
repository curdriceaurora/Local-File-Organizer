# Phase 3 Troubleshooting Guide

## Overview

This guide helps you diagnose and resolve common issues with Phase 3 features, including organization methodologies, file format support, and system configuration.

## Table of Contents

- [PARA Methodology Issues](#para-methodology-issues)
- [Johnny Decimal Issues](#johnny-decimal-issues)
- [File Format Issues](#file-format-issues)
- [Installation & Dependencies](#installation--dependencies)
- [Performance Issues](#performance-issues)
- [Integration Issues](#integration-issues)

---

## PARA Methodology Issues

### Files Categorized Incorrectly

**Symptom**: Files are placed in the wrong PARA category.

**Causes**:
1. Low confidence score (< 70%)
2. Ambiguous file content
3. Missing custom rules

**Solutions**:

**Check Confidence Score**:
```python
from file_organizer.methodologies.para import PARACategorizer

categorizer = PARACategorizer()
result = categorizer.categorize(file_path)

if result.confidence < 0.7:
    print(f"Low confidence: {result.confidence:.2%}")
    print(f"Alternatives: {result.alternative_categories}")
```

**Add Custom Rules**:
```python
from file_organizer.methodologies.para import PARARule, PARACategory

# Create specific rule for your domain
custom_rule = PARARule(
    name="My Work Projects",
    category=PARACategory.PROJECTS,
    conditions={
        "keywords": ["deliverable", "client", "deadline"],
        "path_contains": "/work/"
    },
    priority=10
)

config.add_rule(custom_rule)
```

**Provide Feedback**:
```python
from file_organizer.methodologies.para import PARASuggestionEngine

engine = PARASuggestionEngine()

# Correct the categorization
engine.reject_suggestion(
    file_path,
    suggested_category=PARACategory.PROJECTS,
    correct_category=PARACategory.AREAS,
    feedback="This is ongoing maintenance"
)
```

### Auto-Categorization Too Slow

**Symptom**: Categorization takes > 5 seconds per file.

**Causes**:
1. AI model not optimized
2. Large file content
3. Too many custom rules

**Solutions**:

**Adjust Confidence Threshold**:
```yaml
# ~/.config/file-organizer/config.yaml
para:
  confidence_threshold: 0.8  # Higher = fewer files categorized, but faster
```

**Disable Smart Suggestions**:
```python
config = PARAConfig(
    auto_categorize=True,
    use_smart_suggestions=False  # Faster, but less intelligent
)
```

**Limit Content Analysis**:
```python
# Only analyze first 1000 characters
content = file_content[:1000]
result = categorizer.categorize(file_path, content=content)
```

### Too Many Subcategories Created

**Symptom**: Deep folder hierarchies (Projects/Work/Client-A/Phase-1/...).

**Causes**:
1. Over-organization
2. Incorrect mixed_folder_strategy

**Solutions**:

**Keep Hierarchy Flat**:
```yaml
para:
  max_depth: 2  # Limit folder depth
  mixed_folder_strategy: "dominant"  # Don't split into subfolders
```

**Simplify Structure**:
```bash
# Use flat structure
1-Projects/
├── Client-A-Project-X/
└── Client-B-Project-Y/

# Not:
1-Projects/
└── Client-A/
    └── Projects/
        └── Project-X/
```

### Auto-Archive Not Working

**Symptom**: Old projects not automatically archived.

**Causes**:
1. Auto-archive disabled
2. Incorrect date detection

**Solutions**:

**Enable Auto-Archive**:
```python
config = PARAConfig(
    auto_archive=True,
    archive_after_days=90
)
```

**Manual Archive**:
```bash
# Archive projects older than 90 days
file-organizer archive-old --days 90 --category projects
```

---

## Johnny Decimal Issues

### Number Conflicts

**Symptom**: "Number already exists" error.

**Causes**:
1. Duplicate number assignment
2. Existing files not imported

**Solutions**:

**Find Conflicts**:
```bash
file-organizer jd check-conflicts ~/Documents
```

**Auto-Resolve**:
```bash
# Increment strategy (11.04 → 11.05)
file-organizer jd resolve-conflicts ~/Documents --strategy increment

# Skip strategy (move to next category)
file-organizer jd resolve-conflicts ~/Documents --strategy skip
```

**Import Existing**:
```python
from file_organizer.methodologies.johnny_decimal import JohnnyDecimalGenerator

generator = JohnnyDecimalGenerator()
generator.import_existing_structure("~/Documents")
```

### Category Full (99 Items)

**Symptom**: "Category 11 is full" error.

**Causes**:
1. Too many files in one category
2. No archiving strategy

**Solutions**:

**Archive Old Items**:
```bash
# Move old items to archive
file-organizer jd archive 11 --older-than 1year
```

**Split Category**:
```bash
# Split category 11 into 11 and 15
file-organizer jd split-category 11 --into 11,15
```

**Use Sub-Categories** (temporary):
```python
# Use decimal notation (not ideal, but works)
# 11.01a, 11.01b, etc.
```

### Wrong Category Assignment

**Symptom**: Files assigned to incorrect categories.

**Causes**:
1. Ambiguous content
2. Missing keywords in category definition

**Solutions**:

**Add Keywords**:
```python
from file_organizer.methodologies.johnny_decimal import CategoryDefinition

# Update category keywords
category = CategoryDefinition(
    category_number=11,
    name="Company documents",
    keywords=["registration", "license", "insurance", "certification"]
)

scheme.add_category(category)
```

**Manual Reassignment**:
```bash
# Move file to correct category
file-organizer jd reassign 11.04 --to-category 12
# System automatically assigns new number in category 12
```

### Number Validation Errors

**Symptom**: "Invalid number format" error.

**Causes**:
1. Incorrect format (not XX.YY)
2. Out of range (> 99.99)

**Solutions**:

**Validate Before Assignment**:
```python
from file_organizer.methodologies.johnny_decimal import validate_number

if validate_number("11.04"):
    # Proceed
else:
    print("Invalid format")
```

**Common Mistakes**:
```python
# ❌ Wrong
validate_number("11.100")  # ID must be 00-99
validate_number("100.01")  # Category must be 00-99
validate_number("11")      # Missing ID
validate_number("11.4")    # ID must be two digits

# ✅ Correct
validate_number("11.04")
validate_number("00.01")
validate_number("99.99")
```

---

## File Format Issues

### EPUB Files Not Recognized

**Symptom**: EPUB files not processed correctly.

**Causes**:
1. Corrupted EPUB file
2. Missing dependency

**Solutions**:

**Verify EPUB**:
```bash
# Check file integrity
file-organizer validate book.epub
```

**Reinstall Dependencies**:
```bash
pip install --upgrade ebooklib
```

**Manual Extraction**:
```python
from file_organizer.utils.file_readers import read_epub_file

try:
    content, metadata = read_epub_file("book.epub")
except Exception as e:
    print(f"EPUB error: {e}")
```

### Archive Analysis Too Slow

**Symptom**: ZIP/TAR files take > 10 seconds to analyze.

**Causes**:
1. Large archive size
2. Nested archives
3. Many files in archive

**Solutions**:

**Disable Content Analysis**:
```yaml
file_formats:
  analyze_archive_contents: false  # Just look at filename
```

**Set Size Limit**:
```yaml
file_formats:
  max_archive_size_mb: 500  # Skip archives larger than 500 MB
```

**Skip Nested Archives**:
```yaml
file_formats:
  max_archive_depth: 1  # Don't analyze nested archives
```

### CAD Files Not Loading

**Symptom**: DXF/DWG files fail to process.

**Causes**:
1. Missing dependencies
2. Unsupported CAD version
3. Corrupted file

**Solutions**:

**Install Dependencies**:
```bash
pip install ezdxf
```

**Check Version**:
```python
from file_organizer.utils.file_readers import read_cad_file

try:
    info = read_cad_file("design.dxf")
except Exception as e:
    print(f"CAD error: {e}")
    # Try converting to newer format
```

**Use DXF Instead of DWG**:
```bash
# Convert DWG to DXF (if you have AutoCAD or LibreCAD)
# DXF is better supported
```

### Scientific Formats (Phase 3)

**Symptom**: HDF5/NetCDF not working.

**Status**: These are Phase 3 placeholders (not yet fully implemented).

**Solutions**:

**Check Status**:
```bash
file-organizer feature-status scientific-formats
```

**Get Notified**:
```bash
file-organizer notify-me scientific-formats
```

**Alternative**:
```python
# Use external tools for now
import h5py

# Process HDF5 manually
with h5py.File("data.h5", "r") as f:
    # Extract data
```

---

## Installation & Dependencies

### Ollama Not Found

**Symptom**: "Ollama not found" or "Model not available" error.

**Solutions**:

**Install Ollama**:
```bash
# macOS/Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Or download from ollama.ai
```

**Pull Models**:
```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

**Verify Installation**:
```bash
ollama list
ollama run qwen2.5:3b-instruct-q4_K_M "Hello"
```

### Missing Python Dependencies

**Symptom**: "ModuleNotFoundError" errors.

**Solutions**:

**Install All Dependencies**:
```bash
pip install file-organizer-v2[phase3-all]
```

**Install Specific Features**:
```bash
# Audio support
pip install file-organizer-v2[audio]

# CAD support
pip install file-organizer-v2[cad]

# Archive support
pip install file-organizer-v2[archive]

# Scientific formats
pip install file-organizer-v2[scientific]
```

**Verify Installation**:
```bash
file-organizer --version
file-organizer test-dependencies
```

### Version Conflicts

**Symptom**: Dependency version conflicts.

**Solutions**:

**Create Fresh Environment**:
```bash
python3 -m venv venv-fresh
source venv-fresh/bin/activate
pip install file-organizer-v2[phase3-all]
```

**Update All Dependencies**:
```bash
pip install --upgrade file-organizer-v2
pip install --upgrade -r requirements.txt
```

---

## Performance Issues

### Slow File Processing

**Symptom**: Processing takes > 5 seconds per file.

**Causes**:
1. Large files
2. Slow AI model
3. Too much analysis

**Solutions**:

**Use Faster Model** (if available):
```python
from file_organizer.models import TextModel, ModelConfig

config = ModelConfig(
    name="qwen2.5:1.5b-instruct-q4_K_M",  # Smaller, faster
    temperature=0.3  # Less creative, faster
)

model = TextModel(config)
```

**Batch Processing**:
```bash
# Process multiple files at once
file-organizer organize ~/Downloads --batch-size 10
```

**Disable Features**:
```yaml
# Disable expensive features
para:
  use_smart_suggestions: false

file_formats:
  analyze_archive_contents: false
  cad_metadata_extraction: false
```

### High Memory Usage

**Symptom**: Memory usage > 4 GB.

**Causes**:
1. Large files loaded into memory
2. AI models too large
3. Many files processed at once

**Solutions**:

**Use Smaller Models**:
```python
# Use 3B instead of 7B model
config = ModelConfig(name="qwen2.5:3b-instruct-q4_K_M")
```

**Process in Batches**:
```python
# Process files in smaller batches
organizer.organize(
    input_dir,
    batch_size=5  # Process 5 at a time
)
```

**Set Memory Limits**:
```yaml
system:
  max_memory_mb: 2000  # Limit to 2 GB
  chunk_size_mb: 10    # Process large files in 10 MB chunks
```

### Database Performance

**Symptom**: Database queries slow.

**Causes**:
1. Large history database
2. Missing indexes
3. No cleanup

**Solutions**:

**Clean Old History**:
```bash
# Remove history older than 90 days
file-organizer history clean --older-than 90

# Optimize database
file-organizer history optimize
```

**Compact Database**:
```bash
sqlite3 ~/.config/file-organizer/history.db "VACUUM;"
```

---

## Integration Issues

### GitHub Sync Failing

**Symptom**: Cannot sync with GitHub issues.

**Causes**:
1. gh CLI not authenticated
2. Wrong repository
3. Network issues

**Solutions**:

**Authenticate**:
```bash
gh auth login
gh auth status
```

**Verify Repository**:
```bash
gh repo view
```

**Test Connection**:
```bash
gh issue list
```

### Configuration Not Loading

**Symptom**: Settings not applied.

**Causes**:
1. Wrong config file location
2. Invalid YAML
3. Permissions issue

**Solutions**:

**Check Config Location**:
```bash
# Should be at:
~/.config/file-organizer/config.yaml

# Or:
file-organizer config path
```

**Validate YAML**:
```bash
# Test YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

**Fix Permissions**:
```bash
chmod 644 ~/.config/file-organizer/config.yaml
```

### CLI Commands Not Found

**Symptom**: "command not found: file-organizer"

**Solutions**:

**Reinstall Package**:
```bash
pip install --force-reinstall file-organizer-v2
```

**Check Installation**:
```bash
pip show file-organizer-v2
which file-organizer
```

**Add to PATH**:
```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$PATH:$HOME/.local/bin"
```

---

## Getting Help

### Log Files

Check logs for detailed error information:
```bash
# View logs
tail -f ~/.config/file-organizer/logs/file-organizer.log

# Enable debug logging
file-organizer --debug organize ~/Downloads
```

### Diagnostic Information

Collect diagnostic info:
```bash
file-organizer diagnose > diagnostic-report.txt
```

Includes:
- Python version
- Dependency versions
- Configuration
- System information
- Recent errors

### Community Support

- **GitHub Issues**: https://github.com/your-org/file-organizer-v2/issues
- **Discussions**: https://github.com/your-org/file-organizer-v2/discussions
- **Documentation**: https://file-organizer-v2.readthedocs.io

### Reporting Bugs

When reporting bugs, include:
1. File Organizer version (`file-organizer --version`)
2. Python version (`python --version`)
3. Operating system
4. Steps to reproduce
5. Error messages
6. Diagnostic report

**Template**:
```markdown
## Bug Report

**Version**: file-organizer-v2 2.0.0
**Python**: 3.12.0
**OS**: macOS 14.0

**Steps to Reproduce**:
1. Run `file-organizer organize ~/Downloads`
2. Select PARA methodology
3. Error occurs

**Error Message**:
```
[Paste error here]
```

**Diagnostic Report**:
[Attach diagnostic-report.txt]
```

---

## Related Documentation

- [Phase 3 Overview](README.md) - Feature overview
- [PARA Methodology](para-methodology.md) - PARA guide
- [Johnny Decimal](johnny-decimal.md) - Johnny Decimal guide
- [File Formats](file-formats.md) - Format support

---

**Last Updated**: 2026-01-24
**Help needed?** Open an issue on GitHub
