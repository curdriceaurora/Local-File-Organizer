"""Coverage tests for scientific readers -- targets uncovered branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.utils.readers._base import FileReadError

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# read_hdf5_file
# ---------------------------------------------------------------------------


class TestReadHdf5:
    def test_no_h5py_raises(self):
        with patch("file_organizer.utils.readers.scientific.H5PY_AVAILABLE", False):
            from file_organizer.utils.readers.scientific import read_hdf5_file

            with pytest.raises(ImportError, match="h5py"):
                read_hdf5_file(Path("/test.h5"))

    def test_file_error_raises(self):
        with patch("file_organizer.utils.readers.scientific.H5PY_AVAILABLE", True):
            mock_h5py = MagicMock()
            mock_h5py.File.side_effect = RuntimeError("bad file")
            with patch(
                "file_organizer.utils.readers.scientific.h5py",
                mock_h5py,
                create=True,
            ):
                from file_organizer.utils.readers.scientific import read_hdf5_file

                with pytest.raises(FileReadError):
                    read_hdf5_file(Path("/test.h5"))


# ---------------------------------------------------------------------------
# read_netcdf_file
# ---------------------------------------------------------------------------


class TestReadNetcdf:
    def test_no_netcdf4_raises(self):
        with patch("file_organizer.utils.readers.scientific.NETCDF4_AVAILABLE", False):
            from file_organizer.utils.readers.scientific import read_netcdf_file

            with pytest.raises(ImportError, match="netCDF4"):
                read_netcdf_file(Path("/test.nc"))

    def test_file_error_raises(self):
        with patch("file_organizer.utils.readers.scientific.NETCDF4_AVAILABLE", True):
            mock_nc = MagicMock()
            mock_nc.Dataset.side_effect = RuntimeError("bad file")
            with patch(
                "file_organizer.utils.readers.scientific.netCDF4",
                mock_nc,
                create=True,
            ):
                from file_organizer.utils.readers.scientific import read_netcdf_file

                with pytest.raises(FileReadError):
                    read_netcdf_file(Path("/test.nc"))


# ---------------------------------------------------------------------------
# read_mat_file
# ---------------------------------------------------------------------------


class TestReadMat:
    def test_no_scipy_raises(self):
        with patch("file_organizer.utils.readers.scientific.SCIPY_AVAILABLE", False):
            from file_organizer.utils.readers.scientific import read_mat_file

            with pytest.raises(ImportError, match="scipy"):
                read_mat_file(Path("/test.mat"))

    def test_file_error_raises(self):
        with patch("file_organizer.utils.readers.scientific.SCIPY_AVAILABLE", True):
            mock_loadmat = MagicMock(side_effect=RuntimeError("bad file"))
            with patch(
                "file_organizer.utils.readers.scientific.loadmat",
                mock_loadmat,
                create=True,
            ):
                from file_organizer.utils.readers.scientific import read_mat_file

                with pytest.raises(FileReadError):
                    read_mat_file(Path("/test.mat"))

    def test_successful_read(self):
        # Use a lightweight fake instead of numpy to avoid an undeclared dependency.
        # A real class named ``ndarray`` avoids mutating the global MagicMock type.
        class ndarray:
            """Fake numpy ndarray for testing."""

            def __init__(self, shape: tuple[int, ...]) -> None:
                self.shape = shape

        mock_matrix = ndarray((2, 2))

        with patch("file_organizer.utils.readers.scientific.SCIPY_AVAILABLE", True):
            mock_data = {
                "__header__": b"test",
                "__version__": "1.0",
                "matrix": mock_matrix,
                "scalar": 42,
            }
            mock_loadmat = MagicMock(return_value=mock_data)
            with patch(
                "file_organizer.utils.readers.scientific.loadmat",
                mock_loadmat,
                create=True,
            ):
                from file_organizer.utils.readers.scientific import read_mat_file

                result = read_mat_file(Path("/test.mat"))
                assert "MATLAB File" in result
                assert "matrix" in result
                assert "scalar" in result
