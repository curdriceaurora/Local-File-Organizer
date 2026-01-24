# Bash Permissions Configuration

## Auto-Approval Setup

To enable auto-approval for all bash commands in this project, add the following to `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash"
    ]
  }
}
```

**Important**: Use `"Bash"` without parentheses to allow all bash commands. Do NOT use `"Bash(*)"` or `"Bash(*)"`- these formats are invalid.

## Permission Formats

### Allow All Commands (Recommended for Development)
```json
"Bash"
```

### Allow Specific Commands Only
```json
"Bash(git:*)"        // All git commands
"Bash(npm:*)"        // All npm commands
"Bash(pytest:*)"     // All pytest commands
```

### Allow Specific Command Patterns
```json
"Bash(git commit *)"         // Only git commit
"Bash(npm install *)"        // Only npm install
```

## Common Issues

### Issue: Still Getting Prompts for Bash Commands

**Cause**: The `"Bash"` entry is missing from the allow list, or it's in the wrong format.

**Fix**:
1. Open `.claude/settings.local.json`
2. Add `"Bash"` as the first item in the `"allow"` array
3. Save the file
4. Restart Claude Code session (type `/reload` or start new conversation)

### Issue: Multi-line Bash Commands Not Working

**Cause**: Multi-line bash commands (with heredocs, pipes, etc.) create special encoded entries that don't match specific patterns.

**Fix**: Use blanket approval with `"Bash"` instead of trying to enumerate all possible patterns.

## Current Configuration

This project is configured with blanket bash approval in `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash"  // ← This allows ALL bash commands
      // ... other specific permissions retained for reference
    ]
  }
}
```

## Security Note

Blanket bash approval (`"Bash"`) means Claude Code can execute any bash command without asking. This is appropriate for:
- Development environments
- Personal projects
- Trusted repositories

For production or shared environments, consider using more restrictive patterns.

## Last Updated
2026-01-24 - Added blanket Bash approval to resolve multi-line command approval issues
