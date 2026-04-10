"""Tests for extended type system in schema.py (F4)."""

from __future__ import annotations

import enum
import warnings
from dataclasses import dataclass, field
from typing import Annotated, Literal, TypedDict

import pytest

from milo.commands import CLI
from milo.schema import (
    Description,
    Ge,
    Gt,
    Le,
    Lt,
    MaxLen,
    MinLen,
    Pattern,
    _parse_param_docs,
    _type_to_schema,
    function_to_schema,
)

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


class TestSchemaHelpText:
    def test_docstring_descriptions_in_schema(self):
        """function_to_schema should extract param descriptions from docstrings."""

        def serve(host: str = "localhost", port: int = 8000) -> str:
            """Start the development server.

            Args:
                host: The hostname to bind to.
                port: The port number to listen on.
            """
            return f"{host}:{port}"

        schema = function_to_schema(serve)
        props = schema["properties"]
        assert props["host"]["description"] == "The hostname to bind to."
        assert props["port"]["description"] == "The port number to listen on."

    def test_sphinx_style_docstring(self):
        """Sphinx-style :param: directives."""

        def build(output: str = "_site", drafts: bool = False) -> str:
            """Build the static site.

            :param output: The output directory.
            :param drafts: Include draft pages.
            """
            return output

        schema = function_to_schema(build)
        assert schema["properties"]["output"]["description"] == "The output directory."
        assert schema["properties"]["drafts"]["description"] == "Include draft pages."

    def test_numpy_style_docstring(self):
        """NumPy-style parameter docs."""

        def process(count: int, mode: str = "fast") -> str:
            """Process items.

            Parameters
            ----------
            count : int
                Number of items to process.
            mode : str
                Processing mode (fast or slow).
            """
            return f"{count}:{mode}"

        schema = function_to_schema(process)
        assert schema["properties"]["count"]["description"] == "Number of items to process."
        assert schema["properties"]["mode"]["description"] == "Processing mode (fast or slow)."

    def test_no_docstring_no_description(self):
        """Functions without docstrings should not crash."""

        def plain(name: str) -> str:
            return name

        schema = function_to_schema(plain)
        assert "description" not in schema["properties"]["name"]

    def test_help_text_propagated_to_argparse(self, capsys):
        """Verify that help text from docstrings shows up in --help output."""
        cli = CLI(name="test")

        @cli.command("serve", description="Start server")
        def serve(host: str = "localhost", port: int = 8000) -> str:
            """Start the development server.

            Args:
                host: The hostname to bind to.
                port: The port number.
            """
            return f"{host}:{port}"

        with pytest.raises(SystemExit):
            cli.run(["serve", "--help"])
        out = capsys.readouterr().out
        # The help text from the docstring should appear
        assert "hostname" in out.lower() or "host" in out.lower()

    def test_parse_param_docs_empty(self):
        """Empty or no-param docstrings return empty dict."""
        assert _parse_param_docs("Just a description.") == {}
        assert _parse_param_docs("") == {}

    def test_parse_param_docs_google(self):
        result = _parse_param_docs("""Do something.

        Args:
            name: The user's name.
            count (int): How many times.
        """)
        assert result["name"] == "The user's name."
        assert result["count"] == "How many times."

    def test_parse_param_docs_sphinx(self):
        result = _parse_param_docs("""Do something.

        :param name: The user's name.
        :param count: How many times.
        """)
        assert result["name"] == "The user's name."
        assert result["count"] == "How many times."


# ---------------------------------------------------------------------------
# Annotated constraint tests
# ---------------------------------------------------------------------------


class TestAnnotatedConstraints:
    def test_min_max_length(self):

        def func(name: Annotated[str, MinLen(1), MaxLen(100)]):
            pass

        schema = function_to_schema(func)
        prop = schema["properties"]["name"]
        assert prop["type"] == "string"
        assert prop["minLength"] == 1
        assert prop["maxLength"] == 100

    def test_gt_lt(self):

        def func(age: Annotated[int, Gt(0), Lt(200)]):
            pass

        schema = function_to_schema(func)
        prop = schema["properties"]["age"]
        assert prop["type"] == "integer"
        assert prop["exclusiveMinimum"] == 0
        assert prop["exclusiveMaximum"] == 200

    def test_ge_le(self):

        def func(score: Annotated[float, Ge(0.0), Le(100.0)]):
            pass

        schema = function_to_schema(func)
        prop = schema["properties"]["score"]
        assert prop["type"] == "number"
        assert prop["minimum"] == 0.0
        assert prop["maximum"] == 100.0

    def test_pattern(self):

        def func(email: Annotated[str, Pattern(r"^[^@]+@[^@]+$")]):
            pass

        schema = function_to_schema(func)
        prop = schema["properties"]["email"]
        assert prop["type"] == "string"
        assert prop["pattern"] == r"^[^@]+@[^@]+$"

    def test_description_override(self):

        def func(name: Annotated[str, Description("The user's full name")]):
            pass

        schema = function_to_schema(func)
        prop = schema["properties"]["name"]
        assert prop["description"] == "The user's full name"

    def test_unknown_annotations_ignored(self):
        def func(x: Annotated[str, "some random metadata", 42]):
            pass

        schema = function_to_schema(func)
        prop = schema["properties"]["x"]
        assert prop == {"type": "string"}

    def test_annotated_optional(self):

        def func(name: Annotated[str | None, MinLen(1)] = None):
            pass

        schema = function_to_schema(func)
        prop = schema["properties"]["name"]
        assert prop["type"] == "string"
        assert prop["minLength"] == 1
        assert "required" not in schema

    def test_annotated_with_list(self):

        def func(tags: Annotated[list[str], MinLen(1)]):
            pass

        schema = function_to_schema(func)
        prop = schema["properties"]["tags"]
        assert prop["type"] == "array"
        assert prop["minItems"] == 1


# ---------------------------------------------------------------------------
# Tuple / set / frozenset support
# ---------------------------------------------------------------------------


class TestTupleSetFrozenset:
    def test_tuple_str_ellipsis(self) -> None:
        schema = _type_to_schema(tuple[str, ...])
        assert schema == {"type": "array", "items": {"type": "string"}}

    def test_tuple_int(self) -> None:
        schema = _type_to_schema(tuple[int])
        assert schema == {"type": "array", "items": {"type": "integer"}}

    def test_bare_tuple(self) -> None:
        schema = _type_to_schema(tuple)
        assert schema == {"type": "array"}

    def test_set_int(self) -> None:
        schema = _type_to_schema(set[int])
        assert schema == {"type": "array", "items": {"type": "integer"}, "uniqueItems": True}

    def test_frozenset_str(self) -> None:
        schema = _type_to_schema(frozenset[str])
        assert schema == {"type": "array", "items": {"type": "string"}, "uniqueItems": True}

    def test_bare_set(self) -> None:
        schema = _type_to_schema(set)
        assert schema == {"type": "array"}

    def test_bare_frozenset(self) -> None:
        schema = _type_to_schema(frozenset)
        assert schema == {"type": "array"}

    def test_tuple_in_function(self) -> None:
        def f(tags: tuple[str, ...]) -> None: ...

        schema = function_to_schema(f)
        assert schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}

    def test_set_in_function(self) -> None:
        def f(ids: set[int]) -> None: ...

        schema = function_to_schema(f)
        prop = schema["properties"]["ids"]
        assert prop["type"] == "array"
        assert prop["uniqueItems"] is True


# ---------------------------------------------------------------------------
# Warning on fallback
# ---------------------------------------------------------------------------


class TestFallbackWarning:
    def test_unknown_type_emits_warning(self) -> None:
        class CustomClass:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            schema = _type_to_schema(CustomClass)

        assert schema == {"type": "string"}
        assert len(w) == 1
        assert "CustomClass" in str(w[0].message)

    def test_known_types_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _type_to_schema(str)
            _type_to_schema(int)
            _type_to_schema(list[str])
            _type_to_schema(dict[str, int])

        assert len(w) == 0


# ---------------------------------------------------------------------------
# $ref for recursive dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Node:
    value: str
    children: list[Node] = field(default_factory=list)


@dataclass
class Left:
    right: Right | None = None


@dataclass
class Right:
    left: Left | None = None


class TestSchemaRef:
    def test_self_reference_produces_ref(self) -> None:
        schema = _type_to_schema(Node)
        assert schema["type"] == "object"
        assert schema["properties"]["value"] == {"type": "string"}
        children = schema["properties"]["children"]
        assert children["type"] == "array"
        assert children["items"] == {"$ref": "#/$defs/Node"}

    def test_self_reference_in_function(self) -> None:
        def f(tree: Node) -> None: ...

        schema = function_to_schema(f)
        assert "$defs" in schema
        assert "Node" in schema["$defs"]
        node_schema = schema["$defs"]["Node"]
        assert node_schema["type"] == "object"
        assert "value" in node_schema["properties"]

    def test_mutual_recursion_produces_ref(self) -> None:
        schema = _type_to_schema(Left)
        assert schema["type"] == "object"
        # Left.right → Right, Right.left → Left (cycle) → $ref
        right_schema = schema["properties"]["right"]
        # Right is a nested dataclass
        assert right_schema["type"] == "object"
        left_ref = right_schema["properties"]["left"]
        assert left_ref == {"$ref": "#/$defs/Left"}
