# pyre-ignore-all-errors
"""Readers for scientific data formats: HDF5, NetCDF, MATLAB.

Each public ``read_X_file`` function accepts either a path (legacy) or an
open binary file-like via the ``fileobj`` keyword. The file-like path is
the SafeDir-friendly entry point: callers open via
``SafeDir.open_for_reader``, wrap in ``os.fdopen(fd, "rb")``, and hand to
the reader.

Library-specific notes:

- ``h5py.File`` accepts a file-like directly.
- ``scipy.io.loadmat`` accepts a file-like directly.
- ``netCDF4.Dataset`` is a C extension that needs either a path string or
  ``memory=<bytes>`` (an in-memory buffer). The fileobj branch reads the
  entire stream into bytes and passes ``memory=`` — fine for the kind of
  metadata-only extraction we do, but means very large NetCDF files would
  be buffered. ``_check_fd_size`` caps this defensively.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO

try:
    import h5py

    H5PY_AVAILABLE = True
except ImportError:
    H5PY_AVAILABLE = False

try:
    import netCDF4

    NETCDF4_AVAILABLE = True
except ImportError:
    NETCDF4_AVAILABLE = False

try:
    from scipy.io import loadmat

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from loguru import logger

from file_organizer.utils.readers._base import FileReadError, _check_fd_size, _check_file_size


def _parse_hdf5(source: object, max_datasets: int, label: str) -> str:
    """Parse HDF5 metadata from either a path or a fileobj.

    ``h5py.File`` accepts both forms, so this helper is shared between
    the path and fileobj branches.
    """
    with h5py.File(source, "r") as hf:
        lines = [
            f"HDF5 File: {label}",
            f"Total groups: {len(list(hf.keys()))}",
            "\nStructure:",
        ]

        dataset_count = 0

        def visit_item(name: str, obj: h5py.Dataset | h5py.Group) -> None:
            nonlocal dataset_count
            if dataset_count >= max_datasets:
                return

            if isinstance(obj, h5py.Dataset):
                shape_str = "x".join(map(str, obj.shape))
                size_kb = obj.nbytes / 1024
                lines.append(f"  Dataset: {name} [{obj.dtype}] {shape_str} ({size_kb:.2f} KB)")

                if obj.attrs:
                    for attr_name, attr_value in list(obj.attrs.items())[:3]:
                        lines.append(f"    - {attr_name}: {attr_value}")

                dataset_count += 1
            elif isinstance(obj, h5py.Group):
                lines.append(f"  Group: {name}/")

        hf.visititems(visit_item)

        if dataset_count >= max_datasets:
            lines.append(f"  ... (showing first {max_datasets} datasets)")

        text = "\n".join(lines)
        logger.debug(f"Extracted metadata from HDF5 file {label}")
        return text


def read_hdf5_file(
    file_path: str | Path | None = None,
    max_datasets: int = 20,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read metadata and structure from an HDF5 file.

    Args:
        file_path: Path to HDF5 file (legacy entry point).
        max_datasets: Maximum number of datasets to list
        fileobj: Open binary file-like (SafeDir-friendly entry point). When
            given, ``file_path`` is used only for the log label.

    Returns:
        String with HDF5 structure and metadata

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ImportError: If h5py is not installed
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    # Argument-validation contract is independent of the optional dep —
    # raise ValueError on missing args BEFORE checking H5PY_AVAILABLE so a
    # caller that supplies neither arg gets a clear API error regardless of
    # whether h5py is installed.
    if fileobj is None and file_path is None:
        raise ValueError("read_hdf5_file requires file_path or fileobj")
    if not H5PY_AVAILABLE:
        raise ImportError("h5py is not installed. Install with: pip install h5py")
    # Clamp to a sane floor — a negative limit otherwise short-circuits the
    # dataset visitor and emits "showing first -1 datasets".
    max_datasets = max(0, int(max_datasets))

    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        # Size check outside the try so ``FileTooLargeError`` propagates.
        _check_fd_size(fileobj)
        try:
            return _parse_hdf5(fileobj, max_datasets, label)
        except Exception as e:  # Intentional catch-all: h5py raises library-specific errors
            raise FileReadError(f"Failed to read HDF5 file {label}: {e}") from e
    assert file_path is not None  # narrowed by the early ValueError above
    path = Path(file_path)
    _check_file_size(path)
    try:
        return _parse_hdf5(path, max_datasets, path.name)
    except Exception as e:  # Intentional catch-all: h5py raises library-specific errors
        raise FileReadError(f"Failed to read HDF5 file {path}: {e}") from e


def _parse_netcdf(nc: Any, label: str) -> str:
    """Build the metadata string from an open netCDF4 ``Dataset``.

    The Dataset is opened by the caller — either from a path or from the
    ``memory=`` bytes buffer — and passed in already-open. We never call
    ``netCDF4.Dataset(<path>)`` from within this helper, so the surface
    flagged by the SafeDir rail stays in the public entry point.

    ``nc`` is typed as ``Any`` because netCDF4 lacks type stubs; the
    library exposes ``data_model``, ``dimensions``, ``variables``,
    ``ncattrs()``, and ``getncattr()`` on the Dataset.
    """
    lines = [
        f"NetCDF File: {label}",
        f"Format: {nc.data_model}",
        "\nDimensions:",
    ]

    for dim_name, dim in nc.dimensions.items():
        size = len(dim) if not dim.isunlimited() else "unlimited"
        lines.append(f"  - {dim_name}: {size}")

    lines.append("\nVariables:")

    for _idx, (var_name, var) in enumerate(list(nc.variables.items())[:20]):
        shape_str = "x".join(str(var.shape[i]) for i in range(len(var.shape)))
        lines.append(f"  - {var_name} ({var.dtype}): {shape_str}")

        if hasattr(var, "units"):
            lines.append(f"      units: {var.units}")
        if hasattr(var, "long_name"):
            lines.append(f"      long_name: {var.long_name}")

    if len(nc.variables) > 20:
        lines.append(f"  ... and {len(nc.variables) - 20} more variables")

    if nc.ncattrs():
        lines.append("\nGlobal Attributes:")
        for attr_name in list(nc.ncattrs())[:10]:
            attr_value = nc.getncattr(attr_name)
            lines.append(f"  - {attr_name}: {attr_value}")

    text = "\n".join(lines)
    logger.debug(f"Extracted metadata from NetCDF file {label}")
    return text


def read_netcdf_file(
    file_path: str | Path | None = None,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read metadata and structure from a NetCDF file.

    Args:
        file_path: Path to NetCDF file (legacy entry point).
        fileobj: Open binary file-like (SafeDir-friendly entry point). The
            netCDF4 C library does not accept file-likes directly, so the
            fileobj branch reads the stream into bytes and uses the
            ``memory=`` parameter. ``_check_fd_size`` enforces the 500 MB
            cap before the buffer is materialised.

    Returns:
        String with NetCDF structure and metadata

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ImportError: If netCDF4 is not installed
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    # Argument-validation contract precedes the optional-dep check.
    if fileobj is None and file_path is None:
        raise ValueError("read_netcdf_file requires file_path or fileobj")
    if not NETCDF4_AVAILABLE:
        raise ImportError("netCDF4 is not installed. Install with: pip install netCDF4")

    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        _check_fd_size(fileobj)
        try:
            data = fileobj.read()
            # ``memory=`` requires a non-empty placeholder name; the actual
            # path on disk is never opened. Library docs: pass anything
            # non-empty as ``filename`` when ``memory`` is given.
            with netCDF4.Dataset("inmemory", mode="r", memory=data) as nc:
                return _parse_netcdf(nc, label)
        except Exception as e:  # Intentional catch-all: netCDF4 raises library-specific errors
            raise FileReadError(f"Failed to read NetCDF file {label}: {e}") from e
    assert file_path is not None  # narrowed by the early ValueError above
    path = Path(file_path)
    # Cap path-branch reads at MAX_FILE_SIZE_BYTES — mirrors the fileobj
    # branch's _check_fd_size and the read_hdf5_file path-branch guard,
    # so oversized files don't get buffered into memory by netCDF4.
    _check_file_size(path)
    try:
        with netCDF4.Dataset(path, "r") as nc:
            return _parse_netcdf(nc, path.name)
    except Exception as e:  # Intentional catch-all: netCDF4 raises library-specific errors
        raise FileReadError(f"Failed to read NetCDF file {path}: {e}") from e


def _parse_mat(source: object, label: str) -> str:
    """Build MAT-file metadata from a path or fileobj.

    ``scipy.io.loadmat`` accepts both forms, so this helper is shared
    between the path and fileobj branches.
    """
    mat_contents = loadmat(source, struct_as_record=False, squeeze_me=True)

    lines = [
        f"MATLAB File: {label}",
        "\nVariables:",
    ]

    var_names = [k for k in mat_contents.keys() if not k.startswith("__")]

    for var_name in var_names[:30]:
        var = mat_contents[var_name]

        var_type = type(var).__name__
        if hasattr(var, "shape"):
            shape_str = "x".join(map(str, var.shape))
            lines.append(f"  - {var_name} ({var_type}): {shape_str}")
        else:
            lines.append(f"  - {var_name} ({var_type})")

    if len(var_names) > 30:
        lines.append(f"  ... and {len(var_names) - 30} more variables")

    text = "\n".join(lines)
    logger.debug(f"Extracted metadata from MAT file {label}")
    return text


def read_mat_file(
    file_path: str | Path | None = None,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read metadata and structure from a MATLAB .mat file.

    Args:
        file_path: Path to MAT file (legacy entry point).
        fileobj: Open binary file-like (SafeDir-friendly entry point). When
            given, ``file_path`` is used only for the log label.

    Returns:
        String with MAT file structure and metadata

    Raises:
        FileReadError: If file cannot be read
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ImportError: If scipy is not installed
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    # Argument-validation contract precedes the optional-dep check.
    if fileobj is None and file_path is None:
        raise ValueError("read_mat_file requires file_path or fileobj")
    if not SCIPY_AVAILABLE:
        raise ImportError("scipy is not installed. Install with: pip install scipy")

    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        _check_fd_size(fileobj)
        try:
            return _parse_mat(fileobj, label)
        except Exception as e:  # Intentional catch-all: scipy.io raises library-specific errors
            raise FileReadError(f"Failed to read MAT file {label}: {e}") from e
    assert file_path is not None  # narrowed by the early ValueError above
    path = Path(file_path)
    # Cap path-branch reads at MAX_FILE_SIZE_BYTES — mirrors the fileobj
    # branch's _check_fd_size and the read_hdf5_file path-branch guard.
    _check_file_size(path)
    try:
        return _parse_mat(path, path.name)
    except Exception as e:  # Intentional catch-all: scipy.io raises library-specific errors
        raise FileReadError(f"Failed to read MAT file {path}: {e}") from e
