"""Function signature → JSON Schema for MCP tool compatibility."""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable
from typing import Any, Union, get_args, get_origin

_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def function_to_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Generate MCP-compatible JSON Schema from function type annotations.

    Parameters with defaults are optional (not in required).
    X | None unions unwrapped to base type.
    Supports: str, int, float, bool, list[X], dict[str, X], X | None.
    """
    sig = inspect.signature(func)
    # Resolve string annotations (from __future__ import annotations)
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        annotation = hints.get(name, param.annotation)
        if annotation is inspect.Parameter.empty:
            annotation = str

        # Strip return type
        if name == "return":
            continue

        is_optional = _is_optional(annotation)
        if is_optional:
            annotation = _unwrap_optional(annotation)

        properties[name] = _type_to_schema(annotation)

        has_default = param.default is not inspect.Parameter.empty
        if not has_default and not is_optional:
            required.append(name)

    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def _type_to_schema(annotation: Any) -> dict[str, Any]:
    """Convert Python type annotation to JSON Schema fragment."""
    if annotation in _TYPE_MAP:
        return {"type": _TYPE_MAP[annotation]}

    origin = get_origin(annotation)
    if origin is list:
        args = get_args(annotation)
        if args and args[0] in _TYPE_MAP:
            return {"type": "array", "items": {"type": _TYPE_MAP[args[0]]}}
        return {"type": "array"}

    if origin is dict:
        return {"type": "object"}

    return {"type": "string"}


def _is_optional(annotation: Any) -> bool:
    """Check if annotation is X | None."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return type(None) in get_args(annotation)
    return False


def _unwrap_optional(annotation: Any) -> Any:
    """Extract non-None type from X | None."""
    args = get_args(annotation)
    non_none = [a for a in args if a is not type(None)]
    return non_none[0] if len(non_none) == 1 else str
