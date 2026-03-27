# Deferred Features

This document tracks features that have been evaluated but deferred due to architectural constraints, missing dependencies, or strategic considerations.

## Table of Contents

- [GLM-OCR Integration](#glm-ocr-integration)

---

## GLM-OCR Integration

**Issue**: [#853](https://github.com/rahulvijayy/local-file-organizer/issues/853)
**Evaluated**: 2026-03-26
**Decision**: DEFER
**Status**: Backlog

### Overview

[GLM-OCR](https://huggingface.co/THUDM/glm-ocr) is a 0.9B parameter multimodal model ranked #1 on OmniDocBench V1.5 for OCR tasks. The feature proposal aimed to add GLM-OCR as an optional OCR provider for scanned and image-based PDF processing.

### Evaluation Summary

**Model Characteristics**:
- Size: 0.9B parameters (2.65 GB in BF16)
- Performance: #1 on OmniDocBench V1.5 benchmark
- License: Apache 2.0 (code) + MIT (weights)
- Quantization: 13 community quantizations available
- Requirements: `transformers>=5.3.0`

### Critical Blocker: Architectural Mismatch

**Problem**: GLM-OCR requires a persistent HTTP sidecar daemon for all self-hosted backends (vLLM, SGLang, or MLX server). Current provider abstraction is designed for **in-process** model execution.

**Current Architecture**:
- `llama-cpp-python`: In-process inference
- `mlx-lm`: In-process inference
- All providers: Single-process lifecycle, no external daemon management

**GLM-OCR Requirements**:
- Persistent HTTP server process (vLLM/SGLang/MLX)
- Sidecar lifecycle management (start/stop/health checks)
- Inter-process communication
- Port management and conflict resolution

### Hard Constraint: Dependency Conflict

GLM-OCR cannot coexist with vLLM in the same environment:

```
vLLM requirement:      transformers<5
GLM-OCR requirement:   transformers>=5.3.0
Result:                INCOMPATIBLE
```

This prevents using vLLM as the backend server for GLM-OCR in environments where vLLM is also used for other models.

### Non-Blocking Concerns (Resolved)

The following concerns were evaluated and found acceptable:

✅ **Transformers Version**: Lock file already pins `transformers==5.3.0` - no conflict with existing dependencies
✅ **VRAM Requirements**: 2.65 GB (BF16) is manageable; multiple quantizations available
✅ **License**: Apache 2.0 + MIT licenses are compatible with project licensing

### Implementation Complexity

If architectural blockers are resolved, estimated implementation effort:

- **Complexity**: Complex
- **Changes Required**:
  - New provider abstraction layer supporting server-process model
  - Sidecar daemon lifecycle management
  - Health check and recovery mechanisms
  - Port management system
  - `[ocr]` optional dependency group in `pyproject.toml`
- **Estimated Effort**: 3-5 development sessions
- **Testing Scope**: Integration tests, daemon lifecycle tests, error recovery tests

### Revisit Conditions

This feature should be reconsidered if/when:

1. **Server-Process Provider Type Added**: Project implements Ollama-style deployment pattern with sidecar lifecycle management
2. **Dependency Conflict Resolved**: Alternative backend emerges that supports `transformers>=5.3.0`
3. **In-Process GLM-OCR**: Community develops in-process inference backend (unlikely given model architecture)

### Alternative Solutions

For scanned/image-based PDF OCR needs, consider:

- **Tesseract OCR**: Established open-source OCR engine
- **EasyOCR**: Python-based OCR with GPU support
- **PaddleOCR**: High-performance multilingual OCR
- **Cloud OCR APIs**: Google Vision, Azure Vision (requires network)

### References

- **Issue**: [#853 - Add GLM-OCR support for scanned PDFs](https://github.com/rahulvijayy/local-file-organizer/issues/853)
- **Model**: [THUDM/glm-ocr on Hugging Face](https://huggingface.co/THUDM/glm-ocr)
- **Benchmark**: [OmniDocBench V1.5](https://opendatalab.org.cn/OpenDataLab/OmniDocBench)
- **Architecture Docs**: [Provider Abstraction](./architecture-overview.md#core-components)

---

## Document Maintenance

**Last Updated**: 2026-03-26
**Maintainer**: Development Team
**Review Cycle**: Quarterly or when architectural changes occur

When adding new deferred features to this document:

1. Include evaluation date and decision rationale
2. Document blocking constraints clearly
3. Define concrete revisit conditions
4. Suggest alternative solutions where applicable
5. Link to relevant issues and external resources
