"""Tests for CAD file format readers."""

from pathlib import Path
from textwrap import dedent

import pytest

from file_organizer.utils.file_readers import (
    FileReadError,
    read_cad_file,
    read_dxf_file,
    read_dwg_file,
    read_iges_file,
    read_step_file,
    read_file,
)


@pytest.fixture
def sample_dxf_file(tmp_path: Path) -> Path:
    """Create a minimal valid DXF file for testing."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    dxf_path = tmp_path / "sample.dxf"

    # Create a minimal DXF document
    doc = ezdxf.new('R2010')

    # Set header variables
    doc.header['$TITLE'] = 'Test Drawing'
    doc.header['$AUTHOR'] = 'Test User'

    # Add some layers
    doc.layers.add('Layer1', color=1)
    doc.layers.add('Layer2', color=2)
    doc.layers.add('Layer3', color=3)

    # Add some entities to modelspace
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 10))
    msp.add_circle((5, 5), radius=3)
    msp.add_text('Test Text', dxfattribs={'layer': 'Layer1'})

    # Add a block
    block = doc.blocks.new('TestBlock')
    block.add_circle((0, 0), radius=1)

    # Save the document
    doc.saveas(dxf_path)

    return dxf_path


@pytest.fixture
def sample_step_file(tmp_path: Path) -> Path:
    """Create a minimal STEP file for testing."""
    step_path = tmp_path / "sample.step"

    # Minimal valid STEP file structure
    step_content = dedent("""
        ISO-10303-21;
        HEADER;
        FILE_DESCRIPTION(('Test STEP file'),'2;1');
        FILE_NAME('sample.step','2024-01-24T00:00:00',('Test User'),('Test Organization'),'Test Preprocessor','Test System','');
        FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));
        ENDSEC;
        DATA;
        #1=CARTESIAN_POINT('',(0.,0.,0.));
        #2=DIRECTION('',(0.,0.,1.));
        #3=DIRECTION('',(1.,0.,0.));
        #4=AXIS2_PLACEMENT_3D('',#1,#2,#3);
        #5=CIRCLE('',#4,10.);
        ENDSEC;
        END-ISO-10303-21;
    """).strip()

    step_path.write_text(step_content)
    return step_path


@pytest.fixture
def sample_iges_file(tmp_path: Path) -> Path:
    """Create a minimal IGES file for testing."""
    iges_path = tmp_path / "sample.iges"

    # IGES file with proper column structure (columns 1-72 data, 73 section type, 74-80 sequence)
    iges_content = (
        "Test IGES File Created for Testing                                      S      1\n"
        "1H,,1H;,                                                                S      2\n"
        ",,,3,1,1,4,1,,,,,,,,,,,,1,0;                                            G      1\n"
        "1HTest,12Htest.iges,6H1.0,8H20240124,5H12:00,1E-6,1.0,4HINCH,1,0;      G      2\n"
        "     128       1       0       0       0       0               00000001D      1\n"
        "     128       0       0       1       0                               D      2\n"
        "128,10.0,0.0,0.0;                                                      1P      1\n"
        "S      2G      2D      2P      1                                        T      1\n"
    )

    iges_path.write_text(iges_content)
    return iges_path


# ===== DXF File Tests =====

def test_read_dxf_file_basic(sample_dxf_file: Path) -> None:
    """Test basic DXF file reading."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    result = read_dxf_file(sample_dxf_file)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "DXF" in result
    assert "Layer" in result


def test_read_dxf_file_metadata(sample_dxf_file: Path) -> None:
    """Test DXF metadata extraction."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    result = read_dxf_file(sample_dxf_file)

    # Check for expected metadata
    assert "Test Drawing" in result
    assert "Test User" in result
    assert "Layer1" in result or "Layer2" in result


def test_read_dxf_file_entities(sample_dxf_file: Path) -> None:
    """Test DXF entity information extraction."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    result = read_dxf_file(sample_dxf_file)

    # Check for entity information
    assert "Entities" in result or "entities" in result.lower()


def test_read_dxf_file_max_layers(sample_dxf_file: Path) -> None:
    """Test DXF max_layers parameter."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    result = read_dxf_file(sample_dxf_file, max_layers=1)

    assert isinstance(result, str)
    assert len(result) > 0


def test_read_dxf_file_nonexistent() -> None:
    """Test reading non-existent DXF file."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    with pytest.raises(FileReadError):
        read_dxf_file("/nonexistent/file.dxf")


# ===== DWG File Tests =====

def test_read_dwg_file_fallback(tmp_path: Path) -> None:
    """Test DWG file reading fallback when ezdxf can't parse."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    # Create a fake DWG file (just to test fallback)
    dwg_path = tmp_path / "sample.dwg"
    dwg_path.write_bytes(b"AC1015DWG_HEADER_FAKE_DATA")

    result = read_dwg_file(dwg_path)

    assert isinstance(result, str)
    assert "DWG" in result
    assert "sample.dwg" in result
    assert "Size" in result


def test_read_dwg_file_nonexistent() -> None:
    """Test reading non-existent DWG file."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    result = read_dwg_file("/nonexistent/file.dwg")
    # Should return fallback information, not raise error
    assert isinstance(result, str)


# ===== STEP File Tests =====

def test_read_step_file_basic(sample_step_file: Path) -> None:
    """Test basic STEP file reading."""
    result = read_step_file(sample_step_file)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "STEP" in result
    assert "sample.step" in result


def test_read_step_file_header(sample_step_file: Path) -> None:
    """Test STEP header extraction."""
    result = read_step_file(sample_step_file)

    # Check for header information
    assert "FILE_DESCRIPTION" in result or "FILE_NAME" in result


def test_read_step_file_entity_count(sample_step_file: Path) -> None:
    """Test STEP entity counting."""
    result = read_step_file(sample_step_file)

    # Should have entity count
    assert "entity" in result.lower() or "Approximate" in result


def test_read_step_file_nonexistent() -> None:
    """Test reading non-existent STEP file."""
    with pytest.raises(FileReadError):
        read_step_file("/nonexistent/file.step")


# ===== IGES File Tests =====

def test_read_iges_file_basic(sample_iges_file: Path) -> None:
    """Test basic IGES file reading."""
    result = read_iges_file(sample_iges_file)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "IGES" in result
    assert "sample.iges" in result


def test_read_iges_file_sections(sample_iges_file: Path) -> None:
    """Test IGES section extraction."""
    result = read_iges_file(sample_iges_file)

    # Check for section information
    assert "Start Section" in result or "Global Parameters" in result


def test_read_iges_file_nonexistent() -> None:
    """Test reading non-existent IGES file."""
    with pytest.raises(FileReadError):
        read_iges_file("/nonexistent/file.iges")


# ===== CAD File Dispatcher Tests =====

def test_read_cad_file_dxf(sample_dxf_file: Path) -> None:
    """Test CAD dispatcher with DXF file."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    result = read_cad_file(sample_dxf_file)

    assert isinstance(result, str)
    assert len(result) > 0


def test_read_cad_file_step(sample_step_file: Path) -> None:
    """Test CAD dispatcher with STEP file."""
    result = read_cad_file(sample_step_file)

    assert isinstance(result, str)
    assert "STEP" in result


def test_read_cad_file_iges(sample_iges_file: Path) -> None:
    """Test CAD dispatcher with IGES file."""
    result = read_cad_file(sample_iges_file)

    assert isinstance(result, str)
    assert "IGES" in result


def test_read_cad_file_unsupported(tmp_path: Path) -> None:
    """Test CAD dispatcher with unsupported format."""
    unsupported = tmp_path / "file.xyz"
    unsupported.write_text("test")

    with pytest.raises(ValueError, match="Unsupported CAD file format"):
        read_cad_file(unsupported)


# ===== Generic read_file Integration Tests =====

def test_read_file_dxf_integration(sample_dxf_file: Path) -> None:
    """Test read_file() with DXF format."""
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")

    result = read_file(sample_dxf_file)

    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0


def test_read_file_step_integration(sample_step_file: Path) -> None:
    """Test read_file() with STEP format."""
    result = read_file(sample_step_file)

    assert result is not None
    assert isinstance(result, str)
    assert "STEP" in result


def test_read_file_iges_integration(sample_iges_file: Path) -> None:
    """Test read_file() with IGES format."""
    result = read_file(sample_iges_file)

    assert result is not None
    assert isinstance(result, str)
    assert "IGES" in result


def test_read_file_stp_extension(tmp_path: Path) -> None:
    """Test read_file() with .stp extension (STEP variant)."""
    stp_path = tmp_path / "sample.stp"

    # Minimal STEP content
    step_content = dedent("""
        ISO-10303-21;
        HEADER;
        FILE_DESCRIPTION(('Test'),'2;1');
        FILE_NAME('sample.stp','2024-01-24T00:00:00',('User'),('Org'),'','','');
        FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));
        ENDSEC;
        DATA;
        ENDSEC;
        END-ISO-10303-21;
    """).strip()

    stp_path.write_text(step_content)

    result = read_file(stp_path)

    assert result is not None
    assert "STEP" in result


def test_read_file_igs_extension(tmp_path: Path) -> None:
    """Test read_file() with .igs extension (IGES variant)."""
    igs_path = tmp_path / "sample.igs"

    # Minimal IGES content
    iges_content = (
        "Test IGES                                                                S      1\n"
        "S      1G      0D      0P      0                                        T      1\n"
    )

    igs_path.write_text(iges_content)

    result = read_file(igs_path)

    assert result is not None
    assert "IGES" in result


# ===== Error Handling Tests =====

def test_read_dxf_without_ezdxf(tmp_path: Path, monkeypatch) -> None:
    """Test DXF reading when ezdxf is not available."""
    # Temporarily make ezdxf unavailable
    import file_organizer.utils.file_readers as readers
    monkeypatch.setattr(readers, 'EZDXF_AVAILABLE', False)

    dxf_path = tmp_path / "test.dxf"
    dxf_path.write_text("fake dxf content")

    with pytest.raises(ImportError, match="ezdxf is not installed"):
        read_dxf_file(dxf_path)


def test_read_step_with_corrupted_file(tmp_path: Path) -> None:
    """Test STEP reading with corrupted file."""
    step_path = tmp_path / "corrupted.step"
    # Write invalid STEP content (missing required sections)
    step_path.write_text("INVALID STEP CONTENT")

    result = read_step_file(step_path)

    # Should still return something (basic file info)
    assert isinstance(result, str)
    assert "STEP" in result


def test_read_iges_with_short_file(tmp_path: Path) -> None:
    """Test IGES reading with very short file."""
    iges_path = tmp_path / "short.iges"
    iges_path.write_text("SHORT")

    result = read_iges_file(iges_path)

    # Should still return something
    assert isinstance(result, str)
    assert "IGES" in result
