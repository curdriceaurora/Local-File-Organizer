# pyre-ignore-all-errors
"""Readers for document formats: plain text, DOCX, PDF, spreadsheets, presentations."""

from __future__ import annotations

from pathlib import Path

try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import docx

    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

try:
    from pptx import Presentation

    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

from loguru import logger

from file_organizer.utils.readers._base import FileReadError, _check_file_size


def read_text_file(file_path: str | Path, max_chars: int = 5000) -> str:
    """Read text content from a plain text file.

    Args:
        file_path: Path to text file
        max_chars: Maximum characters to read

    Returns:
        Text content

    Raises:
        FileReadError: If file cannot be read
    """
    file_path = Path(file_path)
    _check_file_size(file_path)
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            text = f.read(max_chars)
        logger.debug(f"Read {len(text)} characters from {file_path.name}")
        return text
    except Exception as e:
        raise FileReadError(f"Failed to read text file {file_path}: {e}") from e


def read_docx_file(file_path: str | Path) -> str:
    """Read text content from a .docx file.

    Args:
        file_path: Path to DOCX file

    Returns:
        Extracted text content

    Raises:
        FileReadError: If file cannot be read
        ImportError: If python-docx is not installed
    """
    if not DOCX_AVAILABLE:
        raise ImportError("python-docx is not installed. Install with: pip install python-docx")

    file_path = Path(file_path)
    _check_file_size(file_path)
    try:
        doc = docx.Document(str(file_path))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        text = "\n".join(paragraphs)
        logger.debug(f"Extracted {len(text)} characters from {file_path.name}")
        return text
    except Exception as e:
        raise FileReadError(f"Failed to read DOCX file {file_path}: {e}") from e


def read_pdf_file(file_path: str | Path, max_pages: int = 5) -> str:
    """Read text content from a PDF file.

    Args:
        file_path: Path to PDF file
        max_pages: Maximum pages to read

    Returns:
        Extracted text content

    Raises:
        FileReadError: If file cannot be read
        ImportError: If PyMuPDF is not installed
    """
    if not PYMUPDF_AVAILABLE:
        raise ImportError("PyMuPDF is not installed. Install with: pip install PyMuPDF")

    file_path = Path(file_path)
    _check_file_size(file_path)
    try:
        with fitz.open(file_path) as doc:
            num_pages = min(max_pages, len(doc))

            pages_text = []
            for page_num in range(num_pages):
                page = doc.load_page(page_num)
                pages_text.append(page.get_text())

            text = "\n".join(pages_text)

        logger.debug(f"Extracted {len(text)} characters from {num_pages} pages of {file_path.name}")
        return text
    except Exception as e:
        raise FileReadError(f"Failed to read PDF file {file_path}: {e}") from e


def read_spreadsheet_file(file_path: str | Path, max_rows: int = 100) -> str:
    """Read content from Excel or CSV file.

    Args:
        file_path: Path to spreadsheet file
        max_rows: Maximum rows to read

    Returns:
        String representation of data

    Raises:
        FileReadError: If file cannot be read
        ImportError: If openpyxl is not installed (for Excel files)
    """
    file_path = Path(file_path)
    _check_file_size(file_path)
    try:
        if file_path.suffix.lower() == ".csv":
            import csv

            rows = []
            with open(file_path, newline="", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i >= max_rows:
                        break
                    rows.append(",".join(row))
            text = "\n".join(rows)
            logger.debug(
                f"Extracted {len(text)} characters from {len(rows)} rows of {file_path.name}"
            )
            return text

        elif file_path.suffix.lower() in (".xlsx", ".xls"):
            if not OPENPYXL_AVAILABLE:
                raise ImportError("openpyxl is not installed. Install with: pip install openpyxl")
            import openpyxl

            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
            ws = wb.active
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= max_rows:
                    break
                # Only keep non-empty values
                row_str = ",".join(str(cell) if cell is not None else "" for cell in row)
                if row_str.strip(","):
                    rows.append(row_str)
            text = "\n".join(rows)
            logger.debug(
                f"Extracted {len(text)} characters from {len(rows)} rows of {file_path.name}"
            )
            return text

        else:
            raise FileReadError(f"Unsupported spreadsheet format: {file_path.suffix}")

    except ImportError:
        raise
    except Exception as e:
        raise FileReadError(f"Failed to read spreadsheet file {file_path}: {e}") from e


def read_presentation_file(file_path: str | Path) -> str:
    """Read text content from PowerPoint file.

    Args:
        file_path: Path to PPT/PPTX file

    Returns:
        Extracted text from all slides

    Raises:
        FileReadError: If file cannot be read
        ImportError: If python-pptx is not installed
    """
    if not PPTX_AVAILABLE:
        raise ImportError("python-pptx is not installed. Install with: pip install python-pptx")

    file_path = Path(file_path)
    _check_file_size(file_path)
    try:
        prs = Presentation(str(file_path))

        slides_text = []
        for slide_num, slide in enumerate(prs.slides, 1):
            slide_content = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_content.append(shape.text)

            if slide_content:
                slides_text.append(f"Slide {slide_num}: " + " | ".join(slide_content))

        text = "\n".join(slides_text)
        logger.debug(
            f"Extracted {len(text)} characters from {len(slides_text)} slides of {file_path.name}"
        )
        return text
    except Exception as e:
        raise FileReadError(f"Failed to read presentation file {file_path}: {e}") from e
