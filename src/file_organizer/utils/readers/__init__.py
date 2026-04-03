"""File reading utilities for various file types.

This package provides readers for all supported file formats, grouped by type:

- :mod:`.documents` — Plain text, DOCX, PDF, spreadsheets, presentations
- :mod:`.ebook` — EPUB ebooks
- :mod:`.archives` — ZIP, 7Z, TAR, RAR archives
- :mod:`.scientific` — HDF5, NetCDF, MATLAB data files
- :mod:`.cad` — DXF, DWG, STEP, IGES CAD files

The :func:`read_file` dispatcher auto-detects format and routes to the correct reader.

Example::

    from file_organizer.utils.readers import read_file, FileTooLargeError

    text = read_file("report.pdf")
    text = read_file("data.zip")
    text = read_file("model.dxf")
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from file_organizer.utils.readers._base import (
    MAX_FILE_SIZE_BYTES,
    FileReadError,
    FileTooLargeError,
    _check_file_size,
)
from file_organizer.utils.readers.archives import (
    read_7z_file,
    read_rar_file,
    read_tar_file,
    read_zip_file,
)
from file_organizer.utils.readers.cad import (
    read_cad_file,
    read_dwg_file,
    read_dxf_file,
    read_iges_file,
    read_step_file,
)
from file_organizer.utils.readers.documents import (
    read_docx_file,
    read_pdf_file,
    read_presentation_file,
    read_spreadsheet_file,
    read_text_file,
)
from file_organizer.utils.readers.ebook import read_ebook_file
from file_organizer.utils.readers.scientific import (
    read_hdf5_file,
    read_mat_file,
    read_netcdf_file,
)

__all__ = [
    # Exceptions / constants
    "FileReadError",
    "FileTooLargeError",
    "MAX_FILE_SIZE_BYTES",
    # Dispatcher
    "read_file",
    # Document readers
    "read_text_file",
    "read_docx_file",
    "read_pdf_file",
    "read_spreadsheet_file",
    "read_presentation_file",
    # eBook readers
    "read_ebook_file",
    # Archive readers
    "read_zip_file",
    "read_7z_file",
    "read_tar_file",
    "read_rar_file",
    # Scientific readers
    "read_hdf5_file",
    "read_netcdf_file",
    "read_mat_file",
    # CAD readers
    "read_dxf_file",
    "read_dwg_file",
    "read_step_file",
    "read_iges_file",
    "read_cad_file",
]


def read_file(file_path: str | Path, **kwargs: object) -> str | None:
    """Read content from any supported file type.

    Auto-detects file type and uses appropriate reader.

    Args:
        file_path: Path to file
        **kwargs: Additional arguments passed to specific readers

    Returns:
        Extracted text content, or None if unsupported

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If file exceeds size limit
    """
    file_path = Path(file_path)
    _check_file_size(file_path)

    # Check for compound extensions (e.g., .tar.gz)
    name_lower = file_path.name.lower()
    ext = file_path.suffix.lower()

    # Handle compound extensions for archives
    if (
        name_lower.endswith(".tar.gz")
        or name_lower.endswith(".tar.bz2")
        or name_lower.endswith(".tar.xz")
    ):
        compound_ext = "." + ".".join(file_path.name.split(".")[-2:]).lower()
    else:
        compound_ext = ext

    readers = {
        # Document formats
        (".txt", ".md"): read_text_file,
        (".docx",): read_docx_file,  # Note: .doc (old binary format) is NOT supported
        (".pdf",): read_pdf_file,
        (".csv", ".xlsx", ".xls"): read_spreadsheet_file,
        (".ppt", ".pptx"): read_presentation_file,
        (".epub",): read_ebook_file,
        # Archive formats
        (".zip",): read_zip_file,
        (".7z",): read_7z_file,
        (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz"): read_tar_file,
        (".rar",): read_rar_file,
        # Scientific formats
        (".hdf5", ".h5", ".hdf"): read_hdf5_file,
        (".nc", ".nc4", ".netcdf"): read_netcdf_file,
        (".mat",): read_mat_file,
        # CAD formats
        (".dxf", ".dwg", ".step", ".stp", ".iges", ".igs"): read_cad_file,
    }

    # Try compound extension first, then fall back to simple extension
    for check_ext in [compound_ext, ext]:
        for extensions, reader in readers.items():
            if check_ext in extensions:
                try:
                    return reader(file_path, **kwargs)  # type: ignore[no-any-return,operator]
                except Exception as e:  # Intentional catch-all: delegates to many reader impls
                    logger.error(f"Error reading {file_path.name}: {e}")
                    raise

    logger.warning(f"Unsupported file type: {ext}")
    return None
