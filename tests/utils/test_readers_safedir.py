"""Tests for the SafeDir-aware reader API.

Covers the additions made in PR3a (#267):

- ``fileobj=`` kwarg on the public reader functions in
  ``utils.readers.documents`` (text, docx, pdf, rtf, spreadsheet,
  presentation). When given, the reader uses the library's file-like
  API instead of opening the path. Path-based callers are unchanged
  (covered by the existing ``tests/utils/test_file_readers.py``).
- ``utils.readers.read_file_via_safedir(safe_dir, name)`` — the
  SafeDir-friendly dispatcher: opens via ``SafeDir.open_for_reader``
  (which refuses symlinks with ``O_NOFOLLOW``) and routes to the
  matching reader via ``fileobj=``.
- ``utils.readers._base._check_fd_size`` — fd-based size check used by
  the fileobj branch.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.utils.readers import (
    MAX_FILE_SIZE_BYTES,
    FileTooLargeError,
    read_7z_file,
    read_docx_file,
    read_dwg_file,
    read_dxf_file,
    read_ebook_file,
    read_file_via_safedir,
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
from file_organizer.utils.readers._base import _check_fd_size
from file_organizer.utils.safedir import SafeDir, SymlinkRejected

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only"),
]


# ---------------------------------------------------------------------------
# fileobj= on individual readers
# ---------------------------------------------------------------------------


class TestReadTextFileFileobj:
    def test_reads_from_fileobj(self) -> None:
        data = b"hello\nworld\n"
        assert read_text_file(fileobj=io.BytesIO(data)) == "hello\nworld\n"

    def test_respects_max_chars(self) -> None:
        data = b"x" * 50_000
        out = read_text_file(fileobj=io.BytesIO(data), max_chars=100)
        assert out == "x" * 100

    def test_ignores_invalid_utf8(self) -> None:
        # An invalid UTF-8 byte gets dropped; the surrounding ASCII remains.
        data = b"valid \xfe more"
        out = read_text_file(fileobj=io.BytesIO(data))
        assert "valid" in out
        assert "more" in out

    def test_label_falls_back_when_no_file_path(self) -> None:
        # Doesn't raise; label is just used in logs.
        assert read_text_file(fileobj=io.BytesIO(b"x")) == "x"


class TestReadDocxFileFileobj:
    @patch("file_organizer.utils.readers.documents.docx")
    def test_reads_from_fileobj(self, mock_docx: MagicMock, tmp_path: Path) -> None:
        para = MagicMock()
        para.text = "Hello docx"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [para]
        mock_docx.Document.return_value = mock_doc

        out = read_docx_file(fileobj=io.BytesIO(b"fake docx bytes"))
        assert out == "Hello docx"
        mock_docx.Document.assert_called_once()


class TestReadPdfFileFileobj:
    @patch("file_organizer.utils.readers.documents.fitz")
    def test_reads_from_fileobj_via_stream(self, mock_fitz: MagicMock) -> None:
        mock_page = MagicMock()
        mock_page.get_text.return_value = "page text"
        mock_doc = MagicMock()
        mock_doc.__enter__.return_value = mock_doc
        mock_doc.__exit__.return_value = None
        mock_doc.__len__.return_value = 1
        mock_doc.load_page.return_value = mock_page
        mock_fitz.open.return_value = mock_doc

        out = read_pdf_file(fileobj=io.BytesIO(b"%PDF-fake"))
        assert out == "page text"
        # The fileobj path must use ``stream=`` so fitz never receives a path.
        kwargs = mock_fitz.open.call_args.kwargs
        assert "stream" in kwargs
        assert kwargs.get("filetype") == "pdf"


class TestReadSpreadsheetFileFileobj:
    def test_csv_from_fileobj(self, tmp_path: Path) -> None:
        data = b"a,b,c\n1,2,3\n4,5,6\n"
        out = read_spreadsheet_file(
            file_path=tmp_path / "data.csv",
            fileobj=io.BytesIO(data),
        )
        assert out == "a,b,c\n1,2,3\n4,5,6"

    @patch("file_organizer.utils.readers.documents.openpyxl")
    def test_xlsx_from_fileobj(self, mock_openpyxl: MagicMock, tmp_path: Path) -> None:
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = iter([("h1", "h2"), (1, 2)])
        mock_wb = MagicMock()
        mock_wb.active = mock_ws
        mock_openpyxl.load_workbook.return_value = mock_wb

        out = read_spreadsheet_file(
            file_path=tmp_path / "data.xlsx",
            fileobj=io.BytesIO(b"fake xlsx"),
        )
        assert "h1,h2" in out
        assert "1,2" in out

    def test_requires_file_path_for_extension_detection(self) -> None:
        with pytest.raises(ValueError, match="file_path"):
            read_spreadsheet_file(fileobj=io.BytesIO(b"data"))


class TestReadPresentationFileFileobj:
    @patch("file_organizer.utils.readers.documents.Presentation")
    def test_reads_from_fileobj(self, mock_prs_cls: MagicMock) -> None:
        shape = MagicMock()
        shape.text = "Slide text"
        slide = MagicMock()
        slide.shapes = [shape]
        mock_prs = MagicMock()
        mock_prs.slides = [slide]
        mock_prs_cls.return_value = mock_prs

        out = read_presentation_file(fileobj=io.BytesIO(b"fake pptx"))
        assert "Slide text" in out


# ---------------------------------------------------------------------------
# Archive readers — fileobj= branch (PR3b)
# ---------------------------------------------------------------------------


def _make_zip(path: Path) -> None:
    import zipfile as _zf

    with _zf.ZipFile(path, "w", _zf.ZIP_DEFLATED) as zf:
        zf.writestr("hello.txt", "hello\n")
        zf.writestr("data.csv", "a,b,c\n1,2,3\n")


def _make_tar(path: Path, *, mode: str = "w:gz") -> None:
    import tarfile as _tf

    payload = path.parent / f".__tar_payload_{path.name}.txt"
    payload.write_text("tar payload")
    with _tf.open(path, mode) as tf:
        tf.add(payload, arcname="readme.txt")
    payload.unlink()


class TestReadZipFileFileobj:
    def test_reads_from_fileobj(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "archive.zip"
        _make_zip(zip_path)

        with zip_path.open("rb") as f:
            out = read_zip_file(file_path=zip_path, fileobj=f)
        assert "ZIP Archive: archive.zip" in out
        assert "Total files: 2" in out
        assert "hello.txt" in out
        assert "data.csv" in out

    def test_label_falls_back_when_no_file_path(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "archive.zip"
        _make_zip(zip_path)
        with zip_path.open("rb") as f:
            out = read_zip_file(fileobj=f)
        assert "ZIP Archive: <fileobj>" in out

    def test_fileobj_error_wraps_as_file_read_error(self, tmp_path: Path) -> None:
        """A zipfile parse error from the fileobj branch wraps as FileReadError."""
        from file_organizer.utils.readers import FileReadError as _FRE

        with patch(
            "file_organizer.utils.readers.archives.zipfile.ZipFile",
            side_effect=RuntimeError("synthetic zip failure"),
        ):
            with pytest.raises(_FRE, match="ZIP file"):
                read_zip_file(fileobj=io.BytesIO(b"not a zip"))

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_zip_file()


class TestReadTarFileFileobj:
    def test_reads_tar_gz_from_fileobj(self, tmp_path: Path) -> None:
        tar_path = tmp_path / "archive.tar.gz"
        _make_tar(tar_path, mode="w:gz")
        with tar_path.open("rb") as f:
            out = read_tar_file(file_path=tar_path, fileobj=f)
        assert "TAR Archive: archive.tar.gz" in out
        assert "Compression: GZ" in out
        assert "Total files: 1" in out
        assert "readme.txt" in out

    def test_reads_plain_tar_from_fileobj(self, tmp_path: Path) -> None:
        tar_path = tmp_path / "archive.tar"
        _make_tar(tar_path, mode="w")
        with tar_path.open("rb") as f:
            out = read_tar_file(file_path=tar_path, fileobj=f)
        assert "Compression: None" in out

    def test_compression_unknown_when_no_file_path(self, tmp_path: Path) -> None:
        """Without a filename hint we can't display the compression type;
        tarfile still auto-detects from the magic bytes so the read succeeds.
        """
        tar_path = tmp_path / "archive.tar.gz"
        _make_tar(tar_path, mode="w:gz")
        with tar_path.open("rb") as f:
            out = read_tar_file(fileobj=f)
        assert "Compression: Unknown" in out
        assert "readme.txt" in out

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_tar_file()


class TestRead7zFileFileobj:
    @patch("file_organizer.utils.readers.archives.py7zr")
    def test_reads_from_fileobj(self, mock_py7zr: MagicMock, tmp_path: Path) -> None:
        mock_file_info = MagicMock()
        mock_file_info.filename = "hello.txt"
        mock_file_info.uncompressed = 12
        mock_file_info.compressed = 6
        mock_archive = MagicMock()
        mock_archive.__enter__.return_value = mock_archive
        mock_archive.__exit__.return_value = None
        mock_archive.list.return_value = [mock_file_info]
        mock_archive.password_protected = False
        mock_py7zr.SevenZipFile.return_value = mock_archive

        out = read_7z_file(file_path=tmp_path / "archive.7z", fileobj=io.BytesIO(b"7z fake"))
        assert "7Z Archive: archive.7z" in out
        assert "Total files: 1" in out
        assert "hello.txt" in out

    @patch("file_organizer.utils.readers.archives.py7zr")
    def test_fileobj_error_wraps_as_file_read_error(
        self, mock_py7zr: MagicMock, tmp_path: Path
    ) -> None:
        from file_organizer.utils.readers import FileReadError as _FRE

        mock_py7zr.SevenZipFile.side_effect = RuntimeError("synthetic 7z failure")
        with pytest.raises(_FRE, match="7Z file"):
            read_7z_file(file_path=tmp_path / "x.7z", fileobj=io.BytesIO(b"not 7z"))

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_7z_file()


class TestReadRarFileFileobj:
    @patch("file_organizer.utils.readers.archives.rarfile")
    def test_reads_from_fileobj(self, mock_rarfile_mod: MagicMock, tmp_path: Path) -> None:
        mock_info = MagicMock()
        mock_info.filename = "hello.txt"
        mock_info.file_size = 100
        mock_info.compress_size = 50
        mock_rf = MagicMock()
        mock_rf.__enter__.return_value = mock_rf
        mock_rf.__exit__.return_value = None
        mock_rf.infolist.return_value = [mock_info]
        mock_rf.needs_password.return_value = False
        # The reader references the module's RarCannotExec class for the
        # narrower except branch — patch.dict-style replacement on the
        # module-level binding loses that attribute, so re-attach a real
        # class object that's never raised by the mock.
        mock_rarfile_mod.RarFile.return_value = mock_rf
        mock_rarfile_mod.RarCannotExec = type("RarCannotExec", (Exception,), {})

        out = read_rar_file(file_path=tmp_path / "archive.rar", fileobj=io.BytesIO(b"rar fake"))
        assert "RAR Archive: archive.rar" in out
        assert "Total files: 1" in out
        assert "hello.txt" in out

    @patch("file_organizer.utils.readers.archives.rarfile")
    def test_fileobj_error_wraps_as_file_read_error(
        self, mock_rarfile_mod: MagicMock, tmp_path: Path
    ) -> None:
        from file_organizer.utils.readers import FileReadError as _FRE

        mock_rarfile_mod.RarFile.side_effect = RuntimeError("synthetic rar failure")
        mock_rarfile_mod.RarCannotExec = type("RarCannotExec", (Exception,), {})
        with pytest.raises(_FRE, match="RAR file"):
            read_rar_file(file_path=tmp_path / "x.rar", fileobj=io.BytesIO(b"not rar"))

    @patch("file_organizer.utils.readers.archives.rarfile")
    def test_fileobj_rar_cannot_exec_wraps_with_unrar_hint(
        self, mock_rarfile_mod: MagicMock, tmp_path: Path
    ) -> None:
        """Missing ``unrar`` tool surfaces as ``FileReadError`` with the
        install-hint message — the narrower ``RarCannotExec`` branch.
        """
        from file_organizer.utils.readers import FileReadError as _FRE

        rar_cannot_exec_cls = type("RarCannotExec", (Exception,), {})
        mock_rarfile_mod.RarCannotExec = rar_cannot_exec_cls
        mock_rarfile_mod.RarFile.side_effect = rar_cannot_exec_cls("unrar missing")
        with pytest.raises(_FRE, match="unrar tool not found"):
            read_rar_file(file_path=tmp_path / "x.rar", fileobj=io.BytesIO(b"not rar"))

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_rar_file()


# ---------------------------------------------------------------------------
# Ebook + scientific readers — fileobj= branch (PR3c)
# ---------------------------------------------------------------------------


def _make_epub(path: Path) -> None:
    """Minimal valid EPUB so ebooklib.read_epub round-trips through fileobj.

    The structure mirrors the ebooklib happy-path: mimetype + container.xml
    + a content.opf manifest + one XHTML chapter. Smaller than fixturing a
    real ebook on disk and avoids a binary blob in the repo.
    """
    import zipfile as _zf

    with _zf.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            (
                '<?xml version="1.0"?>'
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                "<rootfiles>"
                '<rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>'
                "</rootfiles></container>"
            ),
        )
        zf.writestr(
            "content.opf",
            (
                '<?xml version="1.0"?>'
                '<package version="2.0" xmlns="http://www.idpf.org/2007/opf" '
                'unique-identifier="bookid">'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<dc:title>Test Book</dc:title>"
                '<dc:identifier id="bookid">test</dc:identifier>'
                "<dc:language>en</dc:language></metadata>"
                '<manifest><item id="ch1" href="ch1.xhtml" '
                'media-type="application/xhtml+xml"/></manifest>'
                '<spine><itemref idref="ch1"/></spine></package>'
            ),
        )
        zf.writestr(
            "ch1.xhtml",
            "<html><body><p>Chapter one with searchable content text</p></body></html>",
        )


class TestReadEbookFileFileobj:
    def test_reads_from_fileobj(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        _make_epub(epub_path)
        with epub_path.open("rb") as f:
            out = read_ebook_file(file_path=epub_path, fileobj=f)
        assert "Chapter one with searchable content" in out

    def test_label_falls_back_when_no_file_path(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        _make_epub(epub_path)
        with epub_path.open("rb") as f:
            # No file_path supplied: extension check is skipped, label is <fileobj>
            out = read_ebook_file(fileobj=f)
        assert "Chapter one" in out

    def test_rejects_non_epub_extension(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers import FileReadError as _FRE

        with pytest.raises(_FRE, match="Only .epub supported"):
            read_ebook_file(file_path=tmp_path / "book.azw3", fileobj=io.BytesIO(b"x"))

    def test_fileobj_error_wraps_as_file_read_error(self, tmp_path: Path) -> None:
        """A parse error from ebooklib is wrapped as FileReadError on the
        fileobj branch, mirroring the path branch's contract.
        """
        from file_organizer.utils.readers import FileReadError as _FRE

        with pytest.raises(_FRE, match="ebook file"):
            read_ebook_file(file_path=tmp_path / "x.epub", fileobj=io.BytesIO(b"not a zip"))

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_ebook_file()


class TestReadHdf5FileFileobj:
    """``h5py`` is in the ``scientific`` optional extra and not installed by
    the default CI matrix (``.[dev,search]``). Tests mock the library so
    they exercise the reader's Python code paths regardless — matches the
    existing pattern in ``test_file_readers_extended.py``.
    """

    def _build_mocked_h5py(self) -> tuple[MagicMock, MagicMock]:
        mock_ds = MagicMock()
        mock_ds.shape = (4,)
        mock_ds.dtype = "int32"
        mock_ds.nbytes = 16
        mock_ds.attrs = {}

        def fake_visititems(callback):  # type: ignore[no-untyped-def]
            callback("alpha", mock_ds)

        mock_hf = MagicMock()
        mock_hf.keys.return_value = ["alpha"]
        mock_hf.visititems.side_effect = fake_visititems
        mock_hf.__enter__.return_value = mock_hf
        mock_hf.__exit__.return_value = None
        mock_h5py = MagicMock()
        mock_h5py.File.return_value = mock_hf
        mock_h5py.Dataset = type(mock_ds)  # so isinstance(ds, Dataset) holds
        mock_h5py.Group = type(None)  # Won't match group branch
        return mock_h5py, mock_hf

    def test_reads_from_fileobj(self, tmp_path: Path) -> None:
        mock_h5py, _ = self._build_mocked_h5py()
        with (
            patch("file_organizer.utils.readers.scientific.H5PY_AVAILABLE", True),
            patch("file_organizer.utils.readers.scientific.h5py", mock_h5py, create=True),
        ):
            out = read_hdf5_file(
                file_path=tmp_path / "data.h5", fileobj=io.BytesIO(b"fake h5 bytes")
            )
        assert "HDF5 File: data.h5" in out
        assert "alpha" in out
        # Library reached with the fileobj, not the path.
        call_args, _kwargs = mock_h5py.File.call_args
        assert hasattr(call_args[0], "read")

    def test_fileobj_error_wraps_as_file_read_error(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers import FileReadError as _FRE

        mock_h5py = MagicMock()
        mock_h5py.File.side_effect = RuntimeError("synthetic h5 failure")
        with (
            patch("file_organizer.utils.readers.scientific.H5PY_AVAILABLE", True),
            patch("file_organizer.utils.readers.scientific.h5py", mock_h5py, create=True),
        ):
            with pytest.raises(_FRE, match="HDF5"):
                read_hdf5_file(file_path=tmp_path / "x.h5", fileobj=io.BytesIO(b"not h5"))

    def test_requires_arg(self) -> None:
        # No deps needed — ValueError fires before the AVAILABLE check.
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_hdf5_file()


class TestReadNetcdfFileFileobj:
    """``netCDF4`` is in the ``scientific`` optional extra. Mocked here so
    CI without the C library still exercises the buffer-into-``memory=``
    flow on the fileobj branch.
    """

    def _build_mocked_netcdf(self) -> tuple[MagicMock, MagicMock]:
        mock_dim = MagicMock()
        mock_dim.isunlimited.return_value = False
        mock_dim.__len__ = MagicMock(return_value=5)

        mock_var = MagicMock()
        mock_var.dtype = "float32"
        mock_var.shape = (5,)
        mock_var.units = "K"
        # ``hasattr(var, "long_name")`` returns True on MagicMock unless we
        # restrict the spec — accept either branch by leaving it on.

        mock_nc = MagicMock()
        mock_nc.data_model = "NETCDF4"
        mock_nc.dimensions = {"time": mock_dim}
        mock_nc.variables = {"temperature": mock_var}
        mock_nc.ncattrs.return_value = []
        mock_nc.__enter__.return_value = mock_nc
        mock_nc.__exit__.return_value = None

        mock_netcdf4 = MagicMock()
        mock_netcdf4.Dataset.return_value = mock_nc
        return mock_netcdf4, mock_nc

    def test_reads_from_fileobj_via_memory_param(self, tmp_path: Path) -> None:
        """``netCDF4.Dataset`` doesn't accept fileobj; the reader buffers
        the stream into bytes and passes ``memory=`` (the public C API).
        """
        mock_netcdf4, _ = self._build_mocked_netcdf()
        with (
            patch("file_organizer.utils.readers.scientific.NETCDF4_AVAILABLE", True),
            patch("file_organizer.utils.readers.scientific.netCDF4", mock_netcdf4, create=True),
        ):
            out = read_netcdf_file(
                file_path=tmp_path / "data.nc", fileobj=io.BytesIO(b"\x89HDF\r\n\x1a\n" * 4)
            )
        assert "NetCDF File: data.nc" in out
        assert "NETCDF4" in out
        assert "temperature" in out
        # The fileobj branch passes ``memory=<bytes>`` (not a path).
        _args, kwargs = mock_netcdf4.Dataset.call_args
        assert kwargs.get("memory") is not None
        assert isinstance(kwargs["memory"], bytes)

    def test_fileobj_error_wraps_as_file_read_error(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers import FileReadError as _FRE

        mock_netcdf4 = MagicMock()
        mock_netcdf4.Dataset.side_effect = RuntimeError("synthetic netcdf failure")
        with (
            patch("file_organizer.utils.readers.scientific.NETCDF4_AVAILABLE", True),
            patch("file_organizer.utils.readers.scientific.netCDF4", mock_netcdf4, create=True),
        ):
            with pytest.raises(_FRE, match="NetCDF"):
                read_netcdf_file(file_path=tmp_path / "x.nc", fileobj=io.BytesIO(b"not netcdf"))

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_netcdf_file()


class TestReadMatFileFileobj:
    """``scipy`` is in the ``scientific`` optional extra. Mocked so the
    fileobj branch of ``read_mat_file`` is exercised on CI without scipy.
    """

    def test_reads_from_fileobj(self, tmp_path: Path) -> None:
        mock_loadmat = MagicMock(
            return_value={"__header__": b"MAT", "alpha": MagicMock(shape=(3,))}
        )
        with (
            patch("file_organizer.utils.readers.scientific.SCIPY_AVAILABLE", True),
            patch("file_organizer.utils.readers.scientific.loadmat", mock_loadmat, create=True),
        ):
            out = read_mat_file(file_path=tmp_path / "data.mat", fileobj=io.BytesIO(b"fake"))
        assert "MATLAB File: data.mat" in out
        assert "alpha" in out
        # Library reached with the fileobj, not the path.
        call_args, _kwargs = mock_loadmat.call_args
        assert hasattr(call_args[0], "read")

    def test_fileobj_error_wraps_as_file_read_error(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers import FileReadError as _FRE

        mock_loadmat = MagicMock(side_effect=RuntimeError("synthetic mat failure"))
        with (
            patch("file_organizer.utils.readers.scientific.SCIPY_AVAILABLE", True),
            patch("file_organizer.utils.readers.scientific.loadmat", mock_loadmat, create=True),
        ):
            with pytest.raises(_FRE, match="MAT"):
                read_mat_file(file_path=tmp_path / "x.mat", fileobj=io.BytesIO(b"not a mat"))

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_mat_file()


# ---------------------------------------------------------------------------
# CAD readers — fileobj= branch (PR3d)
# ---------------------------------------------------------------------------


def _build_mocked_ezdxf_doc() -> MagicMock:
    """Return a MagicMock that quacks like an ezdxf Drawing.

    Shared by the DXF / DWG fileobj tests so the mock surface stays
    consistent — ``_process_dxf_doc`` iterates layers, modelspace
    entities, and blocks; the mock provides one of each.
    """
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
    return mock_doc


class TestReadDxfFileFileobj:
    """``ezdxf`` is in the ``cad`` optional extra (not in ``.[dev,search]``).
    Mocked so the reader's Python code paths are exercised on CI without
    the library installed.
    """

    def test_reads_from_fileobj(self, tmp_path: Path) -> None:
        mock_doc = _build_mocked_ezdxf_doc()
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf", create=True) as mock_ezdxf,
        ):
            mock_ezdxf.read.return_value = mock_doc
            out = read_dxf_file(
                file_path=tmp_path / "model.dxf", fileobj=io.BytesIO(b"0\nSECTION\n")
            )
        assert "DXF Document Metadata" in out
        assert "AC1032" in out
        assert "Layer0" in out
        # The fileobj branch must use ``ezdxf.read`` (text-stream API),
        # not ``ezdxf.readfile`` (path API).
        mock_ezdxf.read.assert_called_once()
        mock_ezdxf.readfile.assert_not_called()

    def test_fileobj_error_wraps_as_file_read_error(self, tmp_path: Path) -> None:
        from file_organizer.utils.readers import FileReadError as _FRE

        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf", create=True) as mock_ezdxf,
        ):
            mock_ezdxf.read.side_effect = RuntimeError("synthetic ezdxf failure")
            with pytest.raises(_FRE, match="DXF"):
                read_dxf_file(file_path=tmp_path / "bad.dxf", fileobj=io.BytesIO(b"not dxf"))

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_dxf_file()

    def test_fileobj_not_closed_after_return(self, tmp_path: Path) -> None:
        """The fileobj= contract preserves caller ownership. ``ezdxf.read``
        is fed via ``io.TextIOWrapper``, which closes its source stream
        on GC unless ``detach()`` is called — verify the underlying
        binary stream survives the call.
        """
        mock_doc = _build_mocked_ezdxf_doc()
        fileobj = io.BytesIO(b"0\nSECTION\n")
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf", create=True) as mock_ezdxf,
        ):
            mock_ezdxf.read.return_value = mock_doc
            read_dxf_file(file_path=tmp_path / "x.dxf", fileobj=fileobj)
        import gc

        gc.collect()  # force TextIOWrapper finalisation
        assert not fileobj.closed


class TestReadDwgFileFileobj:
    """DWG falls back to a basic file-info message when ezdxf can't parse —
    the fileobj branch uses ``os.fstat`` for size instead of ``Path.stat()``.
    """

    def test_reads_from_fileobj_when_ezdxf_parses(self, tmp_path: Path) -> None:
        mock_doc = _build_mocked_ezdxf_doc()
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf", create=True) as mock_ezdxf,
        ):
            mock_ezdxf.read.return_value = mock_doc
            out = read_dwg_file(file_path=tmp_path / "model.dwg", fileobj=io.BytesIO(b"00000"))
        assert "AC1032" in out
        mock_ezdxf.read.assert_called_once()

    def test_fileobj_fallback_when_ezdxf_fails(self, tmp_path: Path) -> None:
        """``ezdxf`` can't always parse DWG; the reader catches and emits
        a basic file-info message. The fileobj branch derives size from
        ``os.fstat`` rather than touching the path.
        """
        p = tmp_path / "blob.dwg"
        p.write_bytes(b"binary dwg content here")
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf", create=True) as mock_ezdxf,
        ):
            mock_ezdxf.read.side_effect = RuntimeError("cannot parse DWG")
            with p.open("rb") as f:
                out = read_dwg_file(file_path=p, fileobj=f)
        assert "DWG File Information" in out
        assert "blob.dwg" in out
        assert "ODA File Converter" in out
        # Size came from os.fstat on the fileobj, not Path.stat.
        assert "Size:" in out

    def test_fileobj_fallback_handles_unstatable_stream(self, tmp_path: Path) -> None:
        """``BytesIO`` raises on ``fileno()``; the size line is omitted."""
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch("file_organizer.utils.readers.cad.ezdxf", create=True) as mock_ezdxf,
        ):
            mock_ezdxf.read.side_effect = RuntimeError("cannot parse")
            out = read_dwg_file(file_path=tmp_path / "x.dwg", fileobj=io.BytesIO(b"binary"))
        assert "DWG File Information" in out
        # Size line is suppressed when fstat fails (BytesIO).
        assert "Size:" not in out

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_dwg_file()


class TestReadStepFileFileobj:
    """STEP is plain ASCII; the fileobj branch decodes the first 10 KB."""

    def test_reads_from_fileobj(self, tmp_path: Path) -> None:
        step_content = (
            "ISO-10303-21;\n"
            "HEADER;\n"
            "FILE_DESCRIPTION(('test description'),'2;1');\n"
            "FILE_NAME('test.step','2026-01-01',('me'),('co'),'tool','sys','auth');\n"
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
            "ENDSEC;\n"
            "DATA;\n"
            "#1=POINT('',(0.,0.,0.));\n"
            "#2=POINT('',(1.,1.,1.));\n"
            "ENDSEC;\n"
            "END-ISO-10303-21;\n"
        )
        p = tmp_path / "model.step"
        p.write_text(step_content)
        with p.open("rb") as f:
            out = read_step_file(file_path=p, fileobj=f)
        assert "STEP File Information" in out
        assert "model.step" in out
        assert "FILE_DESCRIPTION" in out
        assert "Approximate entity count: 2" in out
        assert "Size:" in out

    def test_fileobj_size_omitted_for_unstatable_stream(self, tmp_path: Path) -> None:
        """``BytesIO`` can't be ``fstat``ed; the Size line is omitted."""
        out = read_step_file(
            file_path=tmp_path / "x.step",
            fileobj=io.BytesIO(b"ISO-10303-21;\nHEADER;\n"),
        )
        assert "STEP File Information" in out
        assert "Size:" not in out

    # NOTE: ``max_lines``-based truncation / byte-cap of STEP content is a
    # WP-3.1 resource-limit concern (#351), deferred to that slice. This
    # WP-2.1 slice reads the first 10 KB (matching the legacy reader), so the
    # fork's ``test_max_lines_limits_content`` assertion does not apply here.

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_step_file()


class TestReadIgesFileFileobj:
    """IGES is column-structured ASCII; the fileobj branch reads N lines."""

    def test_reads_from_fileobj(self, tmp_path: Path) -> None:
        # Column 73 is the section marker (S=Start, G=Global, D=DirectoryEntry,
        # P=ParameterData, T=Terminate). Pad each line to 72 chars + marker.
        def line(content: str, marker: str) -> str:
            return content.ljust(72) + marker + "      1\n"

        iges_content = (
            line("This is the start section", "S")
            + line(",,3HMy ,4HFILE,1,,,,", "G")
            + line("0", "D")
            + line("0", "D")
            + line("Terminate", "T")
        )
        p = tmp_path / "model.iges"
        p.write_text(iges_content)
        with p.open("rb") as f:
            out = read_iges_file(file_path=p, fileobj=f)
        assert "IGES File Information" in out
        assert "model.iges" in out
        assert "Start Section" in out
        assert "Directory entries found: 2" in out

    def test_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="file_path or fileobj"):
            read_iges_file()

    def test_fileobj_not_closed_after_return(self, tmp_path: Path) -> None:
        """IGES wraps the binary fileobj in ``TextIOWrapper`` to read text
        lines; verify ``detach()`` releases ownership so the caller's
        stream isn't closed when the wrapper goes out of scope.
        """
        fileobj = io.BytesIO(b" " * 80 + b"S\n" + b" " * 80 + b"G\n")
        read_iges_file(file_path=tmp_path / "x.iges", fileobj=fileobj)
        import gc

        gc.collect()
        assert not fileobj.closed


# ---------------------------------------------------------------------------
# Either-or argument validation
# ---------------------------------------------------------------------------


class TestFileTooLargeErrorPropagation:
    """`FileTooLargeError` from ``_check_fd_size`` must propagate to callers
    of the ``fileobj=`` branch. The dispatcher docstring promises this type;
    if the broad ``except Exception`` parser-error handler wrapped it as
    ``FileReadError``, callers could no longer distinguish oversized files
    from genuine reader failures.

    Patches ``_check_fd_size`` to raise directly — the goal here is to
    verify the reader's exception handling preserves the type, not to
    re-test ``_check_fd_size`` itself (covered above).
    """

    @staticmethod
    def _raise_too_large(*_args: object, **_kwargs: object) -> None:
        raise FileTooLargeError("test: file too large")

    def test_text_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.documents._check_fd_size",
            side_effect=self._raise_too_large,
        ):
            with pytest.raises(FileTooLargeError):
                read_text_file(fileobj=io.BytesIO(b"any"))

    def test_docx_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.documents._check_fd_size",
            side_effect=self._raise_too_large,
        ):
            with pytest.raises(FileTooLargeError):
                read_docx_file(fileobj=io.BytesIO(b"any"))

    def test_pdf_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.documents._check_fd_size",
            side_effect=self._raise_too_large,
        ):
            with pytest.raises(FileTooLargeError):
                read_pdf_file(fileobj=io.BytesIO(b"any"))

    def test_spreadsheet_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.documents._check_fd_size",
            side_effect=self._raise_too_large,
        ):
            with pytest.raises(FileTooLargeError):
                read_spreadsheet_file(file_path=tmp_path / "x.csv", fileobj=io.BytesIO(b"any"))

    def test_presentation_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.documents._check_fd_size",
            side_effect=self._raise_too_large,
        ):
            with pytest.raises(FileTooLargeError):
                read_presentation_file(fileobj=io.BytesIO(b"any"))

    def test_zip_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.archives._check_fd_size",
            side_effect=self._raise_too_large,
        ):
            with pytest.raises(FileTooLargeError):
                read_zip_file(fileobj=io.BytesIO(b"any"))

    def test_7z_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.archives._check_fd_size",
            side_effect=self._raise_too_large,
        ):
            with pytest.raises(FileTooLargeError):
                read_7z_file(fileobj=io.BytesIO(b"any"))

    def test_tar_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.archives._check_fd_size",
            side_effect=self._raise_too_large,
        ):
            with pytest.raises(FileTooLargeError):
                read_tar_file(fileobj=io.BytesIO(b"any"))

    def test_rar_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.archives._check_fd_size",
            side_effect=self._raise_too_large,
        ):
            with pytest.raises(FileTooLargeError):
                read_rar_file(fileobj=io.BytesIO(b"any"))

    def test_ebook_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.ebook._check_fd_size", side_effect=self._raise_too_large
        ):
            with pytest.raises(FileTooLargeError):
                read_ebook_file(fileobj=io.BytesIO(b"any"))

    def test_hdf5_reader_propagates(self, tmp_path: Path) -> None:
        # Patch H5PY_AVAILABLE so the optional-dep ImportError doesn't fire
        # ahead of the size-check on CI without h5py installed.
        with (
            patch("file_organizer.utils.readers.scientific.H5PY_AVAILABLE", True),
            patch(
                "file_organizer.utils.readers.scientific._check_fd_size",
                side_effect=self._raise_too_large,
            ),
        ):
            with pytest.raises(FileTooLargeError):
                read_hdf5_file(fileobj=io.BytesIO(b"any"))

    def test_netcdf_reader_propagates(self, tmp_path: Path) -> None:
        with (
            patch("file_organizer.utils.readers.scientific.NETCDF4_AVAILABLE", True),
            patch(
                "file_organizer.utils.readers.scientific._check_fd_size",
                side_effect=self._raise_too_large,
            ),
        ):
            with pytest.raises(FileTooLargeError):
                read_netcdf_file(fileobj=io.BytesIO(b"any"))

    def test_mat_reader_propagates(self, tmp_path: Path) -> None:
        with (
            patch("file_organizer.utils.readers.scientific.SCIPY_AVAILABLE", True),
            patch(
                "file_organizer.utils.readers.scientific._check_fd_size",
                side_effect=self._raise_too_large,
            ),
        ):
            with pytest.raises(FileTooLargeError):
                read_mat_file(fileobj=io.BytesIO(b"any"))

    def test_dxf_reader_propagates(self, tmp_path: Path) -> None:
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch(
                "file_organizer.utils.readers.cad._check_fd_size", side_effect=self._raise_too_large
            ),
        ):
            with pytest.raises(FileTooLargeError):
                read_dxf_file(fileobj=io.BytesIO(b"any"))

    def test_dwg_reader_propagates(self, tmp_path: Path) -> None:
        with (
            patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
            patch(
                "file_organizer.utils.readers.cad._check_fd_size", side_effect=self._raise_too_large
            ),
        ):
            with pytest.raises(FileTooLargeError):
                read_dwg_file(fileobj=io.BytesIO(b"any"))

    def test_step_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.cad._check_fd_size", side_effect=self._raise_too_large
        ):
            with pytest.raises(FileTooLargeError):
                read_step_file(fileobj=io.BytesIO(b"any"))

    def test_iges_reader_propagates(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.utils.readers.cad._check_fd_size", side_effect=self._raise_too_large
        ):
            with pytest.raises(FileTooLargeError):
                read_iges_file(fileobj=io.BytesIO(b"any"))


class TestRequiresFilePathOrFileobj:
    """Every reader must reject calls with neither arg supplied."""

    @pytest.mark.parametrize(
        "reader",
        [
            read_text_file,
            read_docx_file,
            read_pdf_file,
            read_presentation_file,
            read_zip_file,
            read_7z_file,
            read_tar_file,
            read_rar_file,
            read_ebook_file,
            read_hdf5_file,
            read_netcdf_file,
            read_mat_file,
            read_dxf_file,
            read_dwg_file,
            read_step_file,
            read_iges_file,
        ],
    )
    def test_rejects_both_args_missing(self, reader) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(ValueError, match="file_path or fileobj"):
            reader()


# ---------------------------------------------------------------------------
# read_file_via_safedir: dispatcher + symlink rejection
# ---------------------------------------------------------------------------


class TestReadFileViaSafedir:
    def test_reads_real_text_file(self, tmp_path: Path) -> None:
        (tmp_path / "notes.txt").write_text("integration test content")
        with SafeDir.open_root(tmp_path) as sd:
            out = read_file_via_safedir(sd, "notes.txt")
        assert out == "integration test content"

    def test_reads_md_file(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("# heading\n\nbody")
        with SafeDir.open_root(tmp_path) as sd:
            out = read_file_via_safedir(sd, "doc.md")
        assert "heading" in out

    def test_refuses_symlink(self, tmp_path: Path) -> None:
        """The dispatcher uses ``open_for_reader`` which refuses symlinks."""
        honey = tmp_path / "honey.txt"
        honey.write_text("do_not_exfiltrate")
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "link.txt").symlink_to(honey)
        except OSError:
            pytest.skip("symlink creation not supported")

        with SafeDir.open_root(organize) as sd:
            with pytest.raises(SymlinkRejected):
                read_file_via_safedir(sd, "link.txt")

    def test_unsupported_extension_returns_none(self, tmp_path: Path) -> None:
        """Extensions outside ``_SAFEDIR_READERS`` return None — caller can
        fall back to legacy path-based ``read_file`` (which itself returns
        None for genuinely unknown formats). After PR3d, every reader the
        codebase supports has a SafeDir mapping, so this exercises the
        truly-unsupported branch with a synthetic extension.
        """
        (tmp_path / "data.unknownext").write_text("dummy")
        with SafeDir.open_root(tmp_path) as sd:
            assert read_file_via_safedir(sd, "data.unknownext") is None

    def test_rejects_bad_name(self, tmp_path: Path) -> None:
        """Component-name validation rides on SafeDir.open_for_reader."""
        with SafeDir.open_root(tmp_path) as sd:
            # ``../escape.txt`` contains ``/`` → SafeDir's _validate_name
            # rejects with "name contains forbidden character".
            with pytest.raises(ValueError, match="forbidden character"):
                read_file_via_safedir(sd, "../escape.txt")

    def test_reads_real_zip_archive(self, tmp_path: Path) -> None:
        """End-to-end: dispatcher resolves ``.zip`` via the new SafeDir
        archive entry and returns the metadata-list output of
        ``read_zip_file``.
        """
        _make_zip(tmp_path / "real.zip")
        with SafeDir.open_root(tmp_path) as sd:
            out = read_file_via_safedir(sd, "real.zip")
        assert out is not None
        assert "ZIP Archive: real.zip" in out
        assert "hello.txt" in out

    @pytest.mark.parametrize(
        ("name", "tar_mode", "expected_compression"),
        [
            ("real.tar", "w", "None"),
            ("real.tar.gz", "w:gz", "GZ"),
            ("real.tgz", "w:gz", "GZ"),
            ("real.tar.bz2", "w:bz2", "BZ2"),
            ("real.tbz2", "w:bz2", "BZ2"),
            ("real.tar.xz", "w:xz", "XZ"),
        ],
    )
    def test_reads_real_tar_archive_for_each_extension(
        self, tmp_path: Path, name: str, tar_mode: str, expected_compression: str
    ) -> None:
        """End-to-end via the dispatcher for every TAR extension in
        ``_SAFEDIR_READERS``. A dropped mapping (incl. the compound-extension
        branch in ``read_file_via_safedir``) would silently return ``None`` —
        we assert real content makes it through for each alias so the
        mapping has positive coverage.
        """
        _make_tar(tmp_path / name, mode=tar_mode)
        with SafeDir.open_root(tmp_path) as sd:
            out = read_file_via_safedir(sd, name)
        assert out is not None, f"dispatcher returned None for {name!r}"
        assert f"TAR Archive: {name}" in out
        assert f"Compression: {expected_compression}" in out
        assert "readme.txt" in out

    def test_dispatches_7z_extension(self, tmp_path: Path) -> None:
        """``.7z`` routes to ``read_7z_file`` via the SafeDir dispatcher.

        ``_SAFEDIR_READERS`` holds direct function references — patching
        ``read_7z_file`` at the module level won't intercept. Instead we
        patch the underlying py7zr binding and assert the reader reached
        it with the SafeDir-opened fileobj (same approach as
        ``test_dispatcher_reraises_unexpected_reader_exception``).
        """
        (tmp_path / "data.7z").write_bytes(b"7z placeholder")
        mock_file_info = MagicMock()
        mock_file_info.filename = "inside.txt"
        mock_file_info.uncompressed = 5
        mock_file_info.compressed = 5
        mock_archive = MagicMock()
        mock_archive.__enter__.return_value = mock_archive
        mock_archive.__exit__.return_value = None
        mock_archive.list.return_value = [mock_file_info]
        mock_archive.password_protected = False

        with SafeDir.open_root(tmp_path) as sd:
            with patch("file_organizer.utils.readers.archives.py7zr") as mock_py7zr:
                mock_py7zr.SevenZipFile.return_value = mock_archive
                out = read_file_via_safedir(sd, "data.7z")
        assert out is not None
        assert "7Z Archive: data.7z" in out
        # SafeDir-opened fileobj reached the underlying library.
        mock_py7zr.SevenZipFile.assert_called_once()
        call_args, _ = mock_py7zr.SevenZipFile.call_args
        assert hasattr(call_args[0], "read")

    def test_dispatches_rar_extension(self, tmp_path: Path) -> None:
        """``.rar`` routes to ``read_rar_file`` via the SafeDir dispatcher."""
        (tmp_path / "data.rar").write_bytes(b"rar placeholder")
        mock_info = MagicMock()
        mock_info.filename = "inside.txt"
        mock_info.file_size = 10
        mock_info.compress_size = 8
        mock_rf = MagicMock()
        mock_rf.__enter__.return_value = mock_rf
        mock_rf.__exit__.return_value = None
        mock_rf.infolist.return_value = [mock_info]
        mock_rf.needs_password.return_value = False

        with SafeDir.open_root(tmp_path) as sd:
            with patch("file_organizer.utils.readers.archives.rarfile") as mock_rarfile_mod:
                mock_rarfile_mod.RarFile.return_value = mock_rf
                mock_rarfile_mod.RarCannotExec = type("RarCannotExec", (Exception,), {})
                out = read_file_via_safedir(sd, "data.rar")
        assert out is not None
        assert "RAR Archive: data.rar" in out
        mock_rarfile_mod.RarFile.assert_called_once()
        call_args, _ = mock_rarfile_mod.RarFile.call_args
        assert hasattr(call_args[0], "read")

    def test_dispatches_epub_extension(self, tmp_path: Path) -> None:
        """End-to-end: dispatcher resolves ``.epub`` via the new SafeDir
        ebook entry and returns ebooklib's parsed text.
        """
        _make_epub(tmp_path / "book.epub")
        with SafeDir.open_root(tmp_path) as sd:
            out = read_file_via_safedir(sd, "book.epub")
        assert out is not None
        assert "Chapter one with searchable content" in out

    @pytest.mark.parametrize("name", ["data.h5", "data.hdf5", "data.hdf"])
    def test_dispatches_hdf5_extensions(self, tmp_path: Path, name: str) -> None:
        """Each HDF5 alias must reach ``read_hdf5_file`` via the dispatcher.

        Mocked rather than using a real HDF5 file so the test runs on the
        default CI matrix (``.[dev,search]`` — no ``scientific`` extra).
        Asserts the SafeDir-opened fileobj reached the library binding.
        """
        # _SAFEDIR_READERS still requires the file to exist for SafeDir's
        # open_for_reader, so a placeholder is enough.
        (tmp_path / name).write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 32)

        mock_ds = MagicMock()
        mock_ds.shape = (3,)
        mock_ds.dtype = "int32"
        mock_ds.nbytes = 12
        mock_ds.attrs = {}

        def fake_visititems(callback):  # type: ignore[no-untyped-def]
            callback("alpha", mock_ds)

        mock_hf = MagicMock()
        mock_hf.keys.return_value = ["alpha"]
        mock_hf.visititems.side_effect = fake_visititems
        mock_hf.__enter__.return_value = mock_hf
        mock_hf.__exit__.return_value = None

        with SafeDir.open_root(tmp_path) as sd:
            with (
                patch("file_organizer.utils.readers.scientific.H5PY_AVAILABLE", True),
                patch("file_organizer.utils.readers.scientific.h5py", create=True) as mock_h5py,
            ):
                mock_h5py.File.return_value = mock_hf
                mock_h5py.Dataset = type(mock_ds)
                mock_h5py.Group = type(None)
                out = read_file_via_safedir(sd, name)
        assert out is not None
        assert f"HDF5 File: {name}" in out
        assert "alpha" in out
        # SafeDir-opened fileobj reached the underlying library.
        call_args, _kwargs = mock_h5py.File.call_args
        assert hasattr(call_args[0], "read")

    @pytest.mark.parametrize("name", ["data.nc", "data.nc4", "data.netcdf"])
    def test_dispatches_netcdf_extensions(self, tmp_path: Path, name: str) -> None:
        """Each NetCDF alias must reach ``read_netcdf_file`` via the
        dispatcher and route through the ``memory=`` parameter (the
        netCDF4 C API doesn't accept fileobjs).
        """
        (tmp_path / name).write_bytes(b"CDF\x01" + b"\x00" * 32)

        mock_dim = MagicMock()
        mock_dim.isunlimited.return_value = False
        mock_dim.__len__ = MagicMock(return_value=2)
        mock_var = MagicMock()
        mock_var.dtype = "float32"
        mock_var.shape = (2,)

        mock_nc = MagicMock()
        mock_nc.data_model = "NETCDF4"
        mock_nc.dimensions = {"time": mock_dim}
        mock_nc.variables = {"x": mock_var}
        mock_nc.ncattrs.return_value = []
        mock_nc.__enter__.return_value = mock_nc
        mock_nc.__exit__.return_value = None

        with SafeDir.open_root(tmp_path) as sd:
            with (
                patch("file_organizer.utils.readers.scientific.NETCDF4_AVAILABLE", True),
                patch(
                    "file_organizer.utils.readers.scientific.netCDF4", create=True
                ) as mock_netcdf4,
            ):
                mock_netcdf4.Dataset.return_value = mock_nc
                out = read_file_via_safedir(sd, name)
        assert out is not None
        assert f"NetCDF File: {name}" in out
        assert "time: 2" in out
        # The fileobj was buffered into bytes and passed as ``memory=``.
        _args, kwargs = mock_netcdf4.Dataset.call_args
        assert isinstance(kwargs.get("memory"), bytes)

    def test_dispatches_mat_extension(self, tmp_path: Path) -> None:
        """End-to-end: ``.mat`` reaches ``read_mat_file`` and scipy parses
        the in-memory stream.
        """
        (tmp_path / "data.mat").write_bytes(b"MATLAB 5.0 MAT-file\x00" + b"\x00" * 32)

        mock_loadmat = MagicMock(
            return_value={"__header__": b"MAT", "alpha": MagicMock(shape=(2,))}
        )
        with SafeDir.open_root(tmp_path) as sd:
            with (
                patch("file_organizer.utils.readers.scientific.SCIPY_AVAILABLE", True),
                patch("file_organizer.utils.readers.scientific.loadmat", mock_loadmat, create=True),
            ):
                out = read_file_via_safedir(sd, "data.mat")
        assert out is not None
        assert "MATLAB File: data.mat" in out
        assert "alpha" in out
        # SafeDir-opened fileobj reached the underlying library.
        call_args, _kwargs = mock_loadmat.call_args
        assert hasattr(call_args[0], "read")

    @pytest.mark.parametrize(
        ("name", "expected_ezdxf_method"),
        [
            ("model.dxf", "read"),
            ("model.dwg", "read"),
        ],
    )
    def test_dispatches_dxf_dwg_extensions(
        self, tmp_path: Path, name: str, expected_ezdxf_method: str
    ) -> None:
        """``.dxf`` and ``.dwg`` reach the ezdxf-based readers via the
        dispatcher. Mocked because ``ezdxf`` is in the ``cad`` optional
        extra (not in the default CI ``.[dev,search]`` install).
        """
        (tmp_path / name).write_text("0\nSECTION\nfake dxf content\n")

        mock_doc = _build_mocked_ezdxf_doc()
        with SafeDir.open_root(tmp_path) as sd:
            with (
                patch("file_organizer.utils.readers.cad.EZDXF_AVAILABLE", True),
                patch("file_organizer.utils.readers.cad.ezdxf", create=True) as mock_ezdxf,
            ):
                mock_ezdxf.read.return_value = mock_doc
                out = read_file_via_safedir(sd, name)
        assert out is not None
        assert "AC1032" in out
        # ezdxf.read (text-stream API) called, not readfile (path API).
        getattr(mock_ezdxf, expected_ezdxf_method).assert_called_once()

    @pytest.mark.parametrize("name", ["model.step", "model.stp"])
    def test_dispatches_step_extensions(self, tmp_path: Path, name: str) -> None:
        """Both ``.step`` and ``.stp`` reach ``read_step_file`` via the
        dispatcher.
        """
        (tmp_path / name).write_text(
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\n"
            "#1=POINT('',(0.,0.,0.));\nENDSEC;\nEND-ISO-10303-21;\n"
        )
        with SafeDir.open_root(tmp_path) as sd:
            out = read_file_via_safedir(sd, name)
        assert out is not None
        assert "STEP File Information" in out
        assert name in out

    @pytest.mark.parametrize("name", ["model.iges", "model.igs"])
    def test_dispatches_iges_extensions(self, tmp_path: Path, name: str) -> None:
        """Both ``.iges`` and ``.igs`` reach ``read_iges_file`` via the
        dispatcher.
        """
        line = lambda content, marker: content.ljust(72) + marker + "      1\n"  # noqa: E731
        (tmp_path / name).write_text(
            line("Start info", "S") + line(",,3HMy,4HFILE,", "G") + line("0", "D")
        )
        with SafeDir.open_root(tmp_path) as sd:
            out = read_file_via_safedir(sd, name)
        assert out is not None
        assert "IGES File Information" in out
        assert name in out

    def test_refuses_symlinked_step(self, tmp_path: Path) -> None:
        """Symlinked CAD files are refused by the dispatcher — exercises
        the SafeDir O_NOFOLLOW path for one of the new extensions.
        """
        real = tmp_path / "real.step"
        real.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\n")
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "decoy.step").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported")

        with SafeDir.open_root(organize) as sd:
            with pytest.raises(SymlinkRejected):
                read_file_via_safedir(sd, "decoy.step")

    def test_refuses_symlinked_epub(self, tmp_path: Path) -> None:
        """The dispatcher refuses a symlinked EPUB in the organize root —
        the SafeDir fd would dereference the link otherwise.
        """
        real = tmp_path / "real.epub"
        _make_epub(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "decoy.epub").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported")

        with SafeDir.open_root(organize) as sd:
            with pytest.raises(SymlinkRejected):
                read_file_via_safedir(sd, "decoy.epub")

    def test_refuses_symlinked_zip(self, tmp_path: Path) -> None:
        """A symlinked archive in the organize root must be refused, not
        followed and indexed.
        """
        real = tmp_path / "real.zip"
        _make_zip(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "decoy.zip").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported")

        with SafeDir.open_root(organize) as sd:
            with pytest.raises(SymlinkRejected):
                read_file_via_safedir(sd, "decoy.zip")


# ---------------------------------------------------------------------------
# _check_fd_size
# ---------------------------------------------------------------------------


class TestCheckFdSize:
    def test_raises_for_large_fd(self, tmp_path: Path) -> None:
        big = tmp_path / "big.bin"
        big.write_bytes(b"\x00" * 1024)
        with big.open("rb") as f:
            with pytest.raises(FileTooLargeError):
                _check_fd_size(f, max_bytes=512)

    def test_allows_small_fd(self, tmp_path: Path) -> None:
        small = tmp_path / "small.bin"
        small.write_bytes(b"\x00" * 100)
        with small.open("rb") as f:
            _check_fd_size(f, max_bytes=MAX_FILE_SIZE_BYTES)  # no raise

    def test_silently_skips_in_memory_buffers(self) -> None:
        """``BytesIO`` raises ``io.UnsupportedOperation`` on ``fileno()``;
        the check should fall through silently rather than erroring out.
        """
        _check_fd_size(io.BytesIO(b"x" * 100), max_bytes=10)  # no raise

    def test_silently_skips_when_fstat_fails(self, tmp_path: Path) -> None:
        """If ``os.fstat`` itself errors (e.g. closed fd), the check
        falls through. The reader's subsequent read will raise its own
        error; the size check shouldn't mask the real problem.
        """
        import os as _os

        target = tmp_path / "x.bin"
        target.write_bytes(b"data")
        f = target.open("rb")
        _os.close(f.fileno())
        # f.fileno() still returns the int, but fstat now raises EBADF
        _check_fd_size(f, max_bytes=10)  # no raise


class TestReadFileViaSafedirCompoundExtension:
    """Cover the ``.tar.gz`` / ``.tar.bz2`` / ``.tar.xz`` branch and the
    dispatcher's exception-rewrap path."""

    def test_tar_gz_dispatches_to_tar_reader(self, tmp_path: Path) -> None:
        """Once archives migrated in PR3b, ``.tar.gz`` resolves via the
        compound-extension branch and reaches ``read_tar_file`` with the
        SafeDir-opened fd. We assert the route taken via patching, since
        crafting a real tar.gz here would duplicate the round-trip test
        below.
        """
        (tmp_path / "data.tar.gz").write_bytes(b"\x1f\x8b\x08\x00")  # gz header
        with SafeDir.open_root(tmp_path) as sd:
            with patch(
                "file_organizer.utils.readers.archives.tarfile.open",
                side_effect=RuntimeError("synthetic tarfile failure"),
            ):
                from file_organizer.utils.readers import FileReadError as _FRE

                with pytest.raises(_FRE):
                    read_file_via_safedir(sd, "data.tar.gz")

    def test_dispatcher_reraises_unexpected_reader_exception(self, tmp_path: Path) -> None:
        """``read_file_via_safedir`` wraps the reader call in a try/except
        that logs then re-raises any exception. Covers the
        ``except Exception as exc: logger.error(...); raise`` block.

        Patching ``utils.readers.documents.fitz.open`` (the underlying
        library) reliably triggers the path because ``read_pdf_file``
        is reached via the dispatcher's ``_SAFEDIR_READERS`` dict —
        patching the module-level binding wouldn't intercept that.
        """
        (tmp_path / "report.pdf").write_bytes(b"%PDF-fake")
        with SafeDir.open_root(tmp_path) as sd:
            with patch(
                "file_organizer.utils.readers.documents.fitz.open",
                side_effect=RuntimeError("synthetic fitz failure"),
            ):
                # The reader wraps the fitz error as FileReadError;
                # the dispatcher logs and re-raises that.
                from file_organizer.utils.readers import FileReadError as _FRE

                with pytest.raises(_FRE):
                    read_file_via_safedir(sd, "report.pdf")
