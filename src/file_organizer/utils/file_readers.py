"""Backward-compatible re-exports from file_organizer.utils.readers.

This module is kept for backward compatibility. New code should import directly
from :mod:`file_organizer.utils.readers` or its sub-modules.

.. deprecated::
    Import from :mod:`file_organizer.utils.readers` instead.
"""

from file_organizer.utils.readers import (  # noqa: F401
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
from file_organizer.utils.readers._base import _check_file_size  # noqa: F401
