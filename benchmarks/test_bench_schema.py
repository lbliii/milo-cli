"""Schema generation benchmarks — function_to_schema cost by complexity."""

from __future__ import annotations

from typing import Annotated, Any

from conftest import complex_func, simple_func

from milo.schema import Description, Ge, Le, MaxLen, MinLen, Pattern, function_to_schema

# ---------------------------------------------------------------------------
# Test functions of increasing complexity
# ---------------------------------------------------------------------------


def _no_params() -> str:
    """A function with zero parameters."""
    return "ok"


def _annotated_func(
    name: Annotated[str, MinLen(1), MaxLen(100), Description("Primary name")],
    age: Annotated[int, Ge(0), Le(150), Description("Age in years")],
    email: Annotated[str, Pattern(r"^[\w.]+@[\w.]+$"), Description("Email address")],
    score: Annotated[float, Ge(0.0), Le(100.0)],
    tags: list[str] | None = None,
) -> dict:
    """Function with Annotated constraints.

    Args:
        name: Primary name.
        age: Age in years.
        email: Email address.
        score: Numeric score.
        tags: Optional tags.
    """
    return {"name": name}


def _nested_types(
    items: list[dict[str, Any]],
    mapping: dict[str, list[int]],
    optional_map: dict[str, str] | None = None,
) -> dict:
    """Function with nested generic types.

    Args:
        items: List of dicts.
        mapping: Mapping of string to int lists.
        optional_map: Optional string mapping.
    """
    return {}


# ---------------------------------------------------------------------------
# Schema generation by parameter count
# ---------------------------------------------------------------------------


def test_bench_schema_no_params(benchmark) -> None:
    """Schema generation for function with 0 params (baseline)."""
    benchmark(function_to_schema, _no_params)


def test_bench_schema_simple(benchmark) -> None:
    """Schema generation for function with 2 params (str, int)."""
    benchmark(function_to_schema, simple_func)


def test_bench_schema_complex(benchmark) -> None:
    """Schema generation for function with 10 params (mixed types)."""
    benchmark(function_to_schema, complex_func)


def test_bench_schema_annotated(benchmark) -> None:
    """Schema generation with Annotated constraints (MinLen, MaxLen, Ge, Le, Pattern)."""
    benchmark(function_to_schema, _annotated_func)


def test_bench_schema_nested_types(benchmark) -> None:
    """Schema generation for nested generics (list[dict[str, Any]], dict[str, list[int]])."""
    benchmark(function_to_schema, _nested_types)
