"""Shared fixtures for the cross-surface conformance scaffold (#1605)."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest

from file_organizer.core.organize_options import OrganizeOptions, OrganizeRequest
from tests.conformance.corpus import CorpusCase, get_case, materialize_case
from tests.conformance.driver import (
    AsyncPythonSDKConformanceDriver,
    CLIConformanceDriver,
    DirectServiceDriver,
    OrganizationConformanceDriver,
    PythonSDKConformanceDriver,
    RemoteCLIConformanceDriver,
    RESTConformanceDriver,
    TUIConformanceDriver,
    TypeScriptSDKConformanceDriver,
    WebFormConformanceDriver,
)


@dataclass
class ConformanceContext:
    """A staged conformance workspace bound to one driver instance."""

    input_root: Path
    output_root: Path
    driver: OrganizationConformanceDriver

    def stage(self, case_id: str) -> CorpusCase:
        """Materialize the corpus case under this context's roots."""
        case = get_case(case_id)
        materialize_case(case, self.input_root, self.output_root)
        return case

    def request(self, **option_overrides: object) -> OrganizeRequest:
        """Build a canonical request for the staged roots."""
        return OrganizeRequest(
            self.input_root,
            self.output_root,
            OrganizeOptions(**option_overrides),  # type: ignore[arg-type]
        )


@pytest.fixture(
    params=(
        DirectServiceDriver,
        CLIConformanceDriver,
        RESTConformanceDriver,
        PythonSDKConformanceDriver,
        RemoteCLIConformanceDriver,
        AsyncPythonSDKConformanceDriver,
        WebFormConformanceDriver,
        TUIConformanceDriver,
        TypeScriptSDKConformanceDriver,
    ),
    ids=(
        "direct",
        "cli",
        "rest",
        "python-sdk",
        "fo-api",
        "python-async-sdk",
        "web-form-adapter",
        "tui-workspace-adapter",
        "typescript-sdk",
    ),
)
def conformance(
    tmp_path: Path, request: pytest.FixtureRequest
) -> Generator[ConformanceContext, None, None]:
    """Run the golden corpus against the oracle and each migrated adapter."""
    driver_type = request.param
    driver = driver_type(tmp_path / "workspace")
    yield ConformanceContext(
        input_root=tmp_path / "input",
        output_root=tmp_path / "output",
        driver=driver,
    )
    if hasattr(driver, "close"):
        driver.close()
