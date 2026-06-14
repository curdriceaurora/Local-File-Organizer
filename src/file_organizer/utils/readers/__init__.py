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

import os
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

try:
    from file_organizer.utils.readers.scientific import (
        read_hdf5_file,
        read_mat_file,
        read_netcdf_file,
    )
except (ImportError, OSError):  # pragma: no cover
    from file_organizer.utils.readers._scientific_stub import (  # type: ignore[no-redef]
        read_hdf5_file,
        read_mat_file,
        read_netcdf_file,
    )
from file_organizer.utils.safedir import SafeDir, _validate_name

__all__ = [
    # Exceptions / constants
    "FileReadError",
    "FileTooLargeError",
    "MAX_FILE_SIZE_BYTES",
    # Dispatchers
    "read_file",
    "read_file_via_safedir",
    "read_file_via_safedir_anchored",
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


# Extension → reader registry for the SafeDir dispatchers. Each reader accepts
# a ``fileobj=`` keyword (the SafeDir-friendly entry point). Mirrors the
# ``read_file`` table but maps to the individual fileobj-capable readers.
_SAFEDIR_READERS: dict[tuple[str, ...], object] = {
    (".txt", ".md"): read_text_file,
    (".docx",): read_docx_file,
    (".pdf",): read_pdf_file,
    (".csv", ".xlsx", ".xls"): read_spreadsheet_file,
    (".ppt", ".pptx"): read_presentation_file,
    (".zip",): read_zip_file,
    (".7z",): read_7z_file,
    (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz"): read_tar_file,
    (".rar",): read_rar_file,
    (".epub",): read_ebook_file,
    (".hdf5", ".h5", ".hdf"): read_hdf5_file,
    (".nc", ".nc4", ".netcdf"): read_netcdf_file,
    (".mat",): read_mat_file,
    (".dxf",): read_dxf_file,
    (".dwg",): read_dwg_file,
    (".step", ".stp"): read_step_file,
    (".iges", ".igs"): read_iges_file,
}


def read_file_via_safedir(
    safe_dir: SafeDir,
    name: str,
    **kwargs: object,
) -> str | None:
    """Open *name* under *safe_dir* and dispatch to a reader.

    The SafeDir-friendly entry point: ``safe_dir.open_for_reader(name)`` is
    used to obtain a file descriptor with ``O_NOFOLLOW``, so a symlink
    swapped in between directory enumeration and read is refused with
    ``SymlinkRejected`` rather than dereferenced.

    Args:
        safe_dir: An open :class:`file_organizer.utils.safedir.SafeDir` for the
            parent directory of *name*.
        name: Single path component identifying the file inside *safe_dir*.
        **kwargs: Additional arguments forwarded to the dispatched reader
            (e.g. ``max_pages`` for PDF).

    Returns:
        Extracted text content, or ``None`` if the file extension isn't
        currently supported via the SafeDir path (caller may choose to fall
        back to legacy ``read_file`` or treat as unsupported). The dispatched
        reader applies the ``os.fstat``-based ``_check_fd_size`` cap on the
        SafeDir-opened fd, raising ``FileTooLargeError`` before it parses the
        stream.

    Raises:
        file_organizer.utils.safedir.SymlinkRejected: If *name* is a symlink.
        ValueError: If *name* contains path separators or is reserved.
        FileReadError: If the reader fails on the file content.
        FileTooLargeError: If the file exceeds ``MAX_FILE_SIZE_BYTES``.
    """
    # Reject traversal payloads (``/``, ``\``, NUL, ``.``/``..``, empty) up
    # front — before extension dispatch. Otherwise a malicious component with
    # an unsupported suffix (e.g. ``../secret.unknownext``) would slip past the
    # documented component-validation contract by returning ``None`` on the
    # unsupported-extension fallback below, never reaching ``open_for_reader``.
    _validate_name(name)

    # Build a Path purely for extension parsing — never used for I/O.
    name_path = Path(name)
    name_lower = name.lower()
    if (
        name_lower.endswith(".tar.gz")
        or name_lower.endswith(".tar.bz2")
        or name_lower.endswith(".tar.xz")
    ):
        compound_ext = "." + ".".join(name_path.name.split(".")[-2:]).lower()
    else:
        compound_ext = name_path.suffix.lower()
    ext = name_path.suffix.lower()

    for check_ext in [compound_ext, ext]:
        for extensions, reader in _SAFEDIR_READERS.items():
            if check_ext in extensions:
                fd = safe_dir.open_for_reader(name)
                # Split fdopen out so the raw fd is closed only when ``fdopen``
                # itself fails (e.g. EMFILE under fd exhaustion). Once fdopen
                # returns, ``with fileobj`` owns the close.
                try:
                    fileobj = os.fdopen(fd, "rb", closefd=True)
                except OSError:
                    os.close(fd)
                    raise
                with fileobj:
                    try:
                        return reader(  # type: ignore[operator,no-any-return]
                            file_path=name_path,
                            fileobj=fileobj,
                            **kwargs,
                        )
                    except Exception as exc:
                        logger.error(f"Error reading {name}: {exc}")
                        raise

    logger.debug(
        f"Extension {ext!r} not yet supported by read_file_via_safedir; caller may fall back"
    )
    return None


def read_file_via_safedir_anchored(
    file_path: Path,
    *,
    trusted_root: Path,
    **kwargs: object,
) -> str | None:
    """Anchored-traversal variant of :func:`read_file_via_safedir`.

    Walks ``file_path.relative_to(trusted_root)`` one component at a time via
    :meth:`file_organizer.utils.safedir.SafeDir.open_anchored_reader`, so an
    ancestor directory swapped to a symlink between enumeration and this read is
    refused with :class:`file_organizer.utils.safedir.SymlinkRejected` rather
    than silently dereferenced. Closes the nested-ancestor TOCTOU window that
    the parent-rooted ``open_root(file_path.parent)`` pattern leaves open.

    Args:
        file_path: Absolute path to the file to read. Must be inside
            *trusted_root* (validated via :meth:`Path.relative_to`, which raises
            ``ValueError`` otherwise).
        trusted_root: The anchor directory whose contents are trusted —
            typically the original scan / organize root the caller walked to
            find *file_path*. Opened once via :meth:`SafeDir.open_root`;
            subsequent components are ``O_NOFOLLOW``-walked from there.
        **kwargs: Forwarded to the dispatched reader.

    Returns:
        Extracted text content, or ``None`` if the extension isn't in the
        SafeDir reader registry (mirrors :func:`read_file_via_safedir`).

    Raises:
        ValueError: If *file_path* is not under *trusted_root*, or if any
            component fails name validation.
        file_organizer.utils.safedir.SymlinkRejected: If any path component
            (intermediate or leaf) is a symlink at open time.
        FileReadError: If the reader fails on the file content.
        FileTooLargeError: If the file exceeds ``MAX_FILE_SIZE_BYTES``.

    See Also:
        :func:`read_file_via_safedir` — parent-rooted variant. Use this anchored
        variant whenever the caller has a meaningful ``trusted_root`` (the
        directory tree it walked); fall back to the parent-rooted variant only
        for standalone reads without a walk context.
    """
    # ``relative_to`` raises ValueError if file_path escapes trusted_root,
    # which is itself a security violation worth surfacing — let it propagate.
    relative = file_path.relative_to(trusted_root)

    name_lower = file_path.name.lower()
    if (
        name_lower.endswith(".tar.gz")
        or name_lower.endswith(".tar.bz2")
        or name_lower.endswith(".tar.xz")
    ):
        compound_ext = "." + ".".join(file_path.name.split(".")[-2:]).lower()
    else:
        compound_ext = file_path.suffix.lower()
    ext = file_path.suffix.lower()

    for check_ext in [compound_ext, ext]:
        for extensions, reader in _SAFEDIR_READERS.items():
            if check_ext in extensions:
                with SafeDir.open_root(trusted_root) as root:
                    fd = root.open_anchored_reader(relative)
                    try:
                        fileobj = os.fdopen(fd, "rb", closefd=True)
                    except OSError:
                        os.close(fd)
                        raise
                    with fileobj:
                        try:
                            return reader(  # type: ignore[operator,no-any-return]
                                file_path=Path(file_path.name),
                                fileobj=fileobj,
                                **kwargs,
                            )
                        except Exception as exc:
                            logger.error(f"Error reading {file_path.name}: {exc}")
                            raise

    logger.debug(
        f"Extension {ext!r} not yet supported by "
        f"read_file_via_safedir_anchored; caller may fall back"
    )
    return None
