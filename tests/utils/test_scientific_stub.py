"""Tests for the scientific-reader stubs (utils/readers/_scientific_stub.py)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from file_organizer.utils.readers._scientific_stub import (
    read_hdf5_file,
    read_mat_file,
    read_netcdf_file,
)

INSTALL_HINT = "install local-file-organizer[scientific]"


@pytest.mark.unit
class TestScientificStubs:
    """Each stub returns an install-hint string naming its format."""

    def test_hdf5_stub_names_format_and_hints_install(self) -> None:
        message = read_hdf5_file("data.h5")
        assert message.startswith("HDF5:")
        assert INSTALL_HINT in message

    def test_mat_stub_names_format_and_hints_install(self) -> None:
        message = read_mat_file(Path("data.mat"))
        assert message.startswith("MAT:")
        assert INSTALL_HINT in message

    def test_netcdf_stub_names_format_and_hints_install(self) -> None:
        message = read_netcdf_file("data.nc")
        assert message.startswith("NetCDF:")
        assert INSTALL_HINT in message

    def test_stubs_accept_fileobj_keyword(self) -> None:
        # The real readers accept an open binary stream; the stubs must
        # keep the same signature so callers don't need to special-case.
        fileobj = io.BytesIO(b"")
        assert INSTALL_HINT in read_hdf5_file(fileobj=fileobj)
        assert INSTALL_HINT in read_mat_file(fileobj=fileobj)
        assert INSTALL_HINT in read_netcdf_file(fileobj=fileobj)

    def test_hdf5_stub_accepts_max_datasets(self) -> None:
        assert INSTALL_HINT in read_hdf5_file("data.h5", max_datasets=5)
