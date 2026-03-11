from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.utils.file_readers import (
    FileReadError,
    read_7z_file,
    read_dwg_file,
    read_dxf_file,
    read_ebook_file,
    read_iges_file,
    read_mat_file,
    read_netcdf_file,
    read_presentation_file,
    read_rar_file,
    read_spreadsheet_file,
    read_tar_file,
)


def test_read_spreadsheet_csv_max_rows(tmp_path: Path) -> None:
    test_file = tmp_path / "test.csv"
    test_file.write_text("\n".join(["A,B"] * 150))
    content = read_spreadsheet_file(test_file, max_rows=100)
    assert len(content.split("\n")) == 100


@patch("file_organizer.utils.readers.documents.OPENPYXL_AVAILABLE", True)
def test_read_spreadsheet_xlsx_max_rows(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")

    test_file = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    for _r in range(150):
        ws.append(["A", "B"])
    wb.save(test_file)
    content = read_spreadsheet_file(test_file, max_rows=100)
    assert len(content.split("\n")) == 100


@patch("file_organizer.utils.readers.documents.PPTX_AVAILABLE", True)
@patch("file_organizer.utils.readers.documents.Presentation", create=True)
def test_read_presentation_file_error(mock_prs_cls: MagicMock, tmp_path: Path) -> None:
    mock_prs_cls.side_effect = Exception("Test error")
    test_file = tmp_path / "test.pptx"
    test_file.write_bytes(b"dummy")
    with pytest.raises(FileReadError):
        read_presentation_file(test_file)


@patch("file_organizer.utils.readers.ebook.EBOOKLIB_AVAILABLE", True)
@patch("file_organizer.utils.readers.ebook.ebooklib", create=True)
@patch("file_organizer.utils.readers.ebook.epub", create=True)
def test_read_ebook_file_max_chars(
    mock_epub: MagicMock, mock_ebooklib: MagicMock, tmp_path: Path
) -> None:
    mock_ebooklib.ITEM_DOCUMENT = 9
    mock_book = MagicMock()
    mock_item = MagicMock()
    mock_item.get_type.return_value = 9
    mock_item.get_content.return_value = b"A" * 15000
    mock_book.get_items.return_value = [mock_item]
    mock_epub.read_epub.return_value = mock_book

    test_file = tmp_path / "test.epub"
    test_file.write_bytes(b"dummy")
    content = read_ebook_file(test_file, max_chars=10000)
    assert len(content) == 10000


@patch("file_organizer.utils.readers.archives.PY7ZR_AVAILABLE", True)
@patch("file_organizer.utils.readers.archives.py7zr", create=True)
def test_read_7z_file_success(mock_py7zr: MagicMock, tmp_path: Path) -> None:
    mock_archive = MagicMock()
    mock_file = MagicMock()
    mock_file.filename = "test.txt"
    mock_file.uncompressed = 1024
    mock_file.compressed = 512
    mock_archive.list.return_value = [mock_file] * 60
    mock_archive.password_protected = False
    mock_py7zr.SevenZipFile.return_value.__enter__.return_value = mock_archive

    test_file = tmp_path / "test.7z"
    test_file.write_bytes(b"dummy")
    content = read_7z_file(test_file, max_files=50)
    assert "7Z Archive" in content
    assert "Total files: 60" in content
    assert "... and 10 more files" in content


@patch("file_organizer.utils.readers.archives.RARFILE_AVAILABLE", True)
@patch("file_organizer.utils.readers.archives.rarfile", create=True)
def test_read_rar_file_success(mock_rarfile: MagicMock, tmp_path: Path) -> None:
    mock_rf = MagicMock()
    mock_info = MagicMock()
    mock_info.filename = "test.txt"
    mock_info.file_size = 1024
    mock_info.compress_size = 512
    mock_rf.infolist.return_value = [mock_info] * 60
    mock_rf.needs_password.return_value = False
    mock_rarfile.RarFile.return_value.__enter__.return_value = mock_rf

    test_file = tmp_path / "test.rar"
    test_file.write_bytes(b"dummy")
    content = read_rar_file(test_file, max_files=50)
    assert "RAR Archive" in content
    assert "Total files: 60" in content
    assert "... and 10 more files" in content


@patch("file_organizer.utils.readers.archives.tarfile.open")
def test_read_tar_file_max_files(mock_tar_open: MagicMock, tmp_path: Path) -> None:
    mock_tf = MagicMock()
    mock_member = MagicMock()
    mock_member.isfile.return_value = True
    mock_member.isdir.return_value = False
    mock_member.size = 1024
    mock_member.name = "test.txt"
    mock_tf.getmembers.return_value = [mock_member] * 60
    mock_tar_open.return_value.__enter__.return_value = mock_tf

    test_file = tmp_path / "test.tar"
    test_file.write_bytes(b"dummy")
    content = read_tar_file(test_file, max_files=50)
    assert "Total files: 60" in content
    assert "... and 10 more files" in content


@patch("file_organizer.utils.readers.scientific.NETCDF4_AVAILABLE", True)
@patch("file_organizer.utils.readers.scientific.netCDF4", create=True)
def test_read_netcdf_file_max_vars(mock_netcdf4: MagicMock, tmp_path: Path) -> None:
    mock_ds = MagicMock()
    # Create > 20 variables
    mock_var = MagicMock()
    mock_var.shape = (10,)
    mock_var.dtype = "float"

    variables = {f"var{i}": mock_var for i in range(25)}
    mock_ds.variables = variables
    mock_ds.dimensions = {}
    mock_ds.ncattrs.return_value = []

    mock_netcdf4.Dataset.return_value.__enter__.return_value = mock_ds

    test_file = tmp_path / "test.nc"
    test_file.write_bytes(b"dummy")
    content = read_netcdf_file(test_file)
    assert len(variables) == 25
    assert "and 5 more variables" in content


@patch("file_organizer.utils.readers.scientific.NETCDF4_AVAILABLE", True)
@patch("file_organizer.utils.readers.scientific.netCDF4", create=True)
def test_read_netcdf_file_error(mock_netcdf4: MagicMock, tmp_path: Path) -> None:
    mock_netcdf4.Dataset.side_effect = Exception("Test error")
    test_file = tmp_path / "test.nc"
    test_file.write_bytes(b"dummy")
    with pytest.raises(FileReadError):
        read_netcdf_file(test_file)


@patch("file_organizer.utils.readers.scientific.SCIPY_AVAILABLE", True)
@patch("file_organizer.utils.readers.scientific.loadmat", create=True)
def test_read_mat_file_max_vars(mock_loadmat: MagicMock, tmp_path: Path) -> None:
    # return > 30 variables
    mock_loadmat.return_value = {f"var{i}": 1 for i in range(35)}

    test_file = tmp_path / "test.mat"
    test_file.write_bytes(b"dummy")
    content = read_mat_file(test_file)
    assert "and 5 more variables" in content


@patch("file_organizer.utils.readers.scientific.SCIPY_AVAILABLE", True)
@patch("file_organizer.utils.readers.scientific.loadmat", create=True)
def test_read_mat_file_error(mock_loadmat: MagicMock, tmp_path: Path) -> None:
    mock_loadmat.side_effect = Exception("Test error")
    test_file = tmp_path / "test.mat"
    test_file.write_bytes(b"dummy")
    with pytest.raises(FileReadError):
        read_mat_file(test_file)


@patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True)
@patch("file_organizer.utils.readers.cad.ezdxf", create=True)
def test_read_dxf_file_exceptions(mock_ezdxf: MagicMock, tmp_path: Path) -> None:
    mock_doc = MagicMock()
    # To hit the except branch inside $TITLE
    mock_header = MagicMock()
    mock_header.get.side_effect = [Exception("Title error"), Exception("Author error")]
    mock_doc.header = mock_header
    mock_doc.layers = []
    mock_doc.modelspace.return_value = []
    mock_doc.blocks = []
    mock_ezdxf.readfile.return_value = mock_doc

    test_file = tmp_path / "test.dxf"
    test_file.write_bytes(b"dummy")
    content = read_dxf_file(test_file)
    assert "DXF Version" in content


@patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True)
@patch("file_organizer.utils.readers.cad.ezdxf", create=True)
def test_read_dwg_file_success(mock_ezdxf: MagicMock, tmp_path: Path) -> None:
    mock_doc = MagicMock()
    mock_doc.header = MagicMock()
    mock_doc.layers = []
    mock_doc.modelspace.return_value = []
    mock_doc.blocks = []
    mock_ezdxf.readfile.return_value = mock_doc
    test_file = tmp_path / "test.dwg"
    test_file.write_bytes(b"dummy")
    content = read_dwg_file(test_file)
    mock_ezdxf.readfile.assert_called_once_with(test_file)
    assert "DXF" in content


def test_read_iges_file_entities(tmp_path: Path) -> None:
    test_file = tmp_path / "test.igs"
    # Create fake IGES with a D record
    line = "S" * 72 + "D      1"
    test_file.write_text(line)
    content = read_iges_file(test_file)
    assert "Directory entries found: 1" in content
