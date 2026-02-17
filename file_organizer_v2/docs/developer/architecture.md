# Architecture Guide

## System Design Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Web Browser (UI)                     │
├─────────────────────────────────────────────────────────┤
│                  HTMX + HTML + CSS                      │
├─────────────────────────────────────────────────────────┤
│        FastAPI Web Server (REST API + WebSocket)        │
├─────────────────────────────────────────────────────────┤
│  File Organizer Core Engine (Python)                    │
│  ├── Text Processor                                     │
│  ├── Vision Processor                                   │
│  ├── Pattern Analyzer                                   │
│  ├── Intelligence Services                              │
│  └── Deduplication Services                             │
├─────────────────────────────────────────────────────────┤
│  External Services                                      │
│  ├── Ollama (Local LLMs)                                │
│  ├── PostgreSQL (Data Storage)                          │
│  ├── Redis (Caching)                                    │
│  └── File System (Storage)                              │
└─────────────────────────────────────────────────────────┘
```

## Backend Stack

### FastAPI Web Framework

- **Purpose**: REST API and WebSocket server
- **Location**: `file_organizer/api/`
- **Key Features**:
  - Automatic API documentation (OpenAPI/Swagger)
  - Built-in request validation
  - WebSocket support
  - Dependency injection

### Core File Organizer Engine

- **Purpose**: File organization logic
- **Location**: `file_organizer/core/`
- **Components**:
  - `file_organizer.py` - Main orchestrator
  - Model abstractions (text, vision, audio)
  - Service layer (processors, analyzers)

### Database Layer

- **ORM**: SQLAlchemy
- **Database**: PostgreSQL
- **Migrations**: Alembic
- **Location**: `file_organizer/models/`, `alembic/`

### Caching Layer

- **Provider**: Redis
- **Purpose**: Performance optimization
- **Usage**: API results, processed metadata

## Frontend Stack

### HTMX + HTML + CSS

- **HTMX**: AJAX interactions without JavaScript
- **HTML**: Server-rendered templates
- **CSS**: Responsive design with Bootstrap/Tailwind
- **Location**: `templates/`, `static/`

### Real-Time Communication

- **WebSocket**: Live event streaming
- **Endpoint**: `/api/v1/ws/{client_id}`
- **Events**: File uploads, organization progress, notifications

## Key Components

### AI Models

#### TextModel

- **Model**: Qwen 2.5 3B (via Ollama)
- **Purpose**: Text understanding and generation
- **Input**: File content/metadata
- **Output**: Categories, tags, descriptions

#### VisionModel

- **Model**: Qwen 2.5-VL 7B (via Ollama)
- **Purpose**: Image/video analysis
- **Input**: Images, video frames
- **Output**: OCR text, descriptions, classification

### Services

#### TextProcessor

- Reads text files
- Extracts metadata
- Generates organization suggestions

#### VisionProcessor

- Analyzes images and videos
- Performs OCR
- Detects content type

#### PatternAnalyzer

- Analyzes file naming patterns
- Learns user preferences
- Generates smart suggestions

#### Intelligence Services

- Tracks user preferences
- Learns organization patterns
- Provides personalized recommendations

### Deduplication

- Image hashing (perceptual)
- Document similarity (embeddings)
- Metadata comparison

## Data Flow

### File Organization Workflow

```
1. User uploads file
   ↓
2. File stored temporarily
   ↓
3. Content analysis:
   - Text extraction
   - Vision analysis
   - Metadata extraction
   ↓
4. Pattern matching:
   - Analyze file properties
   - Check user preferences
   - Generate suggestions
   ↓
5. Organization preview:
   - Proposed folder
   - Suggested filename
   - Confidence score
   ↓
6. User confirmation
   ↓
7. File move/copy to destination
   ↓
8. Update metadata and indices
```

### API Request Flow

```
HTTP Request
   ↓
FastAPI Router
   ↓
Authentication (API Key/JWT)
   ↓
Request Validation
   ↓
Business Logic (Service Layer)
   ↓
Core Engine (File Organizer)
   ↓
Database/File System Operations
   ↓
HTTP Response
```

## Development Patterns

### Service Layer Pattern

```python
# Router (endpoint)
@router.post("/api/v1/files/organize")
async def organize_files(request: OrganizeRequest):
    service = OrganizationService()
    result = await service.organize(request)
    return result

# Service (business logic)
class OrganizationService:
    def __init__(self):
        self.core = FileOrganizer()

    async def organize(self, request):
        # Business logic
        return result

# Core (file organizer logic)
class FileOrganizer:
    def organize(self, files):
        # Core organization logic
        return result
```

### Dependency Injection

```python
from fastapi import Depends

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/api/v1/files")
async def list_files(db: Session = Depends(get_db)):
    return db.query(File).all()
```

## Extension Points

### Plugin System

Extend functionality via hooks:

```python
from file_organizer.plugins import register_hook

@register_hook("on_file_uploaded")
async def my_plugin(file: UploadedFile):
    # Custom logic
    pass
```

### Custom Models

Implement custom AI models:

```python
from file_organizer.models.base import BaseModel

class CustomModel(BaseModel):
    def generate(self, prompt: str) -> str:
        # Custom implementation
        pass
```

## See Also

- [Plugin Development](plugin-development.md)
- [Contributing Guide](contributing.md)
