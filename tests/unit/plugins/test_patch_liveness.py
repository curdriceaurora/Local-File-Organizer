"""Tests for the patch-liveness report plugin (issue #1681, epic #1678).

Unit tests pin the classification semantics (what counts as "accessed");
the pytester tests exercise the full hook flow end-to-end in a subprocess
so the global ``_patch.__enter__`` instrumentation never leaks into this
test session.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, PropertyMock

import pytest

from tests._plugins.patch_liveness import ENV_VAR, classify_mock

pytest_plugins = ["pytester"]

_PLUGIN_SOURCE = Path(__file__).resolve().parents[3] / "tests" / "_plugins" / "patch_liveness.py"


@pytest.mark.unit
class TestClassifyMock:
    """Classification semantics: what counts as an access."""

    def test_fresh_mock_is_dead(self):
        """A mock that nothing touched has zero accesses."""
        status, count = classify_mock(MagicMock())
        assert status == "dead"
        assert count == 0

    def test_called_mock_is_live(self):
        """Calling the mock is an access."""
        m = MagicMock()
        m("arg")
        status, count = classify_mock(m)
        assert status == "live"
        assert count >= 1

    def test_method_called_mock_is_live(self):
        """Calling a method on the mock is an access."""
        m = MagicMock()
        m.generate("prompt")
        status, count = classify_mock(m)
        assert status == "live"
        assert count >= 1

    def test_attribute_read_only_is_live(self):
        """Reading an attribute (no call) still counts as an access."""
        m = MagicMock()
        _ = m.some_attribute
        status, count = classify_mock(m)
        assert status == "live"
        assert count >= 1

    def test_property_mock_read_is_live(self):
        """A PropertyMock records property reads as calls on itself."""
        pm = PropertyMock(return_value="value")
        pm()  # what a property read triggers
        status, count = classify_mock(pm)
        assert status == "live"
        assert count >= 1

    def test_configured_but_untouched_mock_is_dead(self):
        """Test-side configuration (return_value/side_effect) is NOT an access.

        This is the candidate-1 decay pattern from #1678: a test configures
        a mock the code under test never reaches. Configuration must not
        mask deadness.
        """
        m = MagicMock()
        m.return_value = "configured"
        m.side_effect = None
        status, count = classify_mock(m)
        assert status == "dead"
        assert count == 0

    def test_spec_mock_attribute_access_is_live(self):
        """Access through a spec'd attribute counts."""

        class Thing:
            def method(self) -> None: ...

        m = Mock(spec=Thing)
        m.method()
        status, count = classify_mock(m)
        assert status == "live"
        assert count >= 1

    def test_non_mock_replacement_is_untracked(self):
        """Plain-value patches (e.g. patch(..., None)) cannot be tracked."""
        status, count = classify_mock(None)
        assert status == "untracked"
        assert count is None

    def test_non_mock_string_replacement_is_untracked(self):
        """Any non-mock replacement object is untracked, not dead."""
        status, count = classify_mock("a plain value")
        assert status == "untracked"
        assert count is None


@pytest.mark.unit
class TestReportFlow:
    """End-to-end: hooks record dead patches and write the JSONL report."""

    def _install_plugin(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch | None = None
    ) -> None:
        if monkeypatch is not None:
            monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        pytester.makeconftest(_PLUGIN_SOURCE.read_text())

    def test_dead_patch_is_reported_and_suite_stays_green(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dead patch appears in the report; report mode never fails tests."""
        self._install_plugin(pytester, monkeypatch)
        pytester.makepyfile(
            target_mod="""
            def helper():
                return "real"

            CONSTANT = "real-constant"

            def entry():
                return "no helper call"
            """,
            test_sample="""
            from unittest.mock import patch
            import target_mod

            @patch("target_mod.helper")
            def test_dead_patch(mock_helper):
                assert target_mod.entry() == "no helper call"

            @patch("target_mod.helper")
            def test_live_patch(mock_helper):
                mock_helper.return_value = "mocked"
                assert target_mod.helper() == "mocked"

            @patch("target_mod.CONSTANT", None)
            def test_non_mock_patch():
                assert target_mod.CONSTANT is None
            """,
        )
        report = pytester.path / "liveness.jsonl"
        monkeypatch.setenv(ENV_VAR, str(report))

        result = pytester.runpytest_subprocess("-p", "no:randomly")
        result.assert_outcomes(passed=3)

        assert report.exists(), "report file was not written"
        entries = [json.loads(line) for line in report.read_text().splitlines()]

        dead = [e for e in entries if e["status"] == "dead"]
        assert len(dead) == 1
        assert "test_dead_patch" in dead[0]["nodeid"]
        assert "helper" in dead[0]["target"]
        assert dead[0]["access_count"] == 0
        assert dead[0]["file"].endswith("test_sample.py")
        assert isinstance(dead[0]["line"], int)

        untracked = [e for e in entries if e["status"] == "untracked"]
        assert len(untracked) == 1
        assert "test_non_mock_patch" in untracked[0]["nodeid"]

        # The live patch must not be reported at all
        assert not any("test_live_patch" in e["nodeid"] for e in entries)

    def test_disabled_without_env_var(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without the env var, the plugin is inert: no report, no failures."""
        self._install_plugin(pytester, monkeypatch)
        pytester.makepyfile(
            test_sample="""
            from unittest.mock import patch

            @patch("json.dumps")
            def test_dead_patch(mock_dumps):
                assert True
            """
        )
        monkeypatch.delenv(ENV_VAR, raising=False)

        result = pytester.runpytest_subprocess("-p", "no:randomly")
        result.assert_outcomes(passed=1)
        assert not (pytester.path / "liveness.jsonl").exists()

    def test_context_manager_patches_are_tracked(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`with patch(...)` blocks are tracked, not just decorators."""
        self._install_plugin(pytester, monkeypatch)
        pytester.makepyfile(
            test_sample="""
            from unittest.mock import patch

            def test_dead_with_block():
                with patch("json.dumps") as mock_dumps:
                    assert True
            """
        )
        report = pytester.path / "liveness.jsonl"
        monkeypatch.setenv(ENV_VAR, str(report))

        result = pytester.runpytest_subprocess("-p", "no:randomly")
        result.assert_outcomes(passed=1)

        entries = [json.loads(line) for line in report.read_text().splitlines()]
        assert any(e["status"] == "dead" and "test_dead_with_block" in e["nodeid"] for e in entries)

    def test_inherited_xdist_worker_env_var_ignored_in_subprocess(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Inherited PYTEST_XDIST_WORKER env var in non-xdist pytester session does not suffix report file."""
        self._install_plugin(pytester)
        pytester.makepyfile(
            test_sample="""
            from unittest.mock import patch

            def test_dead():
                with patch("json.dumps"):
                    assert True
            """
        )
        report = pytester.path / "liveness.jsonl"
        monkeypatch.setenv(ENV_VAR, str(report))
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")

        result = pytester.runpytest_subprocess("-p", "no:randomly")
        result.assert_outcomes(passed=1)

        assert report.exists(), "report file without worker suffix should be written"
        assert not (pytester.path / "liveness.jsonl.gw0").exists()
