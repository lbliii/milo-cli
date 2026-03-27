"""Tests for extended type system in schema.py (F4)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Literal, TypedDict

from milo.schema import _type_to_schema, function_to_schema

# --- Test Enum ---


class Color(enum.Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class Priority(enum.IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class TestEnum:
    def test_string_enum(self) -> None:
        schema = _type_to_schema(Color)
        assert schema == {"type": "string", "enum": ["red", "green", "blue"]}

    def test_int_enum(self) -> None:
        schema = _type_to_schema(Priority)
        assert schema == {"type": "integer", "enum": [1, 2, 3]}

    def test_enum_in_function(self) -> None:
        def f(color: Color) -> None: ...

        schema = function_to_schema(f)
        assert schema["properties"]["color"] == {"type": "string", "enum": ["red", "green", "blue"]}


# --- Test Literal ---


class TestLiteral:
    def test_string_literal(self) -> None:
        schema = _type_to_schema(Literal["a", "b", "c"])
        assert schema == {"enum": ["a", "b", "c"]}

    def test_int_literal(self) -> None:
        schema = _type_to_schema(Literal[1, 2, 3])
        assert schema == {"enum": [1, 2, 3]}

    def test_literal_in_function(self) -> None:
        def f(mode: Literal["fast", "slow"]) -> None: ...

        schema = function_to_schema(f)
        assert schema["properties"]["mode"] == {"enum": ["fast", "slow"]}


# --- Test dataclass ---


@dataclass
class Address:
    street: str
    city: str
    zip_code: str = ""


@dataclass
class Person:
    name: str
    age: int
    address: Address | None = None


class TestDataclass:
    def test_simple_dataclass(self) -> None:
        schema = _type_to_schema(Address)
        assert schema["type"] == "object"
        assert "street" in schema["properties"]
        assert "city" in schema["properties"]
        assert schema["properties"]["street"] == {"type": "string"}
        assert "street" in schema["required"]
        assert "city" in schema["required"]
        assert "zip_code" not in schema["required"]

    def test_nested_dataclass(self) -> None:
        schema = _type_to_schema(Person)
        assert schema["type"] == "object"
        assert schema["properties"]["name"] == {"type": "string"}
        assert schema["properties"]["age"] == {"type": "integer"}

    def test_dataclass_in_function(self) -> None:
        def f(addr: Address) -> None: ...

        schema = function_to_schema(f)
        assert schema["properties"]["addr"]["type"] == "object"
        assert "street" in schema["properties"]["addr"]["properties"]


# --- Test TypedDict ---


class Config(TypedDict, total=False):
    host: str
    port: int


class StrictConfig(TypedDict):
    host: str
    port: int


class TestTypedDict:
    def test_typed_dict(self) -> None:
        schema = _type_to_schema(Config)
        assert schema["type"] == "object"
        assert schema["properties"]["host"] == {"type": "string"}
        assert schema["properties"]["port"] == {"type": "integer"}

    def test_typed_dict_required_keys(self) -> None:
        schema = _type_to_schema(StrictConfig)
        assert "required" in schema
        assert "host" in schema["required"]
        assert "port" in schema["required"]


# --- Test Union ---


class TestUnion:
    def test_union_two_types(self) -> None:
        schema = _type_to_schema(str | int)
        assert "anyOf" in schema
        assert {"type": "string"} in schema["anyOf"]
        assert {"type": "integer"} in schema["anyOf"]

    def test_union_in_function(self) -> None:
        def f(val: str | int) -> None: ...

        schema = function_to_schema(f)
        assert "anyOf" in schema["properties"]["val"]


# --- Test list[complex_T] ---


class TestListComplex:
    def test_list_of_dataclass(self) -> None:
        schema = _type_to_schema(list[Address])
        assert schema["type"] == "array"
        assert schema["items"]["type"] == "object"
        assert "street" in schema["items"]["properties"]

    def test_list_of_enum(self) -> None:
        schema = _type_to_schema(list[Color])
        assert schema["type"] == "array"
        assert schema["items"] == {"type": "string", "enum": ["red", "green", "blue"]}


# --- Test dict[str, V] ---


class TestDictAdditionalProperties:
    def test_dict_str_int(self) -> None:
        schema = _type_to_schema(dict[str, int])
        assert schema == {"type": "object", "additionalProperties": {"type": "integer"}}

    def test_dict_str_dataclass(self) -> None:
        schema = _type_to_schema(dict[str, Address])
        assert schema["type"] == "object"
        assert schema["additionalProperties"]["type"] == "object"


# --- Test cycle detection ---


@dataclass
class TreeNode:
    value: str
    children: list[TreeNode] = field(default_factory=list)


class TestCycleDetection:
    def test_self_referencing_dataclass(self) -> None:
        schema = _type_to_schema(TreeNode)
        assert schema["type"] == "object"
        assert schema["properties"]["value"] == {"type": "string"}
        # children should be array, but inner TreeNode hits cycle → object
        children_schema = schema["properties"]["children"]
        assert children_schema["type"] == "array"


# --- Test nested combinations ---


class TestNested:
    def test_list_of_optional_int(self) -> None:
        schema = _type_to_schema(list[int | None])
        assert schema["type"] == "array"

    def test_dict_of_list(self) -> None:
        schema = _type_to_schema(dict[str, list[int]])
        assert schema["type"] == "object"
        assert schema["additionalProperties"]["type"] == "array"
