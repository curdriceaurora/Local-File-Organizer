"""Tests for archive and scientific format readers."""

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from file_organizer.utils.file_readers import (
    FileReadError,
    read_7z_file,
    read_file,
    read_hdf5_file,
    read_mat_file,
    read_netcdf_file,
    read_rar_file,
    read_tar_file,
    read_zip_file,
)


@pytest.fixture
def sample_zip_file(tmp_path: Path) -> Path:
    """Create a sample ZIP file for testing."""
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("file1.txt", "Hello World" * 100)
        zf.writestr("dir/file2.txt", "Test content" * 50)
        zf.writestr("file3.dat", b"Binary data" * 200)
    return zip_path


@pytest.fixture
def sample_tar_file(tmp_path: Path) -> Path:
    """Create a sample TAR file for testing."""
    tar_path = tmp_path / "sample.tar.gz"
    with tarfile.open(tar_path, 'w:gz') as tf:
        # Create in-memory files
        for name, content in [
            ("file1.txt", b"Hello World"),
            ("dir/file2.txt", b"Test content"),
            ("file3.dat", b"Binary data"),
        ]:
            data = io.BytesIO(content)
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tf.addfile(info, data)
    return tar_path


@pytest.fixture
def sample_hdf5_file(tmp_path: Path) -> Path:
    """Create a sample HDF5 file for testing."""
    try:
        import h5py
        import numpy as np
    except ImportError:
        pytest.skip("h5py not installed")

    h5_path = tmp_path / "sample.h5"
    with h5py.File(h5_path, 'w') as f:
        # Create dataset
        f.create_dataset('data1', data=np.random.rand(100, 50))
        f.create_dataset('data2', data=np.arange(1000))

        # Add attributes
        f['data1'].attrs['units'] = 'meters'
        f['data1'].attrs['description'] = 'Random data'

        # Create group
        grp = f.create_group('group1')
        grp.create_dataset('nested', data=np.ones((10, 10)))

    return h5_path


@pytest.fixture
def sample_netcdf_file(tmp_path: Path) -> Path:
    """Create a sample NetCDF file for testing."""
    try:
        import netCDF4
        import numpy as np
    except ImportError:
        pytest.skip("netCDF4 not installed")

    nc_path = tmp_path / "sample.nc"
    with netCDF4.Dataset(nc_path, 'w', format='NETCDF4') as nc:
        # Create dimensions
        nc.createDimension('time', 10)
        nc.createDimension('lat', 20)
        nc.createDimension('lon', 30)

        # Create variables
        temp = nc.createVariable('temperature', 'f4', ('time', 'lat', 'lon'))
        temp.units = 'Celsius'
        temp.long_name = 'Surface Temperature'
        temp[:] = np.random.rand(10, 20, 30)

        lat = nc.createVariable('latitude', 'f4', ('lat',))
        lat.units = 'degrees_north'
        lat[:] = np.linspace(-90, 90, 20)

        # Add global attributes
        nc.title = 'Test NetCDF File'
        nc.institution = 'Test Lab'

    return nc_path


@pytest.fixture
def sample_mat_file(tmp_path: Path) -> Path:
    """Create a sample MATLAB .mat file for testing."""
    try:
        import numpy as np
        from scipy.io import savemat
    except ImportError:
        pytest.skip("scipy not installed")

    mat_path = tmp_path / "sample.mat"
    data = {
        'var1': np.random.rand(10, 10),
        'var2': np.arange(100),
        'var3': 'test string',
        'var4': {'nested': np.ones((5, 5))},
    }
    savemat(mat_path, data)
    return mat_path


class TestArchiveReaders:
    """Tests for archive format readers."""

    def test_read_zip_file_success(self, sample_zip_file: Path) -> None:
        """Test reading a ZIP file successfully."""
        result = read_zip_file(sample_zip_file)

        assert "ZIP Archive" in result
        assert "sample.zip" in result
        assert "Total files: 3" in result
        assert "Compressed size:" in result
        assert "Uncompressed size:" in result
        assert "Compression ratio:" in result
        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "file3.dat" in result

    def test_read_zip_file_encryption_detection(self, tmp_path: Path) -> None:
        """Test detection of encrypted ZIP files."""
        zip_path = tmp_path / "encrypted.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("test.txt", "content")
            # Note: Creating truly encrypted ZIP requires pyminizip or similar
            # This test verifies the code path works

        result = read_zip_file(zip_path)
        assert "Encrypted: No" in result  # Our test file is not encrypted

    def test_read_zip_file_max_files_limit(self, tmp_path: Path) -> None:
        """Test that max_files limit is respected."""
        zip_path = tmp_path / "many_files.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for i in range(100):
                zf.writestr(f"file{i}.txt", f"content {i}")

        result = read_zip_file(zip_path, max_files=10)
        assert "Total files: 100" in result
        assert "... and 90 more files" in result

    def test_read_zip_file_nonexistent(self, tmp_path: Path) -> None:
        """Test reading non-existent ZIP file raises error."""
        with pytest.raises(FileReadError):
            read_zip_file(tmp_path / "nonexistent.zip")

    def test_read_tar_file_success(self, sample_tar_file: Path) -> None:
        """Test reading a TAR.GZ file successfully."""
        result = read_tar_file(sample_tar_file)

        assert "TAR Archive" in result
        assert "sample.tar.gz" in result
        assert "Compression: GZ" in result
        assert "Total files: 3" in result
        assert "Total directories:" in result
        assert "file1.txt" in result

    def test_read_tar_file_different_compressions(self, tmp_path: Path) -> None:
        """Test reading TAR files with different compression types."""
        # Test plain TAR
        tar_path = tmp_path / "sample.tar"
        with tarfile.open(tar_path, 'w') as tf:
            data = io.BytesIO(b"test")
            info = tarfile.TarInfo(name="test.txt")
            info.size = 4
            tf.addfile(info, data)

        result = read_tar_file(tar_path)
        assert "Compression: None" in result

    def test_read_7z_file_not_installed(self, tmp_path: Path) -> None:
        """Test that missing py7zr raises appropriate error."""
        # Create a dummy file
        file_path = tmp_path / "test.7z"
        file_path.write_bytes(b"dummy")

        # Mock py7zr as unavailable
        import file_organizer.utils.file_readers as readers
        original = readers.PY7ZR_AVAILABLE
        try:
            readers.PY7ZR_AVAILABLE = False
            with pytest.raises(ImportError, match="py7zr is not installed"):
                read_7z_file(file_path)
        finally:
            readers.PY7ZR_AVAILABLE = original

    def test_read_rar_file_not_installed(self, tmp_path: Path) -> None:
        """Test that missing rarfile raises appropriate error."""
        file_path = tmp_path / "test.rar"
        file_path.write_bytes(b"dummy")

        import file_organizer.utils.file_readers as readers
        original = readers.RARFILE_AVAILABLE
        try:
            readers.RARFILE_AVAILABLE = False
            with pytest.raises(ImportError, match="rarfile is not installed"):
                read_rar_file(file_path)
        finally:
            readers.RARFILE_AVAILABLE = original


class TestScientificReaders:
    """Tests for scientific format readers."""

    def test_read_hdf5_file_success(self, sample_hdf5_file: Path) -> None:
        """Test reading an HDF5 file successfully."""
        result = read_hdf5_file(sample_hdf5_file)

        assert "HDF5 File" in result
        assert "sample.h5" in result
        assert "Dataset:" in result
        assert "data1" in result
        assert "data2" in result
        assert "Group:" in result

    def test_read_hdf5_file_attributes(self, sample_hdf5_file: Path) -> None:
        """Test that HDF5 attributes are extracted."""
        result = read_hdf5_file(sample_hdf5_file)

        assert "units: meters" in result or "units:" in result
        assert "description:" in result or "Random data" in result

    def test_read_hdf5_file_max_datasets(self, tmp_path: Path) -> None:
        """Test that max_datasets limit is respected."""
        try:
            import h5py
            import numpy as np
        except ImportError:
            pytest.skip("h5py not installed")

        h5_path = tmp_path / "many_datasets.h5"
        with h5py.File(h5_path, 'w') as f:
            for i in range(50):
                f.create_dataset(f'data{i}', data=np.random.rand(10))

        result = read_hdf5_file(h5_path, max_datasets=10)
        assert "(showing first 10 datasets)" in result

    def test_read_hdf5_file_not_installed(self, tmp_path: Path) -> None:
        """Test that missing h5py raises appropriate error."""
        file_path = tmp_path / "test.h5"
        file_path.write_bytes(b"dummy")

        import file_organizer.utils.file_readers as readers
        original = readers.H5PY_AVAILABLE
        try:
            readers.H5PY_AVAILABLE = False
            with pytest.raises(ImportError, match="h5py is not installed"):
                read_hdf5_file(file_path)
        finally:
            readers.H5PY_AVAILABLE = original

    def test_read_netcdf_file_success(self, sample_netcdf_file: Path) -> None:
        """Test reading a NetCDF file successfully."""
        result = read_netcdf_file(sample_netcdf_file)

        assert "NetCDF File" in result
        assert "sample.nc" in result
        assert "Format:" in result
        assert "Dimensions:" in result
        assert "Variables:" in result
        assert "temperature" in result
        assert "latitude" in result

    def test_read_netcdf_file_attributes(self, sample_netcdf_file: Path) -> None:
        """Test that NetCDF attributes are extracted."""
        result = read_netcdf_file(sample_netcdf_file)

        assert "Global Attributes:" in result
        assert "title:" in result or "Test NetCDF" in result

    def test_read_netcdf_file_not_installed(self, tmp_path: Path) -> None:
        """Test that missing netCDF4 raises appropriate error."""
        file_path = tmp_path / "test.nc"
        file_path.write_bytes(b"dummy")

        import file_organizer.utils.file_readers as readers
        original = readers.NETCDF4_AVAILABLE
        try:
            readers.NETCDF4_AVAILABLE = False
            with pytest.raises(ImportError, match="netCDF4 is not installed"):
                read_netcdf_file(file_path)
        finally:
            readers.NETCDF4_AVAILABLE = original

    def test_read_mat_file_success(self, sample_mat_file: Path) -> None:
        """Test reading a MATLAB .mat file successfully."""
        result = read_mat_file(sample_mat_file)

        assert "MATLAB File" in result
        assert "sample.mat" in result
        assert "Variables:" in result
        assert "var1" in result
        assert "var2" in result

    def test_read_mat_file_not_installed(self, tmp_path: Path) -> None:
        """Test that missing scipy raises appropriate error."""
        file_path = tmp_path / "test.mat"
        file_path.write_bytes(b"dummy")

        import file_organizer.utils.file_readers as readers
        original = readers.SCIPY_AVAILABLE
        try:
            readers.SCIPY_AVAILABLE = False
            with pytest.raises(ImportError, match="scipy is not installed"):
                read_mat_file(file_path)
        finally:
            readers.SCIPY_AVAILABLE = original


class TestReadFileDispatcher:
    """Tests for read_file() dispatcher with new formats."""

    def test_read_file_zip(self, sample_zip_file: Path) -> None:
        """Test that read_file() correctly dispatches ZIP files."""
        result = read_file(sample_zip_file)
        assert result is not None
        assert "ZIP Archive" in result

    def test_read_file_tar(self, sample_tar_file: Path) -> None:
        """Test that read_file() correctly dispatches TAR files."""
        result = read_file(sample_tar_file)
        assert result is not None
        assert "TAR Archive" in result

    def test_read_file_hdf5(self, sample_hdf5_file: Path) -> None:
        """Test that read_file() correctly dispatches HDF5 files."""
        result = read_file(sample_hdf5_file)
        assert result is not None
        assert "HDF5 File" in result

    def test_read_file_netcdf(self, sample_netcdf_file: Path) -> None:
        """Test that read_file() correctly dispatches NetCDF files."""
        result = read_file(sample_netcdf_file)
        assert result is not None
        assert "NetCDF File" in result

    def test_read_file_mat(self, sample_mat_file: Path) -> None:
        """Test that read_file() correctly dispatches MAT files."""
        result = read_file(sample_mat_file)
        assert result is not None
        assert "MATLAB File" in result

    def test_read_file_multiple_extensions(self, tmp_path: Path) -> None:
        """Test that various archive extensions are recognized."""
        # Test .tgz extension
        tgz_path = tmp_path / "test.tgz"
        with tarfile.open(tgz_path, 'w:gz') as tf:
            data = io.BytesIO(b"test")
            info = tarfile.TarInfo(name="test.txt")
            info.size = 4
            tf.addfile(info, data)

        result = read_file(tgz_path)
        assert result is not None
        assert "TAR Archive" in result

    def test_read_file_h5_extension(self, tmp_path: Path) -> None:
        """Test that .h5 extension is recognized as HDF5."""
        try:
            import h5py
            import numpy as np
        except ImportError:
            pytest.skip("h5py not installed")

        h5_path = tmp_path / "test.h5"
        with h5py.File(h5_path, 'w') as f:
            f.create_dataset('data', data=np.random.rand(10))

        result = read_file(h5_path)
        assert result is not None
        assert "HDF5 File" in result


class TestErrorHandling:
    """Tests for error handling in readers."""

    def test_corrupted_zip_file(self, tmp_path: Path) -> None:
        """Test handling of corrupted ZIP files."""
        zip_path = tmp_path / "corrupted.zip"
        zip_path.write_bytes(b"Not a real ZIP file")

        with pytest.raises(FileReadError):
            read_zip_file(zip_path)

    def test_corrupted_tar_file(self, tmp_path: Path) -> None:
        """Test handling of corrupted TAR files."""
        tar_path = tmp_path / "corrupted.tar"
        tar_path.write_bytes(b"Not a real TAR file")

        with pytest.raises(FileReadError):
            read_tar_file(tar_path)

    def test_corrupted_hdf5_file(self, tmp_path: Path) -> None:
        """Test handling of corrupted HDF5 files."""
        try:
            import h5py  # noqa: F401
        except ImportError:
            pytest.skip("h5py not installed")

        h5_path = tmp_path / "corrupted.h5"
        h5_path.write_bytes(b"Not a real HDF5 file")

        with pytest.raises(FileReadError):
            read_hdf5_file(h5_path)
