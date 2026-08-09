"""Tests for the patch-liveness report plugin (issue #1681, epic #1678).

Unit tests pin the classification semantics (what counts as "accessed");
the pytester tests exercise the full hook flow end-to-end in a subprocess
so the global ``_patch.__enter__`` instrumentation never leaks into this
test session.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import types
from pathlib import Path
from unittest.mock import MagicMock, Mock, NonCallableMock, PropertyMock, create_autospec

import pytest

from tests._plugins.patch_liveness import (
    ENV_VAR,
    _install_negative_assertion_tracking,
    _test_assigned_attrs,
    _wrap_callable,
    classify_mock,
)

pytest_plugins = ["pytester"]

_PLUGIN_SOURCE = Path(__file__).resolve().parents[3] / "tests" / "_plugins" / "patch_liveness.py"


def _class_with(**attrs: object) -> type:
    """Build a throwaway class carrying *attrs* in its class body.

    Binding tests need an attribute set on a class, but assigning one
    after the fact (``Subject.method = ...``) is a global-state mutation
    the environment-leakage rail flags — correctly in general, since it
    cannot tell this ``Subject`` never escapes the test. Building the
    class with the attribute already in place sidesteps the mutation
    instead of suppressing the warning.
    """
    return type("Subject", (), attrs)


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
class TestClassifyMockKnownLimitations:
    """Documented blind spots in access counting.

    These are not aspirations — they are the current, verified behaviour.
    They exist because ``classify_mock`` infers access from ``mock_calls``
    and ``_mock_children``, both of which are populated by ``__getattr__``
    and ``__call__``. An attribute the *test* assigns lands in the mock's
    ``__dict__``, so a later read by the code under test goes straight there
    and is never observed.
    """

    def test_preset_attribute_makes_liveness_undecidable(self) -> None:
        """``mock.attr = v`` then a read must NOT be reported as dead.

        This is the ``mock_sys.platform = "darwin"`` shape. The read
        resolves from the instance ``__dict__`` and is invisible to us, so
        the honest answer is "undecidable" — reporting dead here produced
        real false positives during wave-B triage.
        """
        mock = MagicMock()
        mock.ITEM_DOCUMENT = 9  # the test pre-sets it
        assert mock.ITEM_DOCUMENT == 9  # the code under test reads it

        assert classify_mock(mock) == ("undecidable", 0)

    def test_untouched_mock_with_no_assigned_attrs_is_dead(self) -> None:
        """A mock nothing touched at all is still unambiguously dead."""
        assert classify_mock(MagicMock()) == ("dead", 0)

    def test_attribute_read_without_preset_is_live(self) -> None:
        """The same read IS observed when the test does not pre-set it."""
        mock = MagicMock()
        _ = mock.SOME_CONSTANT

        status, count = classify_mock(mock)
        assert status == "live"
        assert count == 1


@pytest.mark.unit
class TestNegativeAssertionTracking:
    """`assert_not_called()` makes deadness the contract, not a defect.

    The tracking is installed process-wide by ``pytest_configure``, so
    these tests install and remove it around themselves rather than
    relying on the ambient session state.
    """

    @pytest.fixture
    def tracking(self):
        originals = _install_negative_assertion_tracking()
        yield
        for name, original in originals.items():
            setattr(NonCallableMock, name, original)

    def test_asserting_not_called_is_not_decay(self, tracking):
        """The whole point: an unreached-by-design patch is not a finding."""
        mock = MagicMock()

        assert classify_mock(mock) == ("dead", 0), "premise: untouched mock reads dead"
        mock.assert_not_called()
        assert classify_mock(mock) == ("asserted", 0)

    def test_a_failing_assertion_does_not_earn_the_flag(self, tracking):
        """Only a *passing* assertion is a contract; a failing one is a bug."""
        mock = MagicMock()
        mock("reached")

        with pytest.raises(AssertionError):
            mock.assert_not_called()

        assert classify_mock(mock)[0] == "live", "a called mock must stay live"

    def test_flag_does_not_make_the_mock_look_test_configured(self, tracking):
        """The marker must not be mistaken for a test-assigned attribute.

        ``_test_assigned_attrs`` drives the ``undecidable`` verdict; a
        non-underscore marker would silently reclassify every asserted
        mock and mask the very rows this is meant to resolve.
        """
        mock = MagicMock()
        mock.assert_not_called()

        assert _test_assigned_attrs(mock) == []

    def test_probing_the_flag_does_not_itself_register_an_access(self, tracking):
        """Regression: reading the marker with `getattr` broke everything.

        ``MagicMock`` manufactures a child for any unknown attribute, so
        ``getattr(mock, "_fo_asserted_not_called", False)`` returned a
        truthy child mock *and* added to ``_mock_children`` — every mock
        in the suite read as asserted. The check must go through
        ``__dict__``.
        """
        mock = MagicMock()

        assert classify_mock(mock) == ("dead", 0)
        assert classify_mock(mock) == ("dead", 0), "classifying twice changed the verdict"

    def test_install_returns_the_originals_so_it_can_be_undone(self):
        """`pytest_unconfigure` restores from this; without it the wrap leaks.

        Asserted on the return value rather than by observing an
        "uninstrumented" mock, because when the plugin itself is enabled
        there is no uninstrumented state to observe.
        """
        originals = _install_negative_assertion_tracking()
        try:
            assert "assert_not_called" in originals
            assert all(callable(f) for f in originals.values())
        finally:
            for name, original in originals.items():
                setattr(NonCallableMock, name, original)


@pytest.mark.unit
class TestWrapCallable:
    """Making plain-function replacements observable (issue #1719).

    ``_wrap_callable`` trades a fake function for a recording proxy plus
    a probe mock. Every test here is really one question: does the proxy
    behave *exactly* like what it replaced?
    """

    def test_plain_function_becomes_observable(self):
        """The probe records a call the bare function would have hidden."""
        wrapped = _wrap_callable(lambda x: x * 2)
        assert wrapped is not None
        recorder, probe = wrapped

        assert classify_mock(probe) == ("dead", 0)
        assert recorder(21) == 42
        assert classify_mock(probe)[0] == "live"
        probe.assert_called_once_with(21)

    def test_uncalled_function_is_dead_not_untracked(self):
        """The point of the whole exercise: a never-called fake is decay."""
        _, probe = _wrap_callable(lambda: None)

        assert classify_mock(probe) == ("dead", 0)

    def test_wrapper_binds_as_a_method_like_the_function_it_replaced(self):
        """The descriptor contract, which a MagicMock would silently break.

        A function set on a class binds: ``inst.meth()`` passes ``self``.
        The wrapper must too, or the fake is called with the wrong
        arguments. This is why the wrapper is a function and not a mock.
        """

        def fake_method(self, value):
            return f"{type(self).__name__}:{value}"

        recorder, probe = _wrap_callable(fake_method)
        Subject = _class_with(describe=recorder)

        instance = Subject()
        assert instance.describe("x") == "Subject:x"
        # `self` reached both the probe and the wrapped function.
        assert probe.call_args.args == (instance, "x")

    def test_a_magicmock_would_have_dropped_self(self):
        """Counterfactual pinning the reason for the design.

        If this ever starts passing with `self` present, ``MagicMock``
        gained the descriptor protocol and ``_wrap_callable`` could be
        simplified. Until then, it documents the trap.
        """

        Subject = _class_with(describe=MagicMock())
        Subject().describe("x")

        assert Subject.describe.call_args.args == ("x",), "self was passed after all"

    @pytest.mark.parametrize(
        ("replacement", "why"),
        [
            (ValueError, "exception classes must stay usable in `except`"),
            (dict, "classes must stay usable in isinstance/issubclass"),
            (len, "builtins do not bind when set on a class"),
            (functools.partial(int, "0"), "partials do not bind either"),
            ("a string", "constants are not callable at all"),
            (None, "patch(..., None) is a sentinel, not a callable"),
        ],
    )
    def test_unsafe_shapes_are_left_alone(self, replacement, why):
        """Anything whose binding or protocol we would change is untouched."""
        assert _wrap_callable(replacement) is None, why

    def test_bound_method_is_left_alone(self):
        """A bound method already carries its receiver; wrapping adds a second."""

        class Holder:
            def method(self):
                return "held"

        assert _wrap_callable(Holder().method) is None

    def test_autospec_function_is_classified_through_its_mock(self):
        """An autospec'd function is observable without being a Mock itself."""
        called = create_autospec(lambda path: True)
        uncalled = create_autospec(lambda path: True)
        called("any-argument")

        assert classify_mock(called)[0] == "live"
        assert classify_mock(uncalled) == ("dead", 0)

    def test_reading_mock_attribute_does_not_manufacture_an_access(self):
        """The `.mock` lookup must not itself register on a real Mock.

        ``MagicMock().mock`` auto-creates a child, which would read as an
        access and turn every dead mock live. Guarding on "not already a
        Mock" is what prevents that.
        """
        assert classify_mock(MagicMock()) == ("dead", 0)

    def test_staticmethod_keeps_its_non_binding_semantics(self):
        """`staticmethod(lambda: v)` must not start receiving `self`."""

        recorder, probe = _wrap_callable(staticmethod(lambda: "value"))
        Subject = _class_with(compute=recorder)

        assert Subject().compute() == "value"
        assert probe.call_args.args == (), "self leaked into a staticmethod"

    def test_classmethod_still_receives_cls(self):
        """The mirror case: `cls` must still arrive, and only once."""

        recorder, probe = _wrap_callable(classmethod(lambda cls: cls.__name__))
        Subject = _class_with(name_of=recorder)

        assert Subject().name_of() == "Subject"
        assert probe.call_args.args == (Subject,)

    def test_autospec_function_is_left_alone(self):
        """`autospec` yields a real function that is already observable.

        Regression: wrapping it handed the test a copy, so a passing
        ``assert_called_once()`` was followed by ``call_args is None``
        (tests/models/test_model_manager.py, ``Path.is_dir`` autospec).
        """
        autospecced = create_autospec(lambda path: True)

        assert type(autospecced) is types.FunctionType, "premise: autospec makes a function"
        assert _wrap_callable(autospecced) is None

    def test_wrapper_preserves_identity_metadata(self):
        """`functools.wraps`, so code reading __name__ off the fake still works."""

        def fake_initialize():
            """Docstring the code may read."""

        recorder, _ = _wrap_callable(fake_initialize)

        assert recorder.__name__ == "fake_initialize"
        assert recorder.__doc__ == "Docstring the code may read."

    def test_async_function_stays_a_coroutine_function(self):
        """An async fake must not become sync, or `iscoroutinefunction` lies."""

        async def fake_async(value):
            return value + 1

        recorder, probe = _wrap_callable(fake_async)

        assert inspect.iscoroutinefunction(recorder)
        assert asyncio.run(recorder(1)) == 2
        probe.assert_called_once_with(1)

    def test_exceptions_propagate_unchanged(self):
        """The proxy must not swallow or re-wrap what the fake raises."""

        def fake_that_raises():
            raise RuntimeError("boom")

        recorder, probe = _wrap_callable(fake_that_raises)

        with pytest.raises(RuntimeError, match="boom"):
            recorder()
        assert classify_mock(probe)[0] == "live"


@pytest.mark.unit
class TestReportFlow:
    """End-to-end: hooks record dead patches and write the JSONL report."""

    def _install_plugin(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest(_PLUGIN_SOURCE.read_text())

    def test_dead_patch_is_reported_and_suite_stays_green(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dead patch appears in the report; report mode never fails tests."""
        self._install_plugin(pytester)
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

    def test_inherited_worker_env_does_not_suffix_the_report(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A nested session must not be mistaken for an xdist worker.

        ``PYTEST_XDIST_WORKER`` is inherited by every subprocess a test
        spawns. The plugin used to read it at sessionfinish, so whenever the
        outer suite ran under xdist this nested session wrote its report to
        ``<path>.gwN`` and the caller — which only knows ``<path>`` — saw
        nothing. The worker id must come from pytest's own config instead.
        """
        self._install_plugin(pytester)
        pytester.makepyfile(
            target_mod="""
            def helper():
                return "real"

            def entry():
                return "no helper call"
            """,
            test_sample="""
            from unittest.mock import patch
            import target_mod

            @patch("target_mod.helper")
            def test_dead_patch(mock_helper):
                assert target_mod.entry() == "no helper call"
            """,
        )
        report = pytester.path / "liveness.jsonl"
        monkeypatch.setenv(ENV_VAR, str(report))
        # Pretend an xdist worker spawned us, which is exactly what happens
        # when the outer suite runs with -n auto.
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw7")

        result = pytester.runpytest_subprocess("-p", "no:randomly")
        result.assert_outcomes(passed=1)

        assert report.exists(), "report went to a worker-suffixed path"
        assert not (pytester.path / "liveness.jsonl.gw7").exists()

    def test_missing_report_directory_is_created_not_fatal(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A report path under a non-existent directory must not fail the run.

        The plugin is report-only. Pointing it at ``<tmp>/nested/dir/x.jsonl``
        used to raise out of ``pytest_sessionfinish`` and take the whole
        session down — turning reporting into an availability hazard.
        """
        self._install_plugin(pytester)
        pytester.makepyfile(
            target_mod="""
            def helper():
                return "real"

            def entry():
                return "no helper call"
            """,
            test_sample="""
            from unittest.mock import patch
            import target_mod

            @patch("target_mod.helper")
            def test_dead_patch(mock_helper):
                assert target_mod.entry() == "no helper call"
            """,
        )
        report = pytester.path / "does" / "not" / "exist" / "liveness.jsonl"
        monkeypatch.setenv(ENV_VAR, str(report))

        result = pytester.runpytest_subprocess("-p", "no:randomly")

        result.assert_outcomes(passed=1)
        assert report.exists()

    def test_disabled_without_env_var(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without the env var, the plugin is inert: no report, no failures."""
        self._install_plugin(pytester)
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
        self._install_plugin(pytester)
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
