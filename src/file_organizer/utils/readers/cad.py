"""Readers for CAD formats: DXF, DWG, STEP, IGES."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import ezdxf

    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False

from loguru import logger

from file_organizer.utils.readers._base import FileReadError, _check_file_size


def _process_dxf_doc(doc: Any, file_path: Path, max_layers: int = 20) -> str:
    """Extract metadata from an already-loaded ezdxf document.

    Shared by :func:`read_dxf_file` and :func:`read_dwg_file` so the file is
    opened only once even when a DWG read falls back to the DXF path.

    Args:
        doc: An ezdxf document object returned by ``ezdxf.readfile()``.
        file_path: Original file path (used only for the log message).
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
        except Exception:
            logger.opt(exception=True).debug(
                "Failed to read DXF $TITLE header for {}", file_path.name
            )

        try:
            author = doc.header.get("$AUTHOR", "")
            if not author:
                author = doc.header.get("$LASTSAVEDBY", "Unknown")
            metadata_parts.append(f"Author: {author}")
        except Exception:
            logger.opt(exception=True).debug(
                "Failed to read DXF author metadata for {}", file_path.name
            )

    # DXF version
    metadata_parts.append(f"DXF Version: {doc.dxfversion}")

    # Layer information
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

    # Entity statistics
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

    # Blocks
    if doc.blocks:
        block_count = len([b for b in doc.blocks if not b.name.startswith("*")])
        if block_count > 0:
            metadata_parts.append("\n=== Blocks ===")
            metadata_parts.append(f"Block definitions: {block_count}")

    text = "\n".join(metadata_parts)
    logger.debug(f"Extracted {len(text)} characters from DXF file {file_path.name}")
    return text


def read_dxf_file(file_path: str | Path, max_layers: int = 20) -> str:
    """Read metadata and content from a DXF CAD file.

    Args:
        file_path: Path to DXF file
        max_layers: Maximum number of layers to list

    Returns:
        Extracted metadata and layer information

    Raises:
        FileReadError: If file cannot be read
        ImportError: If ezdxf is not installed
    """
    if not EZDXF_AVAILABLE:
        raise ImportError("ezdxf is not installed. Install with: pip install ezdxf")

    file_path = Path(file_path)
    _check_file_size(file_path)
    try:
        doc = ezdxf.readfile(file_path)
        return _process_dxf_doc(doc, file_path, max_layers)
    except Exception as e:
        raise FileReadError(f"Failed to read DXF file {file_path}: {e}") from e


def read_dwg_file(file_path: str | Path) -> str:
    """Read metadata from a DWG CAD file.

    Note: DWG is a proprietary format. This function attempts to read it using ezdxf,
    which has limited DWG support. For full DWG support, consider using ODA File Converter
    to convert DWG to DXF first.

    Args:
        file_path: Path to DWG file

    Returns:
        Extracted metadata or basic file information

    Raises:
        FileReadError: If file cannot be read
        ImportError: If ezdxf is not installed
    """
    if not EZDXF_AVAILABLE:
        raise ImportError("ezdxf is not installed. Install with: pip install ezdxf")

    file_path = Path(file_path)
    _check_file_size(file_path)
    try:
        # Try to read with ezdxf (limited support).
        # Capture the returned document and pass it through to avoid re-opening the file.
        doc = ezdxf.readfile(file_path)
        return _process_dxf_doc(doc, file_path)

    except Exception as e:
        # If ezdxf can't read it, provide basic file info
        logger.warning(f"Could not parse DWG file with ezdxf: {e}")

        if not file_path.exists():
            raise FileReadError(f"File not found: {file_path}") from e

        metadata_parts = [
            "=== DWG File Information ===",
            f"File: {file_path.name}",
            f"Size: {file_path.stat().st_size / 1024:.2f} KB",
            "",
            "Note: Full DWG parsing requires additional tools.",
            "Consider using ODA File Converter to convert DWG to DXF for better support.",
        ]

        return "\n".join(metadata_parts)


def read_step_file(file_path: str | Path, max_lines: int = 100) -> str:
    """Read metadata from a STEP (.step, .stp) CAD file.

    STEP files are ISO 10303 standard format for 3D CAD data exchange.
    This function extracts basic header information.

    Args:
        file_path: Path to STEP file
        max_lines: Maximum lines to read from header

    Returns:
        Extracted header information

    Raises:
        FileReadError: If file cannot be read
    """
    file_path = Path(file_path)
    _check_file_size(file_path)
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            content = f.read(10000)  # Read first 10KB

        metadata_parts = ["=== STEP File Information ==="]
        metadata_parts.append(f"File: {file_path.name}")
        metadata_parts.append(f"Size: {file_path.stat().st_size / 1024:.2f} KB")

        # Extract header section (between HEADER; and ENDSEC;)
        if "HEADER;" in content and "ENDSEC;" in content:
            header_start = content.find("HEADER;")
            header_end = content.find("ENDSEC;", header_start)
            header = content[header_start:header_end]

            metadata_parts.append("\n=== Header Information ===")

            # Extract file description
            if "FILE_DESCRIPTION" in header:
                desc_start = header.find("FILE_DESCRIPTION")
                desc_end = header.find(");", desc_start)
                if desc_end > desc_start:
                    desc = header[desc_start : desc_end + 2]
                    metadata_parts.append(desc.strip())

            # Extract file name
            if "FILE_NAME" in header:
                name_start = header.find("FILE_NAME")
                name_end = header.find(");", name_start)
                if name_end > name_start:
                    name_info = header[name_start : name_end + 2]
                    metadata_parts.append(name_info.strip())

            # Extract schema
            if "FILE_SCHEMA" in header:
                schema_start = header.find("FILE_SCHEMA")
                schema_end = header.find(");", schema_start)
                if schema_end > schema_start:
                    schema = header[schema_start : schema_end + 2]
                    metadata_parts.append(schema.strip())

        # Count entities in DATA section
        if "DATA;" in content:
            # Count lines starting with # (entities)
            entity_count = content.count("\n#")
            metadata_parts.append(f"\nApproximate entity count: {entity_count}")

        text = "\n".join(metadata_parts)
        logger.debug(f"Extracted {len(text)} characters from STEP file {file_path.name}")
        return text

    except Exception as e:
        raise FileReadError(f"Failed to read STEP file {file_path}: {e}") from e


def read_iges_file(file_path: str | Path, max_lines: int = 50) -> str:
    """Read metadata from an IGES (.iges, .igs) CAD file.

    IGES (Initial Graphics Exchange Specification) is a vendor-neutral file format
    for 3D CAD data exchange.

    Args:
        file_path: Path to IGES file
        max_lines: Maximum lines to read from header

    Returns:
        Extracted header information

    Raises:
        FileReadError: If file cannot be read
    """
    file_path = Path(file_path)
    _check_file_size(file_path)
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            lines = [f.readline() for _ in range(max_lines)]

        metadata_parts = ["=== IGES File Information ==="]
        metadata_parts.append(f"File: {file_path.name}")
        metadata_parts.append(f"Size: {file_path.stat().st_size / 1024:.2f} KB")

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

        # Display start section (usually contains file description)
        if start_section:
            metadata_parts.append("\n=== Start Section ===")
            metadata_parts.extend(start_section[:10])  # First 10 lines

        # Display global section (contains parameters)
        if global_section:
            metadata_parts.append("\n=== Global Parameters ===")
            # Join and split by commas to get parameters
            global_params = "".join(global_section)
            params = global_params.split(",")[:5]  # First 5 parameters

            # Parameter meanings (typical order)
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

        # Count entities
        entity_count = sum(1 for line in lines if len(line) >= 73 and line[72] == "D")
        if entity_count > 0:
            metadata_parts.append(f"\nDirectory entries found: {entity_count}")

        text = "\n".join(metadata_parts)
        logger.debug(f"Extracted {len(text)} characters from IGES file {file_path.name}")
        return text

    except Exception as e:
        raise FileReadError(f"Failed to read IGES file {file_path}: {e}") from e


def read_cad_file(file_path: str | Path, **kwargs: object) -> str:
    """Read content from any CAD file format.

    Auto-detects CAD file type and uses appropriate reader.

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
        return reader(file_path, **kwargs)  # type: ignore[no-any-return,operator]
    else:
        raise FileReadError(f"Unsupported CAD file format: {ext}")
