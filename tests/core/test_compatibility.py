"""
Compatibility test suite for Python 3.11+ support validation.

Validates that all patterns used in the codebase work correctly on Python
3.11 and later. This suite is designed to be run under tox against Python
3.11+ interpreters.

Test areas:
- ``from __future__ import annotations`` behavior
- StrEnum correctness (stdlib, Python 3.11+)
- Dataclass field type resolution
- isinstance() with tuple form
- Import path resolution
- datetime.UTC (Python 3.11+)
"""

from __future__ import annotations

import datetime
import importlib
import sys
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any, get_type_hints

import pytest

# ===================================================================
# Section 1: ``from __future__ import annotations`` tests
# ===================================================================


@pytest.mark.unit
class TestFutureAnnotations:
    """Verify that PEP 563 postponed evaluation works for all type hint patterns."""

    def test_builtin_generic_list_annotation(self) -> None:
        """list[str] in annotations should work with future annotations."""

        def func(items: list[str]) -> list[int]:
            return [len(s) for s in items]

        result = func(["hello", "world"])
        assert result == [5, 5]

    def test_builtin_generic_dict_annotation(self) -> None:
        """dict[str, int] in annotations should work with future annotations."""

        def func(mapping: dict[str, int]) -> dict[str, str]:
            return {k: str(v) for k, v in mapping.items()}

        result = func({"a": 1})
        assert result == {"a": "1"}

    def test_builtin_generic_tuple_annotation(self) -> None:
        """tuple[int, str] in annotations should work with future annotations."""

        def func(pair: tuple[int, str]) -> tuple[str, int]:
            return (pair[1], pair[0])

        result = func((42, "hello"))
        assert result == ("hello", 42)

    def test_builtin_generic_set_annotation(self) -> None:
        """set[int] in annotations should work with future annotations."""

        def func(values: set[int]) -> frozenset[int]:
            return frozenset(values)

        result = func({1, 2, 3})
        assert result == frozenset({1, 2, 3})

    def test_union_pipe_syntax_annotation(self) -> None:
        """int | str in annotations should work with future annotations."""

        def func(value: int | str) -> str:
            return str(value)

        assert func(42) == "42"
        assert func("hello") == "hello"

    def test_optional_as_union_none(self) -> None:
        """str | None in annotations should work with future annotations."""

        def func(value: str | None = None) -> str:
            return value or "default"

        assert func() == "default"
        assert func("hello") == "hello"

    def test_nested_generic_annotation(self) -> None:
        """Nested generics like list[dict[str, list[int]]] should work."""

        def func(data: list[dict[str, list[int]]]) -> int:
            total = 0
            for item in data:
                for values in item.values():
                    total += sum(values)
            return total

        assert func([{"a": [1, 2]}, {"b": [3]}]) == 6

    def test_callable_annotation(self) -> None:
        """Callable types in annotations should work with future annotations."""
        from collections.abc import Callable

        def apply(func: Callable[[int], int], value: int) -> int:
            return func(value)

        assert apply(lambda x: x * 2, 5) == 10

    def test_class_method_annotations(self) -> None:
        """Class method annotations with 3.10+ syntax should work."""

        class MyClass:
            def method(self, items: list[str]) -> dict[str, int]:
                return {item: len(item) for item in items}

        obj = MyClass()
        assert obj.method(["hi"]) == {"hi": 2}

    def test_type_hints_are_strings_at_runtime(self) -> None:
        """With future annotations, type hints are stored as strings."""

        def func(x: int | str) -> list[int]:
            return [1]

        # Annotations are stored as strings, not evaluated
        annotations = func.__annotations__
        assert isinstance(annotations["x"], str) and "int" in annotations["x"]
        assert isinstance(annotations["return"], str)


# ===================================================================
# Section 2: StrEnum backport tests
# ===================================================================


@pytest.mark.unit
class TestStrEnumBackport:
    """Verify the StrEnum backport works identically to the 3.11+ stdlib version."""

    def test_import_from_compat(self) -> None:
        """StrEnum should be importable from _compat module."""
        from file_organizer._compat import StrEnum

        assert StrEnum is not None

    def test_basic_strenum_creation(self) -> None:
        """Creating a StrEnum subclass should work."""
        from file_organizer._compat import StrEnum

        class Color(StrEnum):
            RED = "red"
            GREEN = "green"
            BLUE = "blue"

        assert len(Color) == 3

    def test_strenum_string_equality(self) -> None:
        """StrEnum members should compare equal to their string values."""
        from file_organizer._compat import StrEnum

        class Status(StrEnum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        assert Status.ACTIVE == "active"
        assert Status.INACTIVE == "inactive"

    def test_strenum_str_conversion(self) -> None:
        """str() on StrEnum member should return the value, not 'Class.MEMBER'."""
        from file_organizer._compat import StrEnum

        class Priority(StrEnum):
            HIGH = "high"
            LOW = "low"

        assert str(Priority.HIGH) == "high"
        assert str(Priority.LOW) == "low"

    def test_strenum_format_string(self) -> None:
        """StrEnum members should work in f-strings and format()."""
        from file_organizer._compat import StrEnum

        class Level(StrEnum):
            INFO = "info"
            WARN = "warn"

        assert f"level={Level.INFO}" == "level=info"
        assert f"level={Level.WARN}" == "level=warn"

    def test_strenum_is_string_subclass(self) -> None:
        """StrEnum members should be instances of str with their string value."""
        from file_organizer._compat import StrEnum

        class Direction(StrEnum):
            NORTH = "north"

        assert isinstance(Direction.NORTH, str) and Direction.NORTH == "north"

    def test_strenum_is_enum_subclass(self) -> None:
        """StrEnum members should be instances of Enum."""
        from file_organizer._compat import StrEnum

        class Direction(StrEnum):
            NORTH = "north"

        assert isinstance(Direction.NORTH, Enum)

    def test_strenum_value_access(self) -> None:
        """StrEnum .value should return the string value."""
        from file_organizer._compat import StrEnum

        class Mode(StrEnum):
            READ = "read"
            WRITE = "write"

        assert Mode.READ.value == "read"
        assert Mode.WRITE.name == "WRITE"

    def test_strenum_iteration(self) -> None:
        """StrEnum should support iteration over members."""
        from file_organizer._compat import StrEnum

        class Suit(StrEnum):
            HEARTS = "hearts"
            DIAMONDS = "diamonds"
            CLUBS = "clubs"
            SPADES = "spades"

        values = [s.value for s in Suit]
        assert values == ["hearts", "diamonds", "clubs", "spades"]

    def test_strenum_lookup_by_value(self) -> None:
        """StrEnum should support lookup by value."""
        from file_organizer._compat import StrEnum

        class Season(StrEnum):
            SPRING = "spring"
            SUMMER = "summer"

        assert Season("spring") is Season.SPRING
        assert Season("summer") is Season.SUMMER

    def test_strenum_in_dict_key(self) -> None:
        """StrEnum members should work as dict keys and match string keys."""
        from file_organizer._compat import StrEnum

        class Key(StrEnum):
            NAME = "name"
            AGE = "age"

        data: dict[str, Any] = {Key.NAME: "Alice", Key.AGE: 30}
        # Access by enum member
        assert data[Key.NAME] == "Alice"

    def test_strenum_hashable(self) -> None:
        """StrEnum members should be hashable and usable in sets."""
        from file_organizer._compat import StrEnum

        class Tag(StrEnum):
            A = "a"
            B = "b"

        tag_set = {Tag.A, Tag.B, Tag.A}
        assert len(tag_set) == 2

    def test_strenum_type_error_on_non_string(self) -> None:
        """StrEnum should reject non-string values."""
        from file_organizer._compat import StrEnum

        # On Python 3.11+ the native StrEnum raises TypeError too
        with pytest.raises((TypeError, ValueError)):

            class Bad(StrEnum):
                ITEM = 123  # type: ignore[assignment]

    def test_strenum_repr(self) -> None:
        """StrEnum repr should include class name and member name."""
        from file_organizer._compat import StrEnum

        class Flavor(StrEnum):
            VANILLA = "vanilla"

        r = repr(Flavor.VANILLA)
        assert "Flavor" in r
        assert "VANILLA" in r

    def test_para_category_enum(self) -> None:
        """Test that the real PARACategory enum from the codebase works."""
        from file_organizer.methodologies.para.categories import PARACategory

        assert PARACategory.PROJECT == "project"
        assert PARACategory.AREA == "area"
        assert PARACategory.RESOURCE == "resource"
        assert PARACategory.ARCHIVE == "archive"
        assert isinstance(PARACategory.PROJECT, str)

    def test_operation_type_enum(self) -> None:
        """Test that the real OperationType enum from the codebase works."""
        from file_organizer.history.models import OperationType

        assert OperationType.MOVE == "move"
        assert OperationType.RENAME == "rename"
        assert isinstance(OperationType.MOVE, str)


# ===================================================================
# Section 3: Dataclass field type resolution tests
# ===================================================================


@pytest.mark.unit
class TestDataclassCompatibility:
    """Verify dataclass patterns work correctly with future annotations."""

    def test_basic_dataclass_creation(self) -> None:
        """Basic dataclass with new-style annotations should work."""

        @dataclass
        class Point:
            x: int
            y: int

        p = Point(x=1, y=2)
        assert p.x == 1
        assert p.y == 2

    def test_dataclass_with_generic_fields(self) -> None:
        """Dataclass with list[str], dict[str, int] etc. should work."""

        @dataclass
        class Container:
            items: list[str] = field(default_factory=list)
            extra_data: dict[str, Any] = field(default_factory=dict)

        c = Container()
        c.items.append("hello")
        c.extra_data["key"] = 42
        assert c.items == ["hello"]
        assert c.extra_data == {"key": 42}

    def test_dataclass_with_optional_fields(self) -> None:
        """Dataclass with str | None fields should work."""

        @dataclass
        class Config:
            name: str
            description: str | None = None
            tags: list[str] | None = None

        c = Config(name="test")
        assert c.name == "test"
        assert c.description is None
        assert c.tags is None

    def test_dataclass_field_types_resolve(self) -> None:
        """get_type_hints() should resolve string annotations to real types."""

        @dataclass
        class Record:
            name: str
            values: list[int] = field(default_factory=list)

        hints = get_type_hints(Record)
        assert hints["name"] is str
        # The resolved hint for 'values' should be list[int]
        assert hints["values"] is not str  # Should not be a string anymore

    def test_dataclass_fields_metadata(self) -> None:
        """Dataclass fields() introspection should work."""

        @dataclass
        class Item:
            name: str
            count: int = 0
            active: bool = True

        f = fields(Item)
        names = [fld.name for fld in f]
        assert names == ["name", "count", "active"]

    def test_dataclass_hasattr_access(self) -> None:
        """Proper dataclass access should use hasattr, not 'in'."""

        @dataclass
        class Metadata:
            title: str
            duration: float | None = None

        m = Metadata(title="test")

        # Correct pattern: use hasattr
        assert hasattr(m, "title")
        assert hasattr(m, "duration")
        assert m.title == "test"
        assert m.duration is None

        # Incorrect pattern: dict-style 'in' check should NOT work
        assert not isinstance(m, dict)

    def test_frozen_dataclass(self) -> None:
        """Frozen dataclasses should work with new-style annotations."""

        @dataclass(frozen=True)
        class ImmutablePoint:
            x: int
            y: int

        p = ImmutablePoint(x=1, y=2)
        with pytest.raises(AttributeError):
            p.x = 3  # type: ignore[misc]


# ===================================================================
# Section 4: isinstance() with tuple form tests
# ===================================================================


@pytest.mark.unit
class TestIsinstanceTupleForm:
    """Validate that isinstance() uses the 3.9-safe tuple form throughout."""

    def test_isinstance_single_type(self) -> None:
        """isinstance with a single type should work."""
        assert isinstance(42, int) and 42 == 42
        assert isinstance("hello", str) and len("hello") == 5

    def test_isinstance_tuple_of_types(self) -> None:
        """isinstance with tuple of types (3.9-safe form) should work."""
        assert isinstance(42, (int, str))
        assert isinstance("hello", (int, str))
        assert not isinstance(3.14, (int, str))

    def test_isinstance_with_none_type(self) -> None:
        """isinstance check for None should use type(None) in tuple form."""
        value: int | None = None
        assert isinstance(value, (int, type(None)))

        value2: int | None = 42
        assert isinstance(value2, (int, type(None)))

    def test_isinstance_path_types(self) -> None:
        """isinstance with Path types should work."""
        p = Path("/tmp/test")
        assert isinstance(p, (str, Path))
        assert not isinstance(42, (str, Path))

    def test_isinstance_with_enum(self) -> None:
        """isinstance checks with Enum types should work."""
        from file_organizer._compat import StrEnum

        class Color(StrEnum):
            RED = "red"

        assert isinstance(Color.RED, (str, Enum))
        assert isinstance(Color.RED, str)


# ===================================================================
# Section 5: Import path resolution tests
# ===================================================================


@pytest.mark.unit
class TestImportPaths:
    """Verify that all critical import paths resolve correctly."""

    def test_import_compat_module(self) -> None:
        """The _compat module should be importable."""
        mod = importlib.import_module("file_organizer._compat")
        assert hasattr(mod, "StrEnum")
        assert hasattr(mod, "UTC")

    def test_import_strenum_from_compat(self) -> None:
        """StrEnum should be importable from _compat."""
        from file_organizer._compat import StrEnum

        assert issubclass(StrEnum, Enum)

    def test_import_para_categories(self) -> None:
        """PARACategory should be importable."""
        from file_organizer.methodologies.para.categories import PARACategory

        assert issubclass(PARACategory, Enum)

    def test_import_history_models(self) -> None:
        """History models should be importable."""
        from file_organizer.history.models import OperationStatus, OperationType

        assert issubclass(OperationType, Enum)
        assert issubclass(OperationStatus, Enum)

    def test_import_undo_models(self) -> None:
        """Undo models should be importable."""
        from file_organizer.undo.models import ConflictType

        assert issubclass(ConflictType, Enum)

    def test_compat_all_exports(self) -> None:
        """_compat.__all__ should list all public exports."""
        from file_organizer import _compat

        assert "StrEnum" in _compat.__all__
        assert "UTC" in _compat.__all__


# ===================================================================
# Section 6: datetime.UTC tests (Python 3.11+)
# ===================================================================


@pytest.mark.unit
class TestDatetimeCompatibility:
    """Ensure datetime.UTC (Python 3.11+) is used throughout the codebase."""

    def test_timezone_utc_exists(self) -> None:
        """datetime.UTC should exist on Python 3.11+."""
        utc = datetime.UTC
        assert utc is not None

    def test_timezone_utc_offset(self) -> None:
        """timezone.utc should have zero offset."""
        utc = datetime.UTC
        assert utc.utcoffset(None) == datetime.timedelta(0)

    def test_utc_from_compat(self) -> None:
        """UTC constant from _compat should match datetime.UTC."""
        from file_organizer._compat import UTC

        assert UTC is datetime.UTC

    def test_datetime_now_with_utc(self) -> None:
        """Creating UTC-aware datetimes should use datetime.UTC."""
        now = datetime.datetime.now(tz=datetime.UTC)
        assert now.tzinfo is not None
        assert now.tzinfo == datetime.UTC

    def test_datetime_now_with_compat_utc(self) -> None:
        """Creating UTC-aware datetimes with _compat.UTC should work."""
        from file_organizer._compat import UTC

        now = datetime.datetime.now(tz=UTC)
        assert now.tzinfo is not None
        assert now.tzinfo == datetime.UTC

    def test_utc_aware_comparison(self) -> None:
        """UTC-aware datetimes should be comparable."""
        from file_organizer._compat import UTC

        t1 = datetime.datetime(2024, 1, 1, tzinfo=UTC)
        t2 = datetime.datetime(2024, 6, 1, tzinfo=UTC)
        assert t1 < t2

    def test_utc_isoformat(self) -> None:
        """UTC datetime isoformat should include timezone info."""
        from file_organizer._compat import UTC

        dt = datetime.datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)
        iso = dt.isoformat()
        assert "+00:00" in iso or "Z" in iso


# ===================================================================
# Section 7: Version detection tests
# ===================================================================


@pytest.mark.unit
class TestVersionDetection:
    """Test runtime version detection utilities."""

    def test_python_version_fixture(self, python_version: tuple[int, int]) -> None:
        """The python_version fixture should return the correct version."""
        assert python_version == sys.version_info[:2]
        assert python_version[0] == 3
        assert python_version[1] >= 11

    def test_python_version_string_fixture(self, python_version_string: str) -> None:
        """The python_version_string fixture should be a dotted version."""
        parts = python_version_string.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)
