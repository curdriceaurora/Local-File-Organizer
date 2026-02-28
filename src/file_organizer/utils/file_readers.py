"""Backward-compatible re-exports from file_organizer.utils.readers.

This module is kept for backward compatibility. New code should import directly
from :mod:`file_organizer.utils.readers` or its sub-modules.

.. deprecated::
    Import from :mod:`file_organizer.utils.readers` instead.
"""

from file_organizer.utils.readers import (
    MAX_FILE_SIZE_BYTES,
    FileReadError,
    FileTooLargeError,
    read_7z_file,
    read_cad_file,
    read_docx_file,
    read_dwg_file,
    read_dxf_file,
    read_ebook_file,
    read_file,
    read_hdf5_file,
    read_iges_file,
    read_mat_file,
    read_netcdf_file,
    read_pdf_file,
    read_presentation_file,
    read_rar_file,
    read_spreadsheet_file,
    read_step_file,
    read_tar_file,
    read_text_file,
    read_zip_file,
)

# Explicit __all__ so that mypy and other static analysers recognise these
# re-exports as part of this module's public API.
__all__ = [
    "MAX_FILE_SIZE_BYTES",
    "FileReadError",
    "FileTooLargeError",
    # NOTE: _check_file_size is intentionally omitted — it is an internal
    # helper of the ``readers`` sub-package and not part of the public API.
    "read_file",
    "read_text_file",
    "read_docx_file",
    "read_pdf_file",
    "read_spreadsheet_file",
    "read_presentation_file",
    "read_ebook_file",
    "read_zip_file",
    "read_7z_file",
    "read_tar_file",
    "read_rar_file",
    "read_hdf5_file",
    "read_netcdf_file",
    "read_mat_file",
    "read_dxf_file",
    "read_dwg_file",
    "read_step_file",
    "read_iges_file",
    "read_cad_file",
]
