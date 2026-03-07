# Development Guidelines

## 💻 Code Style (Strict)

- **Python Version**: 3.12+ features enabled.
- **Typing**: Strict `mypy` mode. Use `list[str]`, not `List[str]`.
- **Docstrings**: Google Style required on all public functions.
- **Formatting**: Black & Isort enforced.
- **Imports**: No unused imports. Remove build artifacts before committing.

## 🧪 Testing Protocol

**DO NOT run `pytest` directly.**
You must use the logging wrapper to capture artifacts for debugging.

**Correct Usage:**

# Run specific test file (Python, JS, Java, etc.)
./.claude/scripts/test-and-log.sh tests/services/test_text_processor.py

# Run with custom log name (for debugging sessions)
./.claude/scripts/test-and-log.sh tests/my_test.py debug_session_v1.log


- Why?

-- Automatically detects framework (Pytest, Jest, JUnit, etc.)

-- Saves output to tests/logs/ for failure analysis

-- Prevents console clutter

## 🔧 Common Workflows
- Adding a New Model
- Create new class extending BaseModel in models/.
- Implement generate(), generate_stream(), cleanup().
- Update ModelConfig.framework enum.
- Add tests in tests/models/.

## Debugging
- Use logging.basicConfig(level=logging.DEBUG).
- Test models directly using the demo.py script or manual model instantiation.
