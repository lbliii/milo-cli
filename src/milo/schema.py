"""Function signature → JSON Schema for MCP tool compatibility."""

from __future__ import annotations

import dataclasses
import enum
import functools
import inspect
import re as _re
import types
import typing
import warnings
from collections.abc import Callable
from typing import Any, Literal, Union, get_args, get_origin

# ---------------------------------------------------------------------------
# Annotated constraint markers
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class MinLen:
    """Minimum length for strings (minLength) or items for arrays (minItems)."""

    value: int


@dataclasses.dataclass(frozen=True, slots=True)
class MaxLen:
    """Maximum length for strings (maxLength) or items for arrays (maxItems)."""

    value: int


@dataclasses.dataclass(frozen=True, slots=True)
class Gt:
    """Exclusive minimum constraint for numbers."""

    value: int | float


@dataclasses.dataclass(frozen=True, slots=True)
class Lt:
    """Exclusive maximum constraint for numbers."""

    value: int | float


@dataclasses.dataclass(frozen=True, slots=True)
class Ge:
    """Inclusive minimum constraint for numbers."""

    value: int | float


@dataclasses.dataclass(frozen=True, slots=True)
class Le:
    """Inclusive maximum constraint for numbers."""

    value: int | float


@dataclasses.dataclass(frozen=True, slots=True)
class Pattern:
    """Regex pattern constraint for strings."""

    value: str


@dataclasses.dataclass(frozen=True, slots=True)
class Description:
    """Override or supplement the parameter description."""

    value: str


_CONSTRAINT_MAP: dict[type, str] = {
    MinLen: "minLength",
    MaxLen: "maxLength",
    Gt: "exclusiveMinimum",
    Lt: "exclusiveMaximum",
    Ge: "minimum",
    Le: "maximum",
    Pattern: "pattern",
    Description: "description",
}


_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


@functools.lru_cache(maxsize=256)
def function_to_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Generate MCP-compatible JSON Schema from function type annotations.

    Parameters with defaults are optional (not in required).
    X | None unions unwrapped to base type.
    Supports: str, int, float, bool, list[X], dict[str, X], X | None,
    Enum, Literal, dataclass, TypedDict, Union.

    Parameter descriptions are extracted from the function's docstring
    (Google, NumPy, or Sphinx style) and included as ``"description"``
    fields in the schema properties.
    """
    sig = inspect.signature(func)
    # Resolve string annotations (from __future__ import annotations)
    # include_extras=True preserves Annotated metadata for constraint extraction
    try:
        hints = typing.get_type_hints(func, include_extras=True)
    except Exception:
        hints = {}

    # Extract parameter descriptions from docstring
    param_docs = _parse_param_docs(func.__doc__) if func.__doc__ else {}

    properties: dict[str, Any] = {}
    required: list[str] = []
    defs: dict[str, dict[str, Any]] = {}

    for name, param in sig.parameters.items():
        annotation = hints.get(name, param.annotation)
        if annotation is inspect.Parameter.empty:
            annotation = str

        # Strip return type
        if name == "return":
            continue

        # Skip Context parameters (injected by CLI dispatcher)
        if _is_context_type(annotation, name):
            continue

        # Unwrap Annotated to check optional underneath
        bare = annotation
        annotated_meta: tuple = ()
        if get_origin(bare) is typing.Annotated:
            annotated_args = get_args(bare)
            bare = annotated_args[0]
            annotated_meta = annotated_args[1:]

        is_optional = _is_optional(bare)
        if is_optional:
            unwrapped = _unwrap_optional(bare)
            if annotated_meta:
                # Re-wrap: Annotated[unwrapped_type, *meta]
                annotation = typing.Annotated[(unwrapped, *annotated_meta)]
            else:
                annotation = unwrapped

        prop = _type_to_schema(annotation, _defs=defs)

        # Add description from docstring if available
        if name in param_docs:
            prop["description"] = param_docs[name]

        properties[name] = prop

        has_default = param.default is not inspect.Parameter.empty
        if has_default:
            prop["default"] = param.default
        if not has_default and not is_optional:
            required.append(name)

    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    if defs:
        result["$defs"] = defs
    return result


def _type_to_schema(
    annotation: Any,
    _seen: set[int] | None = None,
    _defs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert Python type annotation to JSON Schema fragment.

    *_defs* accumulates ``$defs`` entries for recursive dataclasses so
    they can be emitted as ``{"$ref": "#/$defs/ClassName"}``.
    """
    # Annotated[T, constraints...] — unwrap and apply constraints
    origin = get_origin(annotation)
    if origin is typing.Annotated:
        args = get_args(annotation)
        base_type = args[0]
        schema = _type_to_schema(base_type, _seen, _defs)
        is_array = schema.get("type") == "array"
        for meta in args[1:]:
            key = _CONSTRAINT_MAP.get(type(meta))
            if key:
                # MinLen/MaxLen map to minItems/maxItems for arrays
                if is_array and key == "minLength":
                    key = "minItems"
                elif is_array and key == "maxLength":
                    key = "maxItems"
                schema[key] = meta.value
        return schema

    # Primitive types
    if annotation in _TYPE_MAP:
        return {"type": _TYPE_MAP[annotation]}

    # Handle bare dict/list/tuple/set/frozenset (unparameterized)
    if annotation is dict:
        return {"type": "object"}
    if annotation is list or annotation is tuple or annotation is set or annotation is frozenset:
        return {"type": "array"}

    # Enum subclass
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        values = [m.value for m in annotation]
        if all(isinstance(v, int) for v in values):
            return {"type": "integer", "enum": values}
        return {"type": "string", "enum": values}

    # Literal
    origin = get_origin(annotation)
    if origin is Literal:
        return {"enum": list(get_args(annotation))}

    # dataclass
    if dataclasses.is_dataclass(annotation) and isinstance(annotation, type):
        if _seen is None:
            _seen = set()
        if _defs is None:
            _defs = {}
        type_id = id(annotation)
        class_name = annotation.__name__
        if type_id in _seen:
            # Cycle detected — emit $ref
            return {"$ref": f"#/$defs/{class_name}"}
        _seen = _seen | {type_id}
        props = {}
        req = []
        hints = typing.get_type_hints(annotation)
        for f in dataclasses.fields(annotation):
            field_type = hints.get(f.name, str)
            props[f.name] = _type_to_schema(field_type, _seen, _defs)
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                req.append(f.name)
        result: dict[str, Any] = {"type": "object", "properties": props}
        if req:
            result["required"] = req
        # Register in $defs if any field references this class (cycle was hit)
        if class_name in _defs or any(
            "$ref" in str(v) and class_name in str(v) for v in props.values()
        ):
            _defs[class_name] = result
        return result

    # TypedDict
    if _is_typed_dict(annotation):
        if _seen is None:
            _seen = set()
        type_id = id(annotation)
        if type_id in _seen:
            return {"$ref": f"#/$defs/{annotation.__name__}"}
        _seen = _seen | {type_id}
        hints = typing.get_type_hints(annotation)
        props = {}
        for fname, ftype in hints.items():
            props[fname] = _type_to_schema(ftype, _seen, _defs)
        result: dict[str, Any] = {"type": "object", "properties": props}
        # TypedDict required keys
        req_keys = getattr(annotation, "__required_keys__", set())
        if req_keys:
            result["required"] = sorted(req_keys)
        return result

    # Union (non-Optional, non-None)
    if origin is Union or origin is types.UnionType:
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) > 1:
            if _seen is None:
                _seen = set()
            return {"anyOf": [_type_to_schema(a, _seen, _defs) for a in non_none]}
        if len(non_none) == 1:
            return _type_to_schema(non_none[0], _seen, _defs)

    # list[T] with recursive item schema
    if origin is list:
        args = get_args(annotation)
        if args:
            return {"type": "array", "items": _type_to_schema(args[0], _seen, _defs)}
        return {"type": "array"}

    # tuple[T, ...] → array with items
    if origin is tuple:
        args = get_args(annotation)
        if args:
            # tuple[T, ...] (homogeneous) or tuple[T] (single-element)
            non_ellipsis = [a for a in args if a is not Ellipsis]
            if non_ellipsis:
                return {"type": "array", "items": _type_to_schema(non_ellipsis[0], _seen, _defs)}
        return {"type": "array"}

    # set[T] / frozenset[T] → array with uniqueItems
    if origin is set or origin is frozenset:
        args = get_args(annotation)
        schema: dict[str, Any] = {"type": "array", "uniqueItems": True}
        if args:
            schema["items"] = _type_to_schema(args[0], _seen, _defs)
        return schema

    # dict[str, V] with additionalProperties
    if origin is dict:
        args = get_args(annotation)
        if args and len(args) == 2:
            return {
                "type": "object",
                "additionalProperties": _type_to_schema(args[1], _seen, _defs),
            }
        return {"type": "object"}

    # Unknown type — warn and fall back to string
    type_name = getattr(annotation, "__name__", None) or str(annotation)
    warnings.warn(
        f'Unrecognized type {type_name!r} falling back to {{"type": "string"}}',
        UserWarning,
        stacklevel=2,
    )
    return {"type": "string"}


def _is_typed_dict(annotation: Any) -> bool:
    """Check if annotation is a TypedDict subclass."""
    return (
        isinstance(annotation, type)
        and issubclass(annotation, dict)
        and hasattr(annotation, "__annotations__")
        and hasattr(annotation, "__required_keys__")
    )


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


def return_to_schema(func: Callable[..., Any]) -> dict[str, Any] | None:
    """Generate JSON Schema from function return type annotation.

    Returns None if the function has no return annotation or returns None.
    """
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        hints = {}

    ret = hints.get("return", inspect.Parameter.empty)
    if ret is inspect.Parameter.empty or ret is type(None):
        return None

    # Unwrap Optional return types
    if _is_optional(ret):
        ret = _unwrap_optional(ret)
        if ret is type(None):
            return None

    return _type_to_schema(ret)


def _is_context_type(annotation: Any, name: str) -> bool:
    """Check if an annotation refers to milo's Context type."""
    if name == "ctx":
        return True
    if isinstance(annotation, type) and annotation.__name__ == "Context":
        return True
    return isinstance(annotation, str) and annotation in ("Context", "milo.context.Context")


_GOOGLE_PARAM_RE = _re.compile(r"^\s{2,}(\w+)\s*(?:\(.*?\))?\s*:\s*(.+?)$", _re.MULTILINE)
_SPHINX_PARAM_RE = _re.compile(r"^\s*:param\s+(\w+)\s*:\s*(.+?)$", _re.MULTILINE)
_NUMPY_PARAM_RE = _re.compile(r"^(\w+)\s*:.*?\n\s{4,}(.+?)$", _re.MULTILINE)


def _parse_param_docs(docstring: str) -> dict[str, str]:
    """Extract parameter descriptions from a docstring.

    Supports Google, Sphinx, and NumPy docstring styles::

        # Google style
        Args:
            name: The user's name.
            loud (bool): Whether to shout.

        # Sphinx style
        :param name: The user's name.

        # NumPy style
        Parameters
        ----------
        name : str
            The user's name.
    """
    result: dict[str, str] = {}

    # Google style: look for "Args:" or "Arguments:" section
    args_match = _re.search(r"(?:Args|Arguments|Parameters)\s*:\s*\n((?:\s{2,}.+\n?)+)", docstring)
    if args_match:
        section = args_match.group(1)
        for m in _GOOGLE_PARAM_RE.finditer(section):
            result[m.group(1)] = m.group(2).strip()
        if result:
            return result

    # Sphinx style
    for m in _SPHINX_PARAM_RE.finditer(docstring):
        result[m.group(1)] = m.group(2).strip()
    if result:
        return result

    # NumPy style: look for "Parameters\n----------" section
    numpy_match = _re.search(r"Parameters\s*\n\s*-{3,}\s*\n((?:.*\n?)+?)(?:\n\s*\n|\Z)", docstring)
    if numpy_match:
        section = numpy_match.group(1)
        for m in _NUMPY_PARAM_RE.finditer(section):
            result[m.group(1)] = m.group(2).strip()

    return result
