# AI Model Configuration

### Supported Models

- `qwen2.5:3b-instruct-q4_K_M` — Default text model (~1.9 GB)
- `qwen2.5vl:7b-q4_K_M` — Default vision model (~6.0 GB)
- `faster-whisper` — Audio transcription (local, multi-language)

### Device Support

```python
from file_organizer.models.base import DeviceType

DeviceType.AUTO    # Automatic detection (recommended)
DeviceType.CPU     # CPU inference (universal)
DeviceType.CUDA    # NVIDIA GPU (fastest)
DeviceType.MPS     # Apple Silicon (fast)
DeviceType.METAL   # Apple Metal (fast)
```

---

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity
### 2. Subagent Strategy to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution
### 3. Self-Improvement Loop
- After ANY correction from the user: update 'tasks/lessons.md' with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project
### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness
### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know
now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it
### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how
## Task Management
1. **Plan First**: Write plan to 'tasks/todo.md' with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review to 'tasks/todo.md'
6. **Capture Lessons**: Update 'tasks/lessons.md' after corrections
## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior deveoper standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## Development Guidelines

### Code Style

- **Black** for formatting (line length: 100)
- **isort** for import sorting
- **Ruff** for linting (strict)
- **mypy** strict mode for type checking

### Naming Conventions

- Files/modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_single_underscore`

### Git Commit Messages

```
<type>(<scope>): <subject>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Pre-Commit Validation (REQUIRED)

```bash
bash .claude/scripts/pre-commit-validation.sh
```

Key patterns to avoid:
1. Dict-style dataclass access → use `hasattr()`
2. Wrong return types → read implementation first
3. Non-existent imports → verify module exists
4. Wrong constructor params → check class definition
5. Build artifacts → add to `.gitignore`

---

