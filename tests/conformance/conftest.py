"""Shared fixtures for the cross-surface conformance scaffold (#1605)."""

from __future__ import annotations

from collections.abc import Callable, Generator
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


def _build_conformance_context(
    tmp_path: Path, driver_type: Callable[[Path], OrganizationConformanceDriver]
) -> Generator[ConformanceContext, None, None]:
    """Shared setup/teardown for the ``conformance`` and ``conformance_tagging`` fixtures."""
    driver = driver_type(tmp_path / "workspace")
    yield ConformanceContext(
        input_root=tmp_path / "input",
        output_root=tmp_path / "output",
        driver=driver,
    )
    if hasattr(driver, "close"):
        driver.close()


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
    yield from _build_conformance_context(tmp_path, request.param)


@pytest.fixture(
    params=(
        DirectServiceDriver,
        CLIConformanceDriver,
        RESTConformanceDriver,
        PythonSDKConformanceDriver,
        RemoteCLIConformanceDriver,
        AsyncPythonSDKConformanceDriver,
        TypeScriptSDKConformanceDriver,
    ),
    ids=(
        "direct",
        "cli",
        "rest",
        "python-sdk",
        "fo-api",
        "python-async-sdk",
        "typescript-sdk",
    ),
)
def conformance_tagging(
    tmp_path: Path, request: pytest.FixtureRequest
) -> Generator[ConformanceContext, None, None]:
    """Like ``conformance``, scoped to the 7 surfaces that expose tag controls.

    ``web-form-adapter`` and ``tui-workspace-adapter`` are excluded: neither
    surface's option-mapping layer has UI-facing fields for
    generate_tags/tag_style/tag_prompt yet (the Web form's
    ``_option_form_fields()`` in this driver module, for one, doesn't
    serialize them), so a non-default value passed through either silently
    resets to the domain default on the round trip -- not a real conformance
    gap, just an unbuilt control surface (#1764). Default-value parity for
    these two still runs via the ``conformance`` fixture above, since tagging
    off behaves identically everywhere.
    """
    yield from _build_conformance_context(tmp_path, request.param)
