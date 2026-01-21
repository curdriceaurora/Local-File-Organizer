# Claude Code PM Integration

This directory contains the [Claude Code PM (CCPM)](https://github.com/automazeio/ccpm) system for managing the File Organizer v2.0 project development.

## What is CCPM?

Claude Code PM is a project management system designed for AI-assisted development that:
- Uses **GitHub Issues** as the database for transparent collaboration
- Enables **parallel agent execution** via Git branches for faster development
- Follows **spec-driven development** with full traceability from PRD to production
- Maintains **persistent context** across all work sessions

## Quick Start

### Available Commands

#### PRD Management
- `/pm:prd-new [name]` - Launch brainstorming for new product requirements
- `/pm:prd-parse [name]` - Convert PRD into technical epic with tasks
- `/pm:prd-list` - List all PRDs

#### Epic Operations
- `/pm:epic-decompose [name]` - Break epic into actionable tasks
- `/pm:epic-sync [name]` - Push epic and tasks to GitHub Issues
- `/pm:epic-oneshot [name]` - Decompose and sync in one command

#### Task Execution
- `/pm:issue-start [#]` - Launch specialized agent for issue
- `/pm:issue-sync [#]` - Push progress updates to GitHub
- `/pm:next` - Get next priority task to work on

#### Workflow
- `/pm:status` - Overall project dashboard
- `/pm:standup` - Daily standup report
- `/pm:blocked` - Show blocked tasks

## Project Structure

```
.claude/
├── CLAUDE.md              # Core project instructions
├── README.md              # This file
├── commands/              # PM command definitions
│   ├── pm/                # Project management commands
│   └── test/              # Testing commands
├── prds/                  # Product Requirements Documents
│   └── file-organizer-v2.md  # Main PRD (created)
├── epics/                 # Epic planning workspace
│   └── [epic-name]/       # Per-epic directories (auto-created)
├── context/               # Project-wide context files
├── agents/                # Specialized agent definitions
├── rules/                 # Standard patterns and rules
├── hooks/                 # Git hooks for automation
└── scripts/               # Utility scripts
```

## Current Project Status

### Phase 1: Complete ✅
- Text processing (9 formats)
- Image processing (6 formats)
- Video processing (5 formats, basic)
- 100% quality on tested files
- ~4,200 lines of production code

### GitHub Issues Created
- **#1**: [EPIC] Phase 2 - Enhanced UX
- **#2**: [EPIC] Phase 3 - Feature Expansion
- **#3**: [EPIC] Phase 4 - Intelligence & Learning
- **#4**: [EPIC] Phase 5 - Architecture & Performance
- **#5**: [EPIC] Phase 6 - Web Interface
- **#6**: [EPIC] Testing & Quality Assurance
- **#7**: [EPIC] Documentation & User Guides
- **#8**: [EPIC] Performance Optimization (Critical)

### PRD Status
- **file-organizer-v2**: In Progress (Phase 1 complete, Phase 2 planning)

## Workflow Example

### 1. Start with existing PRD
The main PRD is already created at `.claude/prds/file-organizer-v2.md`

### 2. Parse PRD into epics (if needed)
```
/pm:prd-parse file-organizer-v2
```

### 3. Decompose epic into tasks
```
/pm:epic-decompose phase-2-enhanced-ux
```

### 4. Sync to GitHub
```
/pm:epic-sync phase-2-enhanced-ux
```

### 5. Start working on a task
```
/pm:issue-start 1
```

### 6. Check next task
```
/pm:next
```

## Integration with File Organizer v2.0

### Repository Configuration
- **GitHub Repo**: curdriceaurora/Local-File-Organizer
- **Issues Enabled**: ✅ Yes
- **Branches**: main (protected)
- **CI/CD**: Planned for Phase 2

### Development Workflow
1. **Planning**: Use CCPM to create and manage epics
2. **Execution**: Create branches for parallel development
3. **Testing**: Run test suite before merging
4. **Documentation**: Update docs alongside code
5. **Release**: Follow semantic versioning

### Key Files to Reference
- `file_organizer_v2/BUSINESS_REQUIREMENTS_DOCUMENT.md` - Complete BRD (20,000+ words)
- `file_organizer_v2/PROJECT_STATUS.md` - Current status and metrics
- `file_organizer_v2/README.md` - User-facing documentation

## Best Practices

### For This Project

1. **Always reference the BRD** when planning features
2. **Update PROJECT_STATUS.md** after completing milestones
3. **Test with sample files** before claiming completion
4. **Follow the roadmap** (Phases 2-6) for feature prioritization
5. **Document performance** metrics for optimization tracking

### CCPM General Practices

1. **One branch per epic** - Not per issue
2. **Commit frequently** - Small, focused commits
3. **Update progress** - Keep GitHub issues current
4. **Coordinate on shared files** - Avoid conflicts
5. **Pull before push** - Stay synchronized

## Performance Considerations

### Known Issues to Track
- **Critical**: Image processing speed (240s → 30s target)
- Vision model loading reliability
- Memory usage optimization

### Testing Requirements
- All code must have tests (#6)
- Performance benchmarks for optimizations
- Integration tests for end-to-end workflows

## Documentation

### Project Documentation (Already Exists)
- Business Requirements Document (BRD)
- Project Status Report
- Week-by-week progress reports
- SOTA research analysis

### CCPM Documentation
- [Main README](https://github.com/automazeio/ccpm/blob/main/README.md)
- [Commands Reference](https://github.com/automazeio/ccpm/blob/main/COMMANDS.md)
- [Agents Documentation](https://github.com/automazeio/ccpm/blob/main/AGENTS.md)

## Support

For CCPM-specific questions:
- Visit: https://github.com/automazeio/ccpm
- Follow: [@aroussi](https://x.com/aroussi)

For File Organizer v2.0 questions:
- GitHub Issues: https://github.com/curdriceaurora/Local-File-Organizer/issues
- Documentation: See `file_organizer_v2/` directory

---

**Last Updated**: 2026-01-20
**CCPM Version**: Latest from automazeio/ccpm
**Project Phase**: 1 Complete, 2 Planning
