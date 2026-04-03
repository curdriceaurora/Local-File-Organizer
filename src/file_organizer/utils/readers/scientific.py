# pyre-ignore-all-errors
"""Readers for scientific data formats: HDF5, NetCDF, MATLAB."""

from __future__ import annotations

from pathlib import Path

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

from file_organizer.utils.readers._base import FileReadError


def read_hdf5_file(file_path: str | Path, max_datasets: int = 20) -> str:
    """Read metadata and structure from an HDF5 file.

    Args:
        file_path: Path to HDF5 file
        max_datasets: Maximum number of datasets to list

    Returns:
        String with HDF5 structure and metadata

    Raises:
        FileReadError: If file cannot be read
        ImportError: If h5py is not installed
    """
    if not H5PY_AVAILABLE:
        raise ImportError("h5py is not installed. Install with: pip install h5py")

    file_path = Path(file_path)
    try:
        with h5py.File(file_path, "r") as hf:
            lines = [
                f"HDF5 File: {file_path.name}",
                f"Total groups: {len(list(hf.keys()))}",
                "\nStructure:",
            ]

            dataset_count = 0

            def visit_item(name: str, obj: h5py.Dataset | h5py.Group) -> None:
                """Visit and document HDF5 datasets and groups.

                Args:
                    name: The name of the dataset or group.
                    obj: The HDF5 dataset or group object.
                """
                nonlocal dataset_count
                if dataset_count >= max_datasets:
                    return

                if isinstance(obj, h5py.Dataset):
                    shape_str = "x".join(map(str, obj.shape))
                    size_kb = obj.nbytes / 1024
                    lines.append(f"  Dataset: {name} [{obj.dtype}] {shape_str} ({size_kb:.2f} KB)")

                    # List attributes
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
            logger.debug(f"Extracted metadata from HDF5 file {file_path.name}")
            return text

    except Exception as e:
        raise FileReadError(f"Failed to read HDF5 file {file_path}: {e}") from e


def read_netcdf_file(file_path: str | Path) -> str:
    """Read metadata and structure from a NetCDF file.

    Args:
        file_path: Path to NetCDF file

    Returns:
        String with NetCDF structure and metadata

    Raises:
        FileReadError: If file cannot be read
        ImportError: If netCDF4 is not installed
    """
    if not NETCDF4_AVAILABLE:
        raise ImportError("netCDF4 is not installed. Install with: pip install netCDF4")

    file_path = Path(file_path)
    try:
        with netCDF4.Dataset(file_path, "r") as nc:
            lines = [
                f"NetCDF File: {file_path.name}",
                f"Format: {nc.data_model}",
                "\nDimensions:",
            ]

            # List dimensions
            for dim_name, dim in nc.dimensions.items():
                size = len(dim) if not dim.isunlimited() else "unlimited"
                lines.append(f"  - {dim_name}: {size}")

            lines.append("\nVariables:")

            # List variables (first 20)
            for _idx, (var_name, var) in enumerate(list(nc.variables.items())[:20]):
                shape_str = "x".join(str(var.shape[i]) for i in range(len(var.shape)))
                lines.append(f"  - {var_name} ({var.dtype}): {shape_str}")

                # Show some attributes
                if hasattr(var, "units"):
                    lines.append(f"      units: {var.units}")
                if hasattr(var, "long_name"):
                    lines.append(f"      long_name: {var.long_name}")

            if len(nc.variables) > 20:
                lines.append(f"  ... and {len(nc.variables) - 20} more variables")

            # Global attributes
            if nc.ncattrs():
                lines.append("\nGlobal Attributes:")
                for attr_name in list(nc.ncattrs())[:10]:
                    attr_value = nc.getncattr(attr_name)
                    lines.append(f"  - {attr_name}: {attr_value}")

            text = "\n".join(lines)
            logger.debug(f"Extracted metadata from NetCDF file {file_path.name}")
            return text

    except Exception as e:
        raise FileReadError(f"Failed to read NetCDF file {file_path}: {e}") from e


def read_mat_file(file_path: str | Path) -> str:
    """Read metadata and structure from a MATLAB .mat file.

    Args:
        file_path: Path to MAT file

    Returns:
        String with MAT file structure and metadata

    Raises:
        FileReadError: If file cannot be read
        ImportError: If scipy is not installed
    """
    if not SCIPY_AVAILABLE:
        raise ImportError("scipy is not installed. Install with: pip install scipy")

    file_path = Path(file_path)
    try:
        # Load mat file
        mat_contents = loadmat(file_path, struct_as_record=False, squeeze_me=True)

        lines = [
            f"MATLAB File: {file_path.name}",
            "\nVariables:",
        ]

        # Filter out metadata variables
        var_names = [k for k in mat_contents.keys() if not k.startswith("__")]

        for var_name in var_names[:30]:  # Limit to first 30 variables
            var = mat_contents[var_name]

            # Get type and shape info
            var_type = type(var).__name__
            if hasattr(var, "shape"):
                shape_str = "x".join(map(str, var.shape))
                lines.append(f"  - {var_name} ({var_type}): {shape_str}")
            else:
                lines.append(f"  - {var_name} ({var_type})")

        if len(var_names) > 30:
            lines.append(f"  ... and {len(var_names) - 30} more variables")

        text = "\n".join(lines)
        logger.debug(f"Extracted metadata from MAT file {file_path.name}")
        return text

    except Exception as e:
        raise FileReadError(f"Failed to read MAT file {file_path}: {e}") from e
