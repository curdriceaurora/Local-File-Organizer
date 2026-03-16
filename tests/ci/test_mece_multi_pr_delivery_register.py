from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
REGISTER_REL = "docs/plans/2026-03-16-mece-multi-pr-delivery-register.md"
REGISTER_PATH = FO_ROOT / REGISTER_REL
EXPECTED_ISSUES = {706, 715, 719, 720, 723, 727, 816, 819, 820}
EXPECTED_PRIORITIES = {"P0", "P1", "P2", "P3"}
EXPECTED_STREAM_VALUES: dict[str, dict[str, object]] = {
    "PR-A": {"priority": "P0", "wave": 1, "quick_win": True},
    "PR-B": {"priority": "P1", "wave": 2, "quick_win": False},
    "PR-C": {"priority": "P1", "wave": 2, "quick_win": False},
    "PR-D": {"priority": "P1", "wave": 1, "quick_win": False},
    "PR-E": {"priority": "P2", "wave": 1, "quick_win": True},
    "PR-F": {"priority": "P3", "wave": 1, "quick_win": False},
    "PR-G": {"priority": "P1", "wave": 3, "quick_win": False},
}


def _extract_metadata(text: str) -> dict[str, object]:
    match = re.search(
        r"<!-- MECE_MULTI_PR_DELIVERY_METADATA_START -->\s*```json\s*(.*?)\s*```"
        r"\s*<!-- MECE_MULTI_PR_DELIVERY_METADATA_END -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, "MECE delivery metadata block is missing or malformed"
    metadata = json.loads(match.group(1))
    assert isinstance(metadata, dict), "MECE delivery metadata must decode to a JSON object"
    return metadata


def _read_required(path: Path) -> str:
    assert path.is_file(), f"Expected file does not exist: {path}"
    return path.read_text(encoding="utf-8")


def test_delivery_register_has_mece_partition_and_valid_wave_plan() -> None:
    metadata = _extract_metadata(_read_required(REGISTER_PATH))

    assert metadata["format_version"] == 1
    assert metadata["pr_stream_count"] == 7

    issues_in_scope = {int(item) for item in metadata["issues_in_scope"]}
    assert issues_in_scope == EXPECTED_ISSUES

    streams = metadata["pr_streams"]
    assert isinstance(streams, list)
    assert len(streams) == 7

    stream_ids: set[str] = set()
    covered_issues: list[int] = []

    for stream in streams:
        assert isinstance(stream, dict)
        stream_id = str(stream["id"])
        stream_ids.add(stream_id)
        expected = EXPECTED_STREAM_VALUES.get(stream_id)
        assert expected is not None, f"Unexpected stream id in metadata: {stream_id}"

        assert stream["priority"] in EXPECTED_PRIORITIES
        assert stream["priority"] == expected["priority"]
        assert isinstance(stream["quick_win"], bool)
        assert stream["quick_win"] is expected["quick_win"]
        assert int(stream["wave"]) in {1, 2, 3}
        assert int(stream["wave"]) == expected["wave"]

        issues = stream["issues"]
        assert isinstance(issues, list)
        for issue in issues:
            covered_issues.append(int(issue))

    assert stream_ids == {"PR-A", "PR-B", "PR-C", "PR-D", "PR-E", "PR-F", "PR-G"}
    counts = Counter(covered_issues)
    assert set(counts) == EXPECTED_ISSUES
    assert counts.most_common(1)[0][1] == 1, "Each issue must map to exactly one PR stream"

    wave_order = metadata["wave_order"]
    assert wave_order == {
        "1": ["PR-A", "PR-D", "PR-E", "PR-F"],
        "2": ["PR-B", "PR-C"],
        "3": ["PR-G"],
    }


def test_register_reconciliation_claims_match_repository_evidence() -> None:
    metadata = _extract_metadata(_read_required(REGISTER_PATH))
    evidence = metadata["evidence_paths"]
    assert isinstance(evidence, dict)

    provider_registry_path = FO_ROOT / str(evidence["provider_registry"])
    provider_env_path = FO_ROOT / str(evidence["provider_env"])
    llama_model_path = FO_ROOT / str(evidence["llama_model"])
    ci_workflow_path = FO_ROOT / str(evidence["ci_workflow"])

    provider_registry_text = _read_required(provider_registry_path)
    provider_env_text = _read_required(provider_env_path)
    _read_required(llama_model_path)
    ci_workflow_text = _read_required(ci_workflow_path)

    assert '"llama_cpp"' in provider_registry_text
    assert "_llama_cpp_text_factory" in provider_registry_text
    assert "FO_PROVIDER=llama_cpp" in provider_env_text
    assert 'Literal["ollama", "openai", "llama_cpp", "mlx"]' in provider_env_text

    assert "name: Test non-benchmark suite" in ci_workflow_text
    assert 'pytest tests/ -m "not benchmark"' in ci_workflow_text
    assert "name: Test benchmark-only suite (no xdist)" in ci_workflow_text
    assert "pytest tests/ -m benchmark --benchmark-only" in ci_workflow_text
    assert "dorny/paths-filter" in ci_workflow_text
    assert "needs.changes.outputs.benchmark" in ci_workflow_text

    closeout_assertions = metadata["closeout_assertions"]
    assert closeout_assertions == {
        "issues_reconciled_now": [723, 816],
        "epic_tracking_issue": 706,
        "epic_bottleneck_issue": 715,
    }
