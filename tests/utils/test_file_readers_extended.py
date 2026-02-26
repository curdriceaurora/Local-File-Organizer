"""Extended unit tests for file_readers.py - covers optional-dep happy paths.

The existing test_file_readers.py covers ImportError paths and basic readers.
This file exercises the code paths that run when optional dependencies ARE
available by mocking the library internals.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.utils.file_readers import (
    FileReadError,
    read_cad_file,
    read_file,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# read_7z_file  (py7zr mocked as available)
# ---------------------------------------------------------------------------


class TestRead7zFile:
    """Test read_7z_file with mocked py7zr."""

    def test_success(self, tmp_path):
        from file_organizer.utils.file_readers import read_7z_file

        archive_path = tmp_path / "test.7z"
        archive_path.touch()

        mock_file_info = SimpleNamespace(
            filename="file1.txt",
            compressed=512,
            uncompressed=1024,
        )
        mock_archive = MagicMock()
        mock_archive.list.return_value = [mock_file_info]
        mock_archive.password_protected = False
        mock_archive.__enter__ = MagicMock(return_value=mock_archive)
        mock_archive.__exit__ = MagicMock(return_value=False)

        with patch("file_organizer.utils.file_readers.PY7ZR_AVAILABLE", True), \
             patch("file_organizer.utils.file_readers.py7zr", create=True) as mock_py7zr:
            mock_py7zr.SevenZipFile.return_value = mock_archive
            result = read_7z_file(archive_path)

        assert "7Z Archive" in result
        assert "file1.txt" in result
        assert "Total files: 1" in result

    def test_not_installed(self, tmp_path):
        from file_organizer.utils.file_readers import read_7z_file

        with patch("file_organizer.utils.file_readers.PY7ZR_AVAILABLE", False):
            with pytest.raises(ImportError, match="py7zr"):
                read_7z_file(tmp_path / "test.7z")

    def test_read_error(self, tmp_path):
        from file_organizer.utils.file_readers import read_7z_file

        archive_path = tmp_path / "bad.7z"
        archive_path.touch()

        with patch("file_organizer.utils.file_readers.PY7ZR_AVAILABLE", True), \
             patch("file_organizer.utils.file_readers.py7zr", create=True) as mock_py7zr:
            mock_py7zr.SevenZipFile.side_effect = Exception("corrupt archive")
            with pytest.raises(FileReadError, match="Failed to read 7Z"):
                read_7z_file(archive_path)


# ---------------------------------------------------------------------------
# read_rar_file  (rarfile mocked as available)
# ---------------------------------------------------------------------------


class TestReadRarFile:
    """Test read_rar_file with mocked rarfile."""

    def test_success(self, tmp_path):
        from file_organizer.utils.file_readers import read_rar_file

        rar_path = tmp_path / "test.rar"
        rar_path.touch()

        mock_info = SimpleNamespace(
            filename="doc.txt",
            compress_size=256,
            file_size=512,
        )
        mock_rf = MagicMock()
        mock_rf.infolist.return_value = [mock_info]
        mock_rf.needs_password.return_value = False
        mock_rf.__enter__ = MagicMock(return_value=mock_rf)
        mock_rf.__exit__ = MagicMock(return_value=False)

        with patch("file_organizer.utils.file_readers.RARFILE_AVAILABLE", True), \
             patch("file_organizer.utils.file_readers.rarfile", create=True) as mock_rarfile:
            mock_rarfile.RarFile.return_value = mock_rf
            result = read_rar_file(rar_path)

        assert "RAR Archive" in result
        assert "doc.txt" in result

    def test_not_installed(self, tmp_path):
        from file_organizer.utils.file_readers import read_rar_file

        with patch("file_organizer.utils.file_readers.RARFILE_AVAILABLE", False):
            with pytest.raises(ImportError, match="rarfile"):
                read_rar_file(tmp_path / "test.rar")


# ---------------------------------------------------------------------------
# read_hdf5_file  (h5py mocked as available)
# ---------------------------------------------------------------------------


class TestReadHdf5File:
    """Test read_hdf5_file with mocked h5py."""

    def test_success(self, tmp_path):
        from file_organizer.utils.file_readers import read_hdf5_file

        hdf_path = tmp_path / "test.hdf5"
        hdf_path.touch()

        mock_hf = MagicMock()
        mock_hf.keys.return_value = ["group1"]

        # visititems callback will receive items; we simulate by calling
        # the callback with a mock dataset
        def fake_visititems(callback):
            mock_ds = MagicMock()
            mock_ds.shape = (100, 3)
            mock_ds.dtype = "float32"
            mock_ds.nbytes = 1200
            mock_ds.attrs = {}
            callback("data/values", mock_ds)

        mock_hf.visititems.side_effect = fake_visititems
        mock_hf.__enter__ = MagicMock(return_value=mock_hf)
        mock_hf.__exit__ = MagicMock(return_value=False)

        with patch("file_organizer.utils.file_readers.H5PY_AVAILABLE", True), \
             patch("file_organizer.utils.file_readers.h5py", create=True) as mock_h5py:
            mock_h5py.File.return_value = mock_hf
            mock_h5py.Dataset = type(mock_hf)  # For isinstance checks
            mock_h5py.Group = type(None)  # Won't match
            result = read_hdf5_file(hdf_path)

        assert "HDF5 File" in result
        assert "Total groups: 1" in result

    def test_not_installed(self, tmp_path):
        from file_organizer.utils.file_readers import read_hdf5_file

        with patch("file_organizer.utils.file_readers.H5PY_AVAILABLE", False):
            with pytest.raises(ImportError, match="h5py"):
                read_hdf5_file(tmp_path / "test.hdf5")


# ---------------------------------------------------------------------------
# read_netcdf_file  (netCDF4 mocked as available)
# ---------------------------------------------------------------------------


class TestReadNetcdfFile:
    """Test read_netcdf_file with mocked netCDF4."""

    def test_success(self, tmp_path):
        from file_organizer.utils.file_readers import read_netcdf_file

        nc_path = tmp_path / "test.nc"
        nc_path.touch()

        mock_dim = MagicMock()
        mock_dim.isunlimited.return_value = False
        mock_dim.__len__ = MagicMock(return_value=10)

        mock_var = MagicMock()
        mock_var.dtype = "float32"
        mock_var.shape = (10, 20)
        mock_var.units = "meters"
        mock_var.long_name = "test_variable"

        mock_nc = MagicMock()
        mock_nc.data_model = "NETCDF4"
        mock_nc.dimensions = {"time": mock_dim}
        mock_nc.variables = {"temp": mock_var}
        mock_nc.ncattrs.return_value = ["title"]
        mock_nc.getncattr.return_value = "Test Dataset"
        mock_nc.__enter__ = MagicMock(return_value=mock_nc)
        mock_nc.__exit__ = MagicMock(return_value=False)

        with patch("file_organizer.utils.file_readers.NETCDF4_AVAILABLE", True), \
             patch("file_organizer.utils.file_readers.netCDF4", create=True) as mock_netcdf4:
            mock_netcdf4.Dataset.return_value = mock_nc
            result = read_netcdf_file(nc_path)

        assert "NetCDF File" in result
        assert "NETCDF4" in result
        assert "temp" in result

    def test_not_installed(self, tmp_path):
        from file_organizer.utils.file_readers import read_netcdf_file

        with patch("file_organizer.utils.file_readers.NETCDF4_AVAILABLE", False):
            with pytest.raises(ImportError, match="netCDF4"):
                read_netcdf_file(tmp_path / "test.nc")


# ---------------------------------------------------------------------------
# read_mat_file  (scipy mocked as available)
# ---------------------------------------------------------------------------


class TestReadMatFile:
    """Test read_mat_file with mocked scipy."""

    def test_success(self, tmp_path):
        from file_organizer.utils.file_readers import read_mat_file

        mat_path = tmp_path / "test.mat"
        mat_path.touch()

        import numpy as np

        mock_contents = {
            "__header__": b"MATLAB 5.0",
            "__version__": "1.0",
            "__globals__": [],
            "data_array": np.array([1, 2, 3]),
            "scalar_val": 42,
        }

        with patch("file_organizer.utils.file_readers.SCIPY_AVAILABLE", True), \
             patch("file_organizer.utils.file_readers.loadmat", create=True, return_value=mock_contents):
            result = read_mat_file(mat_path)

        assert "MATLAB File" in result
        assert "data_array" in result
        assert "scalar_val" in result
        # Metadata keys starting with __ should be filtered out
        assert "__header__" not in result

    def test_not_installed(self, tmp_path):
        from file_organizer.utils.file_readers import read_mat_file

        with patch("file_organizer.utils.file_readers.SCIPY_AVAILABLE", False):
            with pytest.raises(ImportError, match="scipy"):
                read_mat_file(tmp_path / "test.mat")


# ---------------------------------------------------------------------------
# read_dxf_file  (ezdxf mocked as available)
# ---------------------------------------------------------------------------


class TestReadDxfFile:
    """Test read_dxf_file with mocked ezdxf."""

    def test_success(self, tmp_path):
        from file_organizer.utils.file_readers import read_dxf_file

        dxf_path = tmp_path / "test.dxf"
        dxf_path.touch()

        mock_header = MagicMock()
        mock_header.get.return_value = "Test Drawing"

        mock_layer = MagicMock()
        mock_layer.dxf.name = "Layer0"
        mock_layer.dxf.color = 7

        mock_entity = MagicMock()
        mock_entity.dxftype.return_value = "LINE"

        mock_modelspace = MagicMock()
        mock_modelspace.__iter__ = MagicMock(return_value=iter([mock_entity]))

        mock_block = MagicMock()
        mock_block.name = "MyBlock"

        mock_doc = MagicMock()
        mock_doc.header = mock_header
        mock_doc.dxfversion = "AC1032"
        mock_doc.layers = [mock_layer]
        mock_doc.modelspace.return_value = mock_modelspace
        mock_doc.blocks = [mock_block]

        with patch("file_organizer.utils.file_readers.EZDXF_AVAILABLE", True), \
             patch("file_organizer.utils.file_readers.ezdxf", create=True) as mock_ezdxf:
            mock_ezdxf.readfile.return_value = mock_doc
            result = read_dxf_file(dxf_path)

        assert "DXF Document Metadata" in result
        assert "AC1032" in result
        assert "Layer0" in result
        assert "LINE" in result

    def test_not_installed(self, tmp_path):
        from file_organizer.utils.file_readers import read_dxf_file

        with patch("file_organizer.utils.file_readers.EZDXF_AVAILABLE", False):
            with pytest.raises(ImportError, match="ezdxf"):
                read_dxf_file(tmp_path / "test.dxf")


# ---------------------------------------------------------------------------
# read_dwg_file  (ezdxf fallback path)
# ---------------------------------------------------------------------------


class TestReadDwgFile:
    """Test read_dwg_file fallback path when ezdxf cannot parse."""

    def test_fallback_when_ezdxf_fails(self, tmp_path):
        from file_organizer.utils.file_readers import read_dwg_file

        dwg_path = tmp_path / "test.dwg"
        dwg_path.write_bytes(b"DWG binary data")

        with patch("file_organizer.utils.file_readers.EZDXF_AVAILABLE", True), \
             patch("file_organizer.utils.file_readers.ezdxf", create=True) as mock_ezdxf:
            mock_ezdxf.readfile.side_effect = Exception("cannot parse DWG")
            result = read_dwg_file(dwg_path)

        assert "DWG File Information" in result
        assert "test.dwg" in result
        assert "ODA File Converter" in result

    def test_fallback_file_not_found(self, tmp_path):
        from file_organizer.utils.file_readers import read_dwg_file

        dwg_path = tmp_path / "missing.dwg"

        with patch("file_organizer.utils.file_readers.EZDXF_AVAILABLE", True), \
             patch("file_organizer.utils.file_readers.ezdxf", create=True) as mock_ezdxf:
            mock_ezdxf.readfile.side_effect = Exception("not found")
            with pytest.raises(FileReadError, match="File not found"):
                read_dwg_file(dwg_path)

    def test_not_installed(self, tmp_path):
        from file_organizer.utils.file_readers import read_dwg_file

        with patch("file_organizer.utils.file_readers.EZDXF_AVAILABLE", False):
            with pytest.raises(ImportError, match="ezdxf"):
                read_dwg_file(tmp_path / "test.dwg")


# ---------------------------------------------------------------------------
# read_file dispatch  (additional extension coverage)
# ---------------------------------------------------------------------------


class TestReadFileDispatch:
    """Test read_file dispatches correctly for additional extensions."""

    def test_unsupported_extension(self, tmp_path):
        f = tmp_path / "data.xyz"
        f.write_text("binary stuff")
        result = read_file(f)
        assert result is None

    def test_7z_dispatch(self, tmp_path):
        f = tmp_path / "archive.7z"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_7z_file", return_value="7z content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "7z content"

    def test_rar_dispatch(self, tmp_path):
        f = tmp_path / "archive.rar"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_rar_file", return_value="rar content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "rar content"

    def test_hdf5_dispatch(self, tmp_path):
        f = tmp_path / "data.hdf5"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_hdf5_file", return_value="hdf5 content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "hdf5 content"

    def test_h5_dispatch(self, tmp_path):
        f = tmp_path / "data.h5"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_hdf5_file", return_value="h5 content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "h5 content"

    def test_nc_dispatch(self, tmp_path):
        f = tmp_path / "data.nc"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_netcdf_file", return_value="nc content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "nc content"

    def test_mat_dispatch(self, tmp_path):
        f = tmp_path / "data.mat"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_mat_file", return_value="mat content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "mat content"

    def test_epub_dispatch(self, tmp_path):
        f = tmp_path / "book.epub"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_ebook_file", return_value="epub content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "epub content"

    def test_pptx_dispatch(self, tmp_path):
        f = tmp_path / "slides.pptx"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_presentation_file", return_value="pptx content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "pptx content"

    def test_dwg_dispatch(self, tmp_path):
        f = tmp_path / "drawing.dwg"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_cad_file", return_value="dwg content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "dwg content"

    def test_igs_dispatch(self, tmp_path):
        f = tmp_path / "model.igs"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_cad_file", return_value="igs content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "igs content"

    def test_tar_bz2_compound_ext(self, tmp_path):
        f = tmp_path / "archive.tar.bz2"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_tar_file", return_value="tar content") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "tar content"

    def test_tar_xz_compound_ext(self, tmp_path):
        f = tmp_path / "archive.tar.xz"
        f.touch()

        with patch("file_organizer.utils.file_readers.read_tar_file", return_value="tar xz") as mock:
            result = read_file(f)
        mock.assert_called_once()
        assert result == "tar xz"

    def test_reader_error_propagated(self, tmp_path):
        f = tmp_path / "bad.hdf5"
        f.touch()

        with patch(
            "file_organizer.utils.file_readers.read_hdf5_file",
            side_effect=FileReadError("corrupt"),
        ):
            with pytest.raises(FileReadError, match="corrupt"):
                read_file(f)


# ---------------------------------------------------------------------------
# read_cad_file dispatch
# ---------------------------------------------------------------------------


class TestReadCadFileDispatch:
    """Test the read_cad_file dispatch function."""

    def test_dxf_dispatch(self, tmp_path):
        f = tmp_path / "test.dxf"
        f.touch()
        with patch("file_organizer.utils.file_readers.read_dxf_file", return_value="dxf") as mock:
            result = read_cad_file(f)
        mock.assert_called_once()
        assert result == "dxf"

    def test_dwg_dispatch(self, tmp_path):
        f = tmp_path / "test.dwg"
        f.touch()
        with patch("file_organizer.utils.file_readers.read_dwg_file", return_value="dwg") as mock:
            result = read_cad_file(f)
        mock.assert_called_once()
        assert result == "dwg"

    def test_step_dispatch(self, tmp_path):
        f = tmp_path / "test.step"
        f.touch()
        with patch("file_organizer.utils.file_readers.read_step_file", return_value="step") as mock:
            result = read_cad_file(f)
        mock.assert_called_once()
        assert result == "step"

    def test_stp_dispatch(self, tmp_path):
        f = tmp_path / "test.stp"
        f.touch()
        with patch("file_organizer.utils.file_readers.read_step_file", return_value="stp") as mock:
            result = read_cad_file(f)
        mock.assert_called_once()
        assert result == "stp"

    def test_iges_dispatch(self, tmp_path):
        f = tmp_path / "test.iges"
        f.touch()
        with patch("file_organizer.utils.file_readers.read_iges_file", return_value="iges") as mock:
            result = read_cad_file(f)
        mock.assert_called_once()
        assert result == "iges"

    def test_unsupported_cad(self, tmp_path):
        f = tmp_path / "test.obj"
        f.touch()
        with pytest.raises(ValueError, match="Unsupported CAD"):
            read_cad_file(f)
