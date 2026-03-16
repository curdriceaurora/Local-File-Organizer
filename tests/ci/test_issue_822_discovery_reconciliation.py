from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_REL = "docs/plans/review-regressions/2026-03-15-issue-822-discovery-artifact.json"
ARTIFACT_PATH = FO_ROOT / ARTIFACT_REL


def _load_artifact() -> dict[str, object]:
    assert ARTIFACT_PATH.is_file(), f"Missing #822 discovery artifact: {ARTIFACT_PATH}"
    data = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "#822 discovery artifact must decode to a JSON object"
    return data


def _split_location(location: str) -> tuple[Path, int]:
    path_str, _, line_str = location.rpartition(":")
    assert path_str and line_str.isdigit(), f"Malformed source location entry: {location!r}"
    return FO_ROOT / path_str, int(line_str)


def test_issue_822_discovery_artifact_schema_and_counts() -> None:
    artifact = _load_artifact()

    assert artifact["artifact_version"] == 1
    assert artifact["issue"] == 822
    assert artifact["generated_date"] == "2026-03-15"

    discovery = artifact["discovery"]
    assert isinstance(discovery, dict)

    swallow = discovery["silent_broad_except_pass"]
    assert isinstance(swallow, dict)
    initial_sites = swallow["initial_sites"]
    assert isinstance(initial_sites, list)
    assert swallow["initial_site_count"] == len(initial_sites)
    assert swallow["remaining_site_count"] == 0

    for location in initial_sites:
        assert isinstance(location, str)
        path, line = _split_location(location)
        assert path.is_file(), f"Discovery location points to missing file: {path}"
        total_lines = len(path.read_text(encoding="utf-8").splitlines())
        assert line > 0
        assert line <= total_lines, (
            f"Discovery location points to invalid line: {path}:{line} (max line {total_lines})"
        )

    import_defaults = discovery["import_time_derived_defaults"]
    assert isinstance(import_defaults, dict)
    sites = import_defaults["sites"]
    assert isinstance(sites, list)
    assert import_defaults["initial_site_count"] == len(sites)

    for site in sites:
        assert isinstance(site, dict)
        module = FO_ROOT / str(site["module"])
        assert module.is_file(), f"Missing import-time default module: {module}"
        test_ref = str(site["fallback_contract_test"])
        test_path_str, _, test_name = test_ref.partition("::")
        assert test_name, f"Malformed fallback contract test reference: {test_ref!r}"
        test_path = FO_ROOT / test_path_str
        assert test_path.is_file(), f"Missing fallback contract test file: {test_path}"
        source = test_path.read_text(encoding="utf-8")
        assert f"def {test_name}(" in source, (
            f"Fallback contract test reference is stale: {test_ref!r}"
        )
