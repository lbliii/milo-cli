"""Property proof for annotation-driven JSON Schema generation."""

from __future__ import annotations

from typing import Annotated, Any

from hypothesis import given
from hypothesis import strategies as st

from milo import Ge, Le, function_to_schema


@given(
    lower=st.integers(min_value=-10_000, max_value=10_000),
    width=st.integers(min_value=0, max_value=1_000),
)
def test_integer_constraint_bounds_are_preserved(lower: int, width: int) -> None:
    upper = lower + width

    def handler(value: int) -> int:
        return value

    handler.__annotations__["value"] = Annotated[int, Ge(lower), Le(upper)]
    schema = function_to_schema(handler)
    value = schema["properties"]["value"]

    assert value["type"] == "integer"
    assert value["minimum"] == lower
    assert value["maximum"] == upper
    assert schema["required"] == ["value"]


@given(
    default=st.one_of(
        st.booleans(),
        st.integers(min_value=-1_000, max_value=1_000),
        st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=40),
    )
)
def test_serializable_defaults_are_optional_and_truthful(default: Any) -> None:
    def handler(value: str = "") -> str:
        return value

    handler.__annotations__["value"] = type(default)
    handler.__defaults__ = (default,)
    schema = function_to_schema(handler)
    value = schema["properties"]["value"]

    assert value["default"] == default
    assert "value" not in schema.get("required", [])


@given(
    description=st.text(
        alphabet=st.sampled_from(tuple("abcdefghijklmnopqrstuvwxyz ")),
        min_size=1,
        max_size=60,
    ).filter(str.strip)
)
def test_docstring_parameter_descriptions_reach_schema(description: str) -> None:
    def handler(value: str) -> str:
        return value

    handler.__doc__ = f"Handle a value.\n\nArgs:\n    value: {description}\n"
    schema = function_to_schema(handler)

    assert schema["properties"]["value"]["description"] == description.strip()
