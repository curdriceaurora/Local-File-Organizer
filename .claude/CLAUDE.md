# Claude Code Project Instructions

## Project: File Organizer v2.0

This is an AI-powered local file management system with privacy-first architecture.

## ⚠️ CRITICAL: PM Skills Are Mandatory

**NEVER manually create or update GitHub issues/PRs or CCPM tracking documents.**
**ALWAYS use PM skills for ALL project management operations.**

See: `.claude/rules/pm-skills-mandatory.md` for complete requirements.

### Quick Reference

```bash
# Issue management
/pm:issue-start {number}     # Start working on issue
/pm:issue-sync {number}      # Sync progress to GitHub
/pm:issue-close {number}     # Close completed issue

# Epic management
/pm:epic-decompose {name}    # Break epic into tasks
/pm:epic-sync {name}         # Sync epic to GitHub

# Status views
/pm:issue-status             # View all issues
/pm:status                   # View complete status
```

**Why mandatory?** PM skills maintain CCPM consistency, prevent wrong-repo operations, enforce proper frontmatter, and create audit trails.

## Project Structure

```
Local-File-Organizer/
├── .claude/                 # CCPM project management
│   ├── commands/         # PM commands
│   ├── prds/             # Product requirements
│   ├── epics/            # Epic planning workspace
│   ├── context/          # Project-wide context
│   └── agents/           # Specialized agent definitions
├── file_organizer_v2/    # Main application
│   ├── src/file_organizer/
│   │   ├── models/       # AI model abstractions
│   │   ├── services/     # Business logic
│   │   ├── core/         # Orchestration
│   │   └── utils/        # Utilities
│   ├── scripts/          # Test and utility scripts
│   ├── demo.py           # CLI demo
│   └── pyproject.toml    # Project configuration
└── file_organizer_v2/BUSINESS_REQUIREMENTS_DOCUMENT.md