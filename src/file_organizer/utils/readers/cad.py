# pyre-ignore-all-errors
"""Readers for CAD formats: DXF, DWG, STEP, IGES.

Each public ``read_X_file`` function accepts either a path (legacy) or an
open binary file-like via the ``fileobj`` keyword. The file-like path is
the SafeDir-friendly entry point: callers open via
``SafeDir.open_for_reader``, wrap in ``os.fdopen(fd, "rb")``, and hand to
the reader.

Library-specific notes:

- ``ezdxf.readfile`` takes a path; ``ezdxf.read`` takes a **text** stream.
  The fileobj branch wraps the binary fileobj in ``io.TextIOWrapper``
  before handing it to ``ezdxf.read``.
- STEP and IGES are plain ASCII text formats; the fileobj branch wraps
  the binary fileobj in ``io.TextIOWrapper`` and reads as text.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, BinaryIO

try:
    import ezdxf

    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False

from loguru import logger

from file_organizer.utils.readers._base import FileReadError, _check_fd_size, _check_file_size


def _process_dxf_doc(doc: Any, label: str, max_layers: int = 20) -> str:
    """Extract metadata from an already-loaded ezdxf document.

    Shared by :func:`read_dxf_file` and :func:`read_dwg_file` so the file is
    opened only once even when a DWG read falls back to the DXF path.

    Args:
        doc: An ezdxf document object returned by ``ezdxf.readfile()`` or
            ``ezdxf.read()``.
        label: Filename (or ``<fileobj>``) used in the log message.
        max_layers: Maximum number of layers to list.

    Returns:
        Extracted metadata and layer information as a string.
    """
    metadata_parts: list[str] = []

    # Header variables
    if hasattr(doc, "header"):
        metadata_parts.append("=== DXF Document Metadata ===")

        try:
            title = doc.header.get("$TITLE", "Untitled")
            if title:
                metadata_parts.append(f"Title: {title}")
        except Exception:  # Intentional catch-all: ezdxf header raises library-specific errors
            logger.opt(exception=True).debug("Failed to read DXF $TITLE header for {}", label)

        try:
            author = doc.header.get("$AUTHOR", "")
            if not author:
                author = doc.header.get("$LASTSAVEDBY", "Unknown")
            metadata_parts.append(f"Author: {author}")
        except Exception:  # Intentional catch-all: ezdxf header raises library-specific errors
            logger.opt(exception=True).debug("Failed to read DXF author metadata for {}", label)

    metadata_parts.append(f"DXF Version: {doc.dxfversion}")

    if doc.layers:
        layer_count = len(doc.layers)
        metadata_parts.append(f"\n=== Layers ({layer_count} total) ===")

        for idx, layer in enumerate(doc.layers):
            if idx >= max_layers:
                metadata_parts.append(f"... and {layer_count - max_layers} more layers")
                break

            layer_info = f"Layer: {layer.dxf.name}"
            if hasattr(layer.dxf, "color"):
                layer_info += f" (Color: {layer.dxf.color})"
            metadata_parts.append(layer_info)

    modelspace = doc.modelspace()
    entity_types: dict[str, int] = {}

    for entity in modelspace:
        entity_type = entity.dxftype()
        entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

    if entity_types:
        metadata_parts.append("\n=== Entities ===")
        metadata_parts.append(f"Total entities: {sum(entity_types.values())}")

        for entity_type, count in sorted(entity_types.items()):
            metadata_parts.append(f"  {entity_type}: {count}")

    if doc.blocks:
        block_count = len([b for b in doc.blocks if not b.name.startswith("*")])
        if block_count > 0:
            metadata_parts.append("\n=== Blocks ===")
            metadata_parts.append(f"Block definitions: {block_count}")

    text = "\n".join(metadata_parts)
    logger.debug(f"Extracted {len(text)} characters from DXF file {label}")
    return text


def _read_dxf_from_fileobj(fileobj: BinaryIO) -> Any:
    """Hand a binary fileobj to ``ezdxf.read`` via a text wrapper.

    ``ezdxf.read`` takes a ``TextIO``; SafeDir hands us a binary fd. The
    ``surrogateescape`` errors handler matches ``ezdxf.readfile``'s default
    so non-UTF-8 byte sequences in headers round-trip cleanly.

    The wrapper is ``detach()``'d on every exit path — including
    exceptions — so the caller's underlying binary stream survives the
    wrapper's garbage collection (``TextIOWrapper`` otherwise closes
    its source on ``__del__``). This both preserves the caller-owned
    ``fileobj=`` contract and lets the DWG fallback path below still
    ``os.fstat`` the same fd after a parse failure.
    """
    text_stream = io.TextIOWrapper(fileobj, encoding="utf-8", errors="surrogateescape")
    try:
        return ezdxf.read(text_stream)  # type: ignore[attr-defined]  # ezdxf stubs incomplete
    finally:
        text_stream.detach()


def read_dxf_file(
    file_path: str | Path | None = None,
    max_layers: int = 20,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read metadata and content from a DXF CAD file.

    Args:
        file_path: Path to DXF file (legacy entry point).
        max_layers: Maximum number of layers to list
        fileobj: Open binary file-like (SafeDir-friendly entry point). When
            given, ``file_path`` is used only for the log label.

    Returns:
        Extracted metadata and layer information

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ImportError: If ezdxf is not installed
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    if fileobj is None and file_path is None:
        raise ValueError("read_dxf_file requires file_path or fileobj")
    if not EZDXF_AVAILABLE:
        raise ImportError("ezdxf is not installed. Install with: pip install ezdxf")

    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        _check_fd_size(fileobj)
        try:
            doc = _read_dxf_from_fileobj(fileobj)
            return _process_dxf_doc(doc, label, max_layers)
        except Exception as e:  # Intentional catch-all: ezdxf raises library-specific errors
            raise FileReadError(f"Failed to read DXF file {label}: {e}") from e
    assert file_path is not None  # narrowed above
    path = Path(file_path)
    _check_file_size(path)
    try:
        doc = ezdxf.readfile(path)  # type: ignore[attr-defined]  # ezdxf stubs incomplete
        return _process_dxf_doc(doc, path.name, max_layers)
    except Exception as e:  # Intentional catch-all: ezdxf raises library-specific errors
        raise FileReadError(f"Failed to read DXF file {path}: {e}") from e


def read_dwg_file(
    file_path: str | Path | None = None,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read metadata from a DWG CAD file.

    Note: DWG is a proprietary format. This function attempts to read it
    using ezdxf, which has limited DWG support. For full DWG support,
    consider using ODA File Converter to convert DWG to DXF first.

    Args:
        file_path: Path to DWG file (legacy entry point).
        fileobj: Open binary file-like (SafeDir-friendly entry point). When
            given, ``file_path`` is used only for the log label and the
            file-info fallback message; the fallback that displays
            ``Size: ... KB`` uses ``os.fstat`` on the fd.

    Returns:
        Extracted metadata or basic file information

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ImportError: If ezdxf is not installed
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    if fileobj is None and file_path is None:
        raise ValueError("read_dwg_file requires file_path or fileobj")
    if not EZDXF_AVAILABLE:
        raise ImportError("ezdxf is not installed. Install with: pip install ezdxf")

    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        _check_fd_size(fileobj)
        try:
            doc = _read_dxf_from_fileobj(fileobj)
            return _process_dxf_doc(doc, label)
        except Exception as e:  # Intentional catch-all: ezdxf raises library-specific errors
            logger.warning(f"Could not parse DWG file with ezdxf: {e}")
            # Path-based fallback inspected the file with ``file_path.stat()``;
            # for the fileobj branch we use the fd size, which avoids a
            # second filesystem call that could race against SafeDir's
            # symlink rejection.
            try:
                size_bytes = os.fstat(fileobj.fileno()).st_size
                size_kb = size_bytes / 1024
            except (OSError, AttributeError, ValueError):
                size_kb = -1.0

            metadata_parts = [
                "=== DWG File Information ===",
                f"File: {label}",
            ]
            if size_kb >= 0:
                metadata_parts.append(f"Size: {size_kb:.2f} KB")
            metadata_parts.extend(
                [
                    "",
                    "Note: Full DWG parsing requires additional tools.",
                    "Consider using ODA File Converter to convert DWG to DXF for better support.",
                ]
            )
            return "\n".join(metadata_parts)

    assert file_path is not None  # narrowed above
    path = Path(file_path)
    _check_file_size(path)
    try:
        doc = ezdxf.readfile(path)  # type: ignore[attr-defined]  # ezdxf stubs incomplete
        return _process_dxf_doc(doc, path.name)
    except Exception as e:  # Intentional catch-all: ezdxf raises library-specific errors
        logger.warning(f"Could not parse DWG file with ezdxf: {e}")

        if not path.exists():
            raise FileReadError(f"File not found: {path}") from e

        metadata_parts = [
            "=== DWG File Information ===",
            f"File: {path.name}",
            f"Size: {path.stat().st_size / 1024:.2f} KB",
            "",
            "Note: Full DWG parsing requires additional tools.",
            "Consider using ODA File Converter to convert DWG to DXF for better support.",
        ]

        return "\n".join(metadata_parts)


def _parse_step_text(content: str, label: str, size_kb: float) -> str:
    """Extract STEP metadata from the file content.

    Args:
        content: Raw text read from the STEP file (first 10 KB).
        label: Filename used in the log message.
        size_kb: File size in kilobytes, or -1 if unavailable.
    """
    metadata_parts = ["=== STEP File Information ===", f"File: {label}"]
    if size_kb >= 0:
        metadata_parts.append(f"Size: {size_kb:.2f} KB")

    # Extract header section (between HEADER; and ENDSEC;)
    if "HEADER;" in content and "ENDSEC;" in content:
        header_start = content.find("HEADER;")
        header_end = content.find("ENDSEC;", header_start)
        header = content[header_start:header_end]

        metadata_parts.append("\n=== Header Information ===")

        if "FILE_DESCRIPTION" in header:
            desc_start = header.find("FILE_DESCRIPTION")
            desc_end = header.find(");", desc_start)
            if desc_end > desc_start:
                desc = header[desc_start : desc_end + 2]
                metadata_parts.append(desc.strip())

        if "FILE_NAME" in header:
            name_start = header.find("FILE_NAME")
            name_end = header.find(");", name_start)
            if name_end > name_start:
                name_info = header[name_start : name_end + 2]
                metadata_parts.append(name_info.strip())

        if "FILE_SCHEMA" in header:
            schema_start = header.find("FILE_SCHEMA")
            schema_end = header.find(");", schema_start)
            if schema_end > schema_start:
                schema = header[schema_start : schema_end + 2]
                metadata_parts.append(schema.strip())

    if "DATA;" in content:
        entity_count = content.count("\n#")
        metadata_parts.append(f"\nApproximate entity count: {entity_count}")

    text = "\n".join(metadata_parts)
    logger.debug(f"Extracted {len(text)} characters from STEP file {label}")
    return text


def read_step_file(
    file_path: str | Path | None = None,
    max_lines: int = 100,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read metadata from a STEP (.step, .stp) CAD file.

    STEP files are ISO 10303 standard format for 3D CAD data exchange.
    This function extracts basic header information from the first 10 KB of the
    file (matching the legacy path reader).

    Args:
        file_path: Path to STEP file (legacy entry point).
        max_lines: Accepted for backward-compatible call signatures but not
            used for truncation in this slice; the read is bounded to 10 KB.
            (A ``max_lines`` / byte-budget cap is a WP-3.1 concern, #351.)
        fileobj: Open binary file-like (SafeDir-friendly entry point).
            STEP is plain ASCII; the binary stream is decoded UTF-8 with
            errors ignored, matching the legacy path-branch behavior.

    Returns:
        Extracted header information

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    if fileobj is None and file_path is None:
        raise ValueError("read_step_file requires file_path or fileobj")

    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        _check_fd_size(fileobj)
        try:
            text_stream = io.TextIOWrapper(fileobj, encoding="utf-8", errors="ignore")
            try:
                # WP-2.1: bounded in-memory read (first 10 KB), matching the
                # legacy path reader. (A byte-budgeted readline cap for
                # adversarial single-line files is a WP-3.1 concern, #351.)
                content = text_stream.read(10000)
            finally:
                text_stream.detach()
            try:
                size_kb = os.fstat(fileobj.fileno()).st_size / 1024
            except (OSError, AttributeError, ValueError):
                size_kb = -1.0
            return _parse_step_text(content, label, size_kb)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            raise FileReadError(f"Failed to read STEP file {label}: {e}") from e

    assert file_path is not None  # narrowed above
    path = Path(file_path)
    _check_file_size(path)
    try:
        with path.open(  # noqa: safedir-required  # reader utility — legacy path-branch; SafeDir-aware callers pass fileobj=
            encoding="utf-8", errors="ignore"
        ) as f:  # safedir: ok — legacy path-branch; SafeDir-aware callers pass fileobj=
            content = f.read(10000)  # first 10 KB, matches legacy behavior
        size_kb = path.stat().st_size / 1024
        return _parse_step_text(content, path.name, size_kb)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise FileReadError(f"Failed to read STEP file {path}: {e}") from e


def _parse_iges_lines(lines: list[str], label: str, size_kb: float) -> str:
    """Extract IGES metadata from the first N lines of the file."""
    metadata_parts = ["=== IGES File Information ===", f"File: {label}"]
    if size_kb >= 0:
        metadata_parts.append(f"Size: {size_kb:.2f} KB")

    # IGES files have structured sections marked in column 73
    # S = Start, G = Global, D = Directory Entry, P = Parameter Data, T = Terminate

    start_section = []
    global_section = []

    for line in lines:
        if len(line) >= 73:
            section_type = line[72]
            content = line[:72].strip()

            if section_type == "S" and content:
                start_section.append(content)
            elif section_type == "G" and content:
                global_section.append(content)

    if start_section:
        metadata_parts.append("\n=== Start Section ===")
        metadata_parts.extend(start_section[:10])

    if global_section:
        metadata_parts.append("\n=== Global Parameters ===")
        global_params = "".join(global_section)
        params = global_params.split(",")[:5]

        param_names = [
            "Parameter delimiter",
            "Record delimiter",
            "Product ID from sender",
            "File name",
            "Native system ID",
        ]

        for name, value in zip(param_names, params, strict=False):
            if value.strip():
                metadata_parts.append(f"{name}: {value.strip()}")

    entity_count = sum(1 for line in lines if len(line) >= 73 and line[72] == "D")
    if entity_count > 0:
        metadata_parts.append(f"\nDirectory entries found: {entity_count}")

    text = "\n".join(metadata_parts)
    logger.debug(f"Extracted {len(text)} characters from IGES file {label}")
    return text


def read_iges_file(
    file_path: str | Path | None = None,
    max_lines: int = 50,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read metadata from an IGES (.iges, .igs) CAD file.

    IGES (Initial Graphics Exchange Specification) is a vendor-neutral file
    format for 3D CAD data exchange.

    Args:
        file_path: Path to IGES file (legacy entry point).
        max_lines: Maximum lines to read from header
        fileobj: Open binary file-like (SafeDir-friendly entry point). The
            binary stream is decoded UTF-8 line-by-line with errors ignored,
            matching the legacy path-branch behavior.

    Returns:
        Extracted header information

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    if fileobj is None and file_path is None:
        raise ValueError("read_iges_file requires file_path or fileobj")

    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        _check_fd_size(fileobj)
        try:
            # ``TextIOWrapper`` closes its source stream on GC; detach the
            # underlying binary fd before the wrapper goes out of scope so
            # the caller-owned ``fileobj`` survives this call.
            text_stream = io.TextIOWrapper(fileobj, encoding="utf-8", errors="ignore")
            try:
                lines = [text_stream.readline() for _ in range(max_lines)]
            finally:
                text_stream.detach()
            try:
                size_kb = os.fstat(fileobj.fileno()).st_size / 1024
            except (OSError, AttributeError, ValueError):
                size_kb = -1.0
            return _parse_iges_lines(lines, label, size_kb)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            raise FileReadError(f"Failed to read IGES file {label}: {e}") from e

    assert file_path is not None  # narrowed above
    path = Path(file_path)
    _check_file_size(path)
    try:
        with path.open(  # noqa: safedir-required  # reader utility — legacy path-branch; SafeDir-aware callers pass fileobj=
            encoding="utf-8", errors="ignore"
        ) as f:  # safedir: ok — legacy path-branch; SafeDir-aware callers pass fileobj=
            lines = [f.readline() for _ in range(max_lines)]
        size_kb = path.stat().st_size / 1024
        return _parse_iges_lines(lines, path.name, size_kb)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise FileReadError(f"Failed to read IGES file {path}: {e}") from e


def read_cad_file(file_path: str | Path, **kwargs: object) -> str:
    """Read content from any CAD file format (path-only convenience dispatcher).

    Auto-detects CAD file type and uses appropriate reader. This is the
    legacy path-based entry point; the SafeDir dispatcher in
    ``utils.readers.read_file_via_safedir`` registers each extension
    directly against the per-format readers so the fileobj branch is
    reached without going through this function.

    Args:
        file_path: Path to CAD file
        **kwargs: Additional arguments passed to specific readers

    Returns:
        Extracted metadata and content

    Raises:
        FileReadError: If file cannot be read
    """
    file_path = Path(file_path)
    ext = file_path.suffix.lower()

    cad_readers = {
        ".dxf": read_dxf_file,
        ".dwg": read_dwg_file,
        ".step": read_step_file,
        ".stp": read_step_file,
        ".iges": read_iges_file,
        ".igs": read_iges_file,
    }

    reader = cad_readers.get(ext)
    if reader:
        return reader(file_path, **kwargs)  # type: ignore[operator,no-any-return,arg-type]  # Union dict value; see pyproject.toml [[tool.mypy.overrides]]
    else:
        raise FileReadError(f"Unsupported CAD file format: {ext}")
