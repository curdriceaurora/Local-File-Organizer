"""Tests for the advisory test-environment-leakage CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_test_environment_leakage as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _write(tmp_path: Path, source: str) -> Path:
    src = tmp_path / "subject.py"
    src.write_text(source, encoding="utf-8")
    return src


def test_flags_direct_class_attribute_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "class Target:\n"
        "    enabled = False\n\n"
        "def test_leaks_class_state():\n"
        "    Target.enabled = True\n",
    )

    violations = checker.check_file(src)

    assert len(violations) == 1
    assert "class/global attribute mutation" in violations[0][1]


def test_flags_imported_module_attribute_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import package.config as config_module\n\n"
        "def test_leaks_module_state():\n"
        "    config_module._config = object()\n",
    )

    violations = checker.check_file(src)

    assert len(violations) == 1
    assert "class/global attribute mutation" in violations[0][1]


def test_allows_instance_and_mock_attribute_setup(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "from unittest.mock import Mock\n\n"
        "def test_plain_object_setup():\n"
        "    user = Mock()\n"
        "    user.is_active = False\n"
        "    client = Mock()\n"
        "    client.get.return_value = 'ok'\n",
    )

    assert checker.check_file(src) == []


def test_flags_sys_modules_assignment_without_patch_dict(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import sys\n\n"
        "def test_leaks_import_state():\n"
        "    sys.modules['optional_dep'] = object()\n",
    )

    violations = checker.check_file(src)

    assert len(violations) == 1
    assert "sys.modules" in violations[0][1]


def test_flags_fixture_yield_cleanup_that_is_not_exception_safe(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import pytest\n\n"
        "class Target:\n"
        "    value = 'old'\n\n"
        "@pytest.fixture\n"
        "def leaky_fixture():\n"
        "    Target.value = 'new'\n"
        "    yield\n"
        "    Target.value = 'old'\n",
    )

    violations = checker.check_file(src)

    assert len(violations) == 1
    assert any("fixture mutates shared state before yield" in msg for _, msg, _ in violations)


def test_allows_try_finally_restoration_around_class_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "class Target:\n"
        "    value = 'old'\n\n"
        "def test_scoped_mutation():\n"
        "    try:\n"
        "        Target.value = 'new'\n"
        "    finally:\n"
        "        Target.value = 'old'\n",
    )

    assert checker.check_file(src) == []


def test_allows_immediate_try_finally_restoration_after_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import sys\n"
        "from io import StringIO\n\n"
        "def test_stdout_capture():\n"
        "    old_stdout = sys.stdout\n"
        "    sys.stdout = StringIO()\n"
        "    try:\n"
        "        assert sys.stdout.getvalue() == ''\n"
        "    finally:\n"
        "        sys.stdout = old_stdout\n",
    )

    assert checker.check_file(src) == []


def test_allows_multiple_setup_mutations_restored_by_following_finally(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "class First:\n"
        "    value = 'old'\n\n"
        "class Second:\n"
        "    value = 'old'\n\n"
        "def test_multi_setup_restore():\n"
        "    First.value = 'new'\n"
        "    Second.value = 'new'\n"
        "    try:\n"
        "        assert First.value == 'new'\n"
        "    finally:\n"
        "        First.value = 'old'\n"
        "        Second.value = 'old'\n",
    )

    assert checker.check_file(src) == []


def test_allows_patch_dict_for_sys_modules(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import sys\n"
        "from unittest.mock import patch\n\n"
        "def test_scoped_import_state():\n"
        "    with patch.dict(sys.modules, {'optional_dep': object()}):\n"
        "        assert 'optional_dep' in sys.modules\n",
    )

    assert checker.check_file(src) == []


def test_unrelated_patch_dict_does_not_hide_sys_modules_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import os\n"
        "import sys\n"
        "from unittest.mock import patch\n\n"
        "def test_unrelated_patch_dict():\n"
        "    with patch.dict(os.environ, {'FLAG': '1'}):\n"
        "        sys.modules['optional_dep'] = object()\n",
    )

    violations = checker.check_file(src)

    assert len(violations) == 1
    assert "sys.modules" in violations[0][1]


def test_allows_nested_patch_object_contexts(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "from unittest.mock import patch\n\n"
        "class Target:\n"
        "    left = False\n"
        "    right = False\n\n"
        "def test_nested_patch_contexts():\n"
        "    with patch.object(Target, 'left', True):\n"
        "        with patch.object(Target, 'right', True):\n"
        "            assert Target.left and Target.right\n",
    )

    assert checker.check_file(src) == []


def test_allows_patch_decorators(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import sys\n"
        "from unittest.mock import patch\n\n"
        "class Target:\n"
        "    enabled = False\n\n"
        "@patch.object(Target, 'enabled', True)\n"
        "@patch.dict(sys.modules, {'optional_dep': object()})\n"
        "def test_patch_decorators():\n"
        "    Target.enabled = False\n"
        "    sys.modules['optional_dep'] = object()\n",
    )

    assert checker.check_file(src) == []


def test_unrelated_patch_object_does_not_hide_direct_class_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "from unittest.mock import patch\n\n"
        "class Patched:\n"
        "    enabled = False\n\n"
        "class Leaky:\n"
        "    enabled = False\n\n"
        "def test_unrelated_patch_context():\n"
        "    with patch.object(Patched, 'enabled', True):\n"
        "        Leaky.enabled = True\n",
    )

    violations = checker.check_file(src)

    assert len(violations) == 1
    assert "Leaky.enabled" in violations[0][2]


def test_allows_monkeypatch_setattr_and_setitem(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import sys\n\n"
        "class Target:\n"
        "    enabled = False\n\n"
        "def test_monkeypatch_is_scoped(monkeypatch):\n"
        "    monkeypatch.setattr(Target, 'enabled', True)\n"
        "    monkeypatch.setitem(sys.modules, 'optional_dep', object())\n",
    )

    assert checker.check_file(src) == []


def test_allows_fixture_finalizer_registered_before_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import pytest\n\n"
        "class Target:\n"
        "    value = 'old'\n\n"
        "@pytest.fixture\n"
        "def scoped_fixture(request):\n"
        "    request.addfinalizer(lambda: setattr(Target, 'value', 'old'))\n"
        "    Target.value = 'new'\n"
        "    yield\n",
    )

    assert checker.check_file(src) == []


def test_unrelated_fixture_finalizer_does_not_hide_later_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import pytest\n\n"
        "class Target:\n"
        "    value = 'old'\n\n"
        "class Other:\n"
        "    value = 'old'\n\n"
        "@pytest.fixture\n"
        "def leaky_fixture(request):\n"
        "    request.addfinalizer(lambda: setattr(Other, 'value', 'old'))\n"
        "    Target.value = 'new'\n"
        "    yield\n",
    )

    violations = checker.check_file(src)

    assert len(violations) == 1
    assert "fixture mutates shared state before yield" in violations[0][1]


def test_flags_global_statement_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "STATE = False\n\ndef test_global_write():\n    global STATE\n    STATE = True\n",
    )

    violations = checker.check_file(src)

    assert len(violations) == 1
    assert "global statement" in violations[0][1]


@pytest.mark.parametrize(
    ("statement", "expected_message"),
    [
        ("del sys.modules['optional_dep']", "sys.modules"),
        ("del globals()['STATE']", "globals()"),
        ("del imported_mod.flag", "class/global attribute"),
    ],
)
def test_flags_delete_based_state_mutation(
    tmp_path: Path, statement: str, expected_message: str
) -> None:
    src = _write(
        tmp_path,
        "import sys\n"
        "import package.config as imported_mod\n\n"
        "def test_delete_leaks_state():\n"
        f"    {statement}\n",
    )

    violations = checker.check_file(src)

    assert len(violations) == 1
    assert expected_message in violations[0][1]


def test_targeted_noqa_suppresses_intentional_exception(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "import sys\n\n"
        "def test_intentional_import_cache_state():\n"
        "    sys.modules['fixture_only'] = object()  # noqa\n",
    )

    assert checker.check_file(src) == []


@pytest.mark.xfail(
    strict=False,
    reason="Advisory rail: existing findings are classified before enforcement.",
)
def test_repo_environment_leakage_findings_are_zero() -> None:
    root = Path(__file__).resolve().parents[2]
    violations = [
        (path, lineno, msg, line)
        for path in sorted((root / "tests").rglob("*.py"))
        for lineno, msg, line in checker.check_file(path)
    ]

    assert not violations, "test-environment-leakage findings remain:\n" + "\n".join(
        f"{path.relative_to(root)}:{lineno}: {msg} -> `{line}`"
        for path, lineno, msg, line in violations
    )
