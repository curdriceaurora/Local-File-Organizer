# Developer Guide

Extend and customize File Organizer for your needs.

## Quick Start

### Clone Repository

```bash
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd file_organizer_v2
```

### Install Development Environment

```bash
pip install -e ".[dev]"
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

### Start Development Server

```bash
python -m uvicorn main:app --reload
```

## Main Sections

### Understanding the System

- [Architecture Guide](architecture.md) - System design and components
- Understanding API structure
- Database schema overview

### Extending File Organizer

- [Plugin Development](plugin-development.md) - Create custom plugins
- Creating custom methodologies
- Adding new file type handlers

### Integration

- [API Clients](api-clients.md) - Client libraries and examples
- Webhook integration
- Third-party service integration

### Best Practices

- Code style and standards
- Pull request process
- Unit and integration testing

## Architecture

```
File Organizer v2.0
├── Web Interface (FastAPI)
│   ├── REST API
│   ├── WebSocket
│   └── Static Files
│
├── Core Engine
│   ├── File Processors
│   │   ├── Text Processor
│   │   ├── Vision Processor
│   │   └── Audio Processor
│   │
│   ├── Methodologies
│   │   ├── PARA
│   │   ├── Johnny Decimal
│   │   └── Custom
│   │
│   └── Services
│       ├── Analytics
│       ├── Deduplication
│       ├── Search
│       └── Intelligence
│
├── Storage
│   ├── PostgreSQL Database
│   ├── File System
│   └── Redis Cache
│
└── AI Inference
    └── Ollama (Local LLMs)
```

## Key Files

**Web Server**

- `web_server/main.py` - FastAPI application
- `web_server/routes/` - API endpoints
- `web_server/models.py` - Pydantic models

**Core Engine**

- `file_organizer/core/` - Main orchestrator
- `file_organizer/services/` - Business logic
- `file_organizer/models/` - AI model interfaces

**Database**

- `file_organizer/db/` - Database models
- `alembic/` - Database migrations

## Development Tasks

### Create Custom Methodology

```python
from file_organizer.methodologies import BaseMethodology

class CustomMethod(BaseMethodology):
    name = "custom"

    def categorize(self, file_path):
        # Your logic here
        return category
```

See [Plugin Development](plugin-development.md).

### Create API Endpoint

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")

@router.post("/custom-endpoint")
async def custom_endpoint(data: MyModel):
    return {"result": "success"}
```

### Add File Type Support

1. Create reader in `utils/file_readers.py`
1. Register in processor
1. Add tests
1. Update documentation

## Testing

### Run Tests

```bash
pytest                      # All tests
pytest tests/unit/          # Unit tests only
pytest tests/ -v            # Verbose output
pytest tests/ --cov         # With coverage
```

### Write Tests

```python
import pytest

def test_my_feature():
    # Arrange
    data = setup_test_data()

    # Act
    result = my_function(data)

    # Assert
    assert result == expected_value
```

## Code Standards

### Python Style

- Follow PEP 8
- Use type hints
- Max line length 88 (Black)
- Sort imports (isort)

### Naming

- Classes: `PascalCase`
- Functions: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`

### Documentation

- Google-style docstrings
- Document public APIs
- Include usage examples

## Contributing

### Process

1. Fork repository
1. Create feature branch: `git checkout -b feature/my-feature`
1. Make changes with tests
1. Run quality checks
1. Commit with clear message
1. Push and create PR

### Quality Checks

```bash
ruff check .              # Linting
black .                   # Formatting
mypy .                    # Type checking
pytest                    # Tests
```

## Resources

### Documentation

- This Developer Guide
- [API Reference](../api/index.md)
- Code comments and docstrings

### Community

- [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues)
- [GitHub Discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)
- [GitHub Releases](https://github.com/curdriceaurora/Local-File-Organizer/releases)

### Related Projects

- [Ollama](https://ollama.ai) - Local LLM inference
- [FastAPI](https://fastapi.tiangolo.com) - Web framework
- [SQLAlchemy](https://www.sqlalchemy.org) - Database ORM

## Getting Help

### Documentation

- Read the architecture guide
- Check API documentation
- Review existing code

### Support

- GitHub Issues for bugs
- GitHub Discussions for questions
- Code comments in relevant files

## Next Steps

- [Architecture Guide](architecture.md)
- [Plugin Development](plugin-development.md)
- [API Reference](../api/index.md)
