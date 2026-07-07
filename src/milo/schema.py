"""Function signature → JSON Schema for MCP tool compatibility."""

from __future__ import annotations

import dataclasses
import enum
import functools
import inspect
import json
import math
import re as _re
import types
import typing
import warnings
from collections.abc import Callable, Mapping
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


@dataclasses.dataclass(frozen=True, slots=True)
class Positional:
    """Present an ``Annotated`` parameter as a positional CLI argument."""

    metavar: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class Option:
    """Customize an ``Annotated`` CLI option without changing its schema name."""

    aliases: tuple[str, ...] = ()
    metavar: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "aliases", tuple(self.aliases))
        invalid = [alias for alias in self.aliases if not alias.startswith("-")]
        if invalid:
            msg = f"Option aliases must start with '-': {invalid!r}"
            raise ValueError(msg)


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


def function_to_schema(
    func: Callable[..., Any],
    *,
    strict: bool = False,
    warn_missing_docs: bool = False,
) -> dict[str, Any]:
    """Generate MCP-compatible JSON Schema from function type annotations.

    Parameters with defaults are optional (not in required).
    X | None unions unwrapped to base type.
    Supports: str, int, float, bool, list[X], dict[str, X], X | None,
    Enum, Literal, dataclass, TypedDict, Union.

    Parameter descriptions are extracted from the function's docstring
    (Google, NumPy, or Sphinx style) and included as ``"description"``
    fields in the schema properties.

    ``Context``-typed parameters (and any parameter named ``ctx``) are
    intentionally omitted from the returned schema. The CLI dispatcher
    injects them at call time, so they are invisible to MCP clients and
    should not appear in ``tools/list`` descriptors. See
    :func:`_is_context_type` for the exact detection rules.

    When *strict* is True, unrecognized type annotations raise
    :class:`TypeError` instead of silently falling back to ``"string"``.

    When *warn_missing_docs* is True, every schema parameter without a
    description (no ``Args:`` entry and no ``Annotated[..., Description(...)]``)
    emits a :class:`UserWarning`. Default ``False`` so production schema
    generation stays silent; ``milo verify`` opts in.
    """
    schema, undocumented = _function_to_schema_cached(func, strict=strict)
    if warn_missing_docs:
        for name in undocumented:
            warnings.warn(
                f"Parameter {name!r} has no description; "
                f"add an 'Args:' entry to the docstring or "
                f"Annotated[..., Description(...)] to the type",
                UserWarning,
                stacklevel=2,
            )
    return schema


def validate_arguments(
    schema: dict[str, Any],
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and coerce command arguments against Milo's JSON Schema.

    The returned mapping is a new dictionary. String inputs are coerced only
    when the schema declares a non-string primitive, array, or object type.
    Unknown and missing arguments are rejected before handler execution.
    """
    properties = schema.get("properties", {})
    required = schema.get("required", ())

    for name in arguments:
        if name not in properties:
            _raise_argument_error(
                code_name="INP_UNEXPECTED_ARGUMENT",
                argument=name,
                message=f"Unexpected argument {name!r}.",
                constraint={"additionalProperties": False},
                reason="unexpected_argument",
                suggestion=f"Remove {name!r}; it is not declared by this command.",
            )

    for name in required:
        if name not in arguments:
            _raise_argument_error(
                code_name="INP_REQUIRED_ARGUMENT",
                argument=name,
                message=f"Missing required argument {name!r}.",
                constraint={"required": True},
                reason="missing_required_argument",
                suggestion=f"Provide {name!r}.",
            )

    validated = {
        name: _validate_schema_value(value, properties[name], argument=name, root=schema)
        for name, value in arguments.items()
    }
    for name, value_schema in properties.items():
        if (
            name not in arguments
            and "default" in value_schema
            and value_schema["default"] is not None
        ):
            _validate_schema_value(
                value_schema["default"], value_schema, argument=name, root=schema
            )
    return validated


def _validate_schema_value(
    value: Any,
    value_schema: dict[str, Any],
    *,
    argument: str,
    root: dict[str, Any],
) -> Any:
    value_schema = _resolve_schema_ref(value_schema, root)

    if value is None and value_schema.get("default", object()) is None:
        return None

    if "anyOf" in value_schema:
        from milo._errors import InputError

        for candidate in value_schema["anyOf"]:
            try:
                return _validate_schema_value(value, candidate, argument=argument, root=root)
            except InputError:
                continue
        _raise_argument_error(
            code_name="INP_ARGUMENT_TYPE",
            argument=argument,
            message=f"Argument {argument!r} does not match any allowed type.",
            constraint={"anyOf": value_schema["anyOf"]},
            reason="type_mismatch",
            suggestion="Use a value matching one of the declared schema alternatives.",
        )

    expected = value_schema.get("type")
    coerced = _coerce_schema_type(value, expected, argument=argument)

    if "enum" in value_schema and coerced not in value_schema["enum"]:
        _raise_constraint_error(
            argument,
            "enum",
            value_schema["enum"],
            f"Use one of: {', '.join(map(repr, value_schema['enum']))}.",
        )

    if expected == "string":
        _validate_string_constraints(coerced, value_schema, argument)
    elif expected in {"integer", "number"}:
        _validate_number_constraints(coerced, value_schema, argument)
    elif expected == "array":
        _validate_array_constraints(coerced, value_schema, argument, root)
    elif expected == "object":
        coerced = _validate_object_constraints(coerced, value_schema, argument, root)

    return coerced


def _resolve_schema_ref(value_schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = value_schema.get("$ref")
    prefix = "#/$defs/"
    if not isinstance(ref, str) or not ref.startswith(prefix):
        return value_schema
    resolved = root.get("$defs", {}).get(ref.removeprefix(prefix))
    return resolved if isinstance(resolved, dict) else value_schema


def _coerce_schema_type(value: Any, expected: Any, *, argument: str) -> Any:
    if expected is None:
        return value

    coerced = value
    try:
        if expected == "string":
            if not isinstance(value, str):
                raise TypeError
        elif expected == "integer":
            if isinstance(value, bool):
                raise TypeError
            if isinstance(value, str):
                coerced = int(value)
            elif not isinstance(value, int):
                raise TypeError
        elif expected == "number":
            if isinstance(value, bool):
                raise TypeError
            if isinstance(value, str):
                coerced = float(value)
            elif not isinstance(value, (int, float)):
                raise TypeError
            if not math.isfinite(coerced):
                raise TypeError
        elif expected == "boolean":
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"true", "1", "yes", "on"}:
                    coerced = True
                elif normalized in {"false", "0", "no", "off"}:
                    coerced = False
                else:
                    raise TypeError
            elif not isinstance(value, bool):
                raise TypeError
        elif expected == "null":
            if value is not None:
                raise TypeError
        elif expected == "array":
            if isinstance(value, str):
                coerced = json.loads(value)
            elif isinstance(value, (list, tuple, set, frozenset)):
                coerced = list(value)
            if not isinstance(coerced, list):
                raise TypeError
        elif expected == "object":
            if isinstance(value, str):
                coerced = json.loads(value)
            if not isinstance(coerced, dict):
                raise TypeError
    except TypeError, ValueError:
        _raise_argument_error(
            code_name="INP_ARGUMENT_TYPE",
            argument=argument,
            message=f"Argument {argument!r} must be of type {expected!r}.",
            constraint={"type": expected},
            reason="type_mismatch",
            suggestion=f"Provide {argument!r} as {expected}.",
        )
    return coerced


def _validate_string_constraints(value: str, value_schema: dict[str, Any], argument: str) -> None:
    if "minLength" in value_schema and len(value) < value_schema["minLength"]:
        _raise_constraint_error(
            argument,
            "minLength",
            value_schema["minLength"],
            f"Use at least {value_schema['minLength']} character(s).",
        )
    if "maxLength" in value_schema and len(value) > value_schema["maxLength"]:
        _raise_constraint_error(
            argument,
            "maxLength",
            value_schema["maxLength"],
            f"Use at most {value_schema['maxLength']} character(s).",
        )
    if "pattern" in value_schema and _re.search(value_schema["pattern"], value) is None:
        _raise_constraint_error(
            argument,
            "pattern",
            value_schema["pattern"],
            f"Use text matching /{value_schema['pattern']}/.",
        )


def _validate_number_constraints(
    value: int | float, value_schema: dict[str, Any], argument: str
) -> None:
    checks = (
        ("minimum", lambda bound: value >= bound, "greater than or equal to"),
        ("maximum", lambda bound: value <= bound, "less than or equal to"),
        ("exclusiveMinimum", lambda bound: value > bound, "greater than"),
        ("exclusiveMaximum", lambda bound: value < bound, "less than"),
    )
    for key, predicate, wording in checks:
        if key in value_schema and not predicate(value_schema[key]):
            _raise_constraint_error(
                argument,
                key,
                value_schema[key],
                f"Use a value {wording} {value_schema[key]}.",
            )


def _validate_array_constraints(
    value: list[Any],
    value_schema: dict[str, Any],
    argument: str,
    root: dict[str, Any],
) -> None:
    if "minItems" in value_schema and len(value) < value_schema["minItems"]:
        _raise_constraint_error(
            argument,
            "minItems",
            value_schema["minItems"],
            f"Provide at least {value_schema['minItems']} item(s).",
        )
    if "maxItems" in value_schema and len(value) > value_schema["maxItems"]:
        _raise_constraint_error(
            argument,
            "maxItems",
            value_schema["maxItems"],
            f"Provide at most {value_schema['maxItems']} item(s).",
        )
    if value_schema.get("uniqueItems") and any(
        left == right for index, left in enumerate(value) for right in value[index + 1 :]
    ):
        _raise_constraint_error(
            argument,
            "uniqueItems",
            True,
            "Remove duplicate items.",
        )
    item_schema = value_schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            value[index] = _validate_schema_value(
                item,
                item_schema,
                argument=f"{argument}[{index}]",
                root=root,
            )


def _validate_object_constraints(
    value: dict[str, Any],
    value_schema: dict[str, Any],
    argument: str,
    root: dict[str, Any],
) -> dict[str, Any]:
    properties = value_schema.get("properties", {})
    required = value_schema.get("required", ())
    for name in required:
        if name not in value:
            _raise_argument_error(
                code_name="INP_REQUIRED_ARGUMENT",
                argument=f"{argument}.{name}",
                message=f"Missing required field {name!r} in {argument!r}.",
                constraint={"required": True},
                reason="missing_required_argument",
                suggestion=f"Provide {argument}.{name!s}.",
            )

    validated = dict(value)
    for name, item in value.items():
        if name in properties:
            validated[name] = _validate_schema_value(
                item,
                properties[name],
                argument=f"{argument}.{name}",
                root=root,
            )
        elif value_schema.get("additionalProperties") is False:
            _raise_argument_error(
                code_name="INP_UNEXPECTED_ARGUMENT",
                argument=f"{argument}.{name}",
                message=f"Unexpected field {name!r} in {argument!r}.",
                constraint={"additionalProperties": False},
                reason="unexpected_argument",
                suggestion=f"Remove {argument}.{name!s}.",
            )
        elif isinstance(value_schema.get("additionalProperties"), dict):
            validated[name] = _validate_schema_value(
                item,
                value_schema["additionalProperties"],
                argument=f"{argument}.{name}",
                root=root,
            )
    return validated


def _raise_constraint_error(
    argument: str,
    key: str,
    expected: Any,
    suggestion: str,
) -> typing.NoReturn:
    _raise_argument_error(
        code_name="INP_ARGUMENT_CONSTRAINT",
        argument=argument,
        message=f"Argument {argument!r} violates {key}={expected!r}.",
        constraint={key: expected},
        reason="constraint_violation",
        suggestion=suggestion,
    )


def _raise_argument_error(
    *,
    code_name: str,
    argument: str,
    message: str,
    constraint: dict[str, Any],
    reason: str,
    suggestion: str,
) -> typing.NoReturn:
    from milo._errors import ErrorCode, InputError

    raise InputError(
        ErrorCode[code_name],
        message,
        argument=argument,
        constraint=constraint,
        context={"reason": reason},
        suggestion=suggestion,
    )


@functools.lru_cache(maxsize=256)
def _function_to_schema_cached(
    func: Callable[..., Any], *, strict: bool = False
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Compute (schema, undocumented_param_names). Cached; warnings live in the wrapper."""
    sig = inspect.signature(func)
    # Resolve string annotations (from __future__ import annotations)
    # include_extras=True preserves Annotated metadata for constraint extraction
    try:
        hints = typing.get_type_hints(func, include_extras=True)
    except NameError:
        # Forward references that can't be resolved — fall back to signature annotations
        warnings.warn(
            f"Could not resolve type hints for {func.__qualname__}: unresolved forward reference. "
            f"Schema will fall back to raw signature annotations.",
            stacklevel=2,
        )
        hints = {}
    except Exception:
        warnings.warn(
            f"Could not resolve type hints for {func.__qualname__}. "
            f"Schema will fall back to raw signature annotations.",
            stacklevel=2,
        )
        hints = {}

    # Extract parameter descriptions from docstring
    param_docs = _parse_param_docs(func.__doc__) if func.__doc__ else {}

    properties: dict[str, Any] = {}
    required: list[str] = []
    defs: dict[str, dict[str, Any]] = {}
    undocumented: list[str] = []

    for name, param in sig.parameters.items():
        if param.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
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

        prop = _type_to_schema(annotation, _defs=defs, _strict=strict)

        # Add description from docstring if available
        if name in param_docs:
            prop["description"] = param_docs[name]

        # Track params that ended up with no description from any source
        # (no Args entry and no Annotated[..., Description(...)]). The wrapper
        # turns this into UserWarnings when warn_missing_docs=True.
        if "description" not in prop:
            undocumented.append(name)

        properties[name] = prop

        has_default = param.default is not inspect.Parameter.empty
        if has_default and isinstance(
            param.default, (str, int, float, bool, type(None), list, dict)
        ):
            try:
                json.dumps(param.default)
            except TypeError, ValueError:
                pass  # non-serializable nested value — omit default
            else:
                prop["default"] = param.default
        if not has_default:
            required.append(name)

    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    if defs:
        result["$defs"] = defs
    return result, tuple(undocumented)


def _type_to_schema(
    annotation: Any,
    _seen: set[int] | None = None,
    _defs: dict[str, dict[str, Any]] | None = None,
    *,
    _strict: bool = False,
) -> dict[str, Any]:
    """Convert Python type annotation to JSON Schema fragment.

    *_defs* accumulates ``$defs`` entries for recursive dataclasses so
    they can be emitted as ``{"$ref": "#/$defs/ClassName"}``.

    When *_strict* is True, unrecognized types raise TypeError.
    """
    # Annotated[T, constraints...] — unwrap and apply constraints
    origin = get_origin(annotation)
    if origin is typing.Annotated:
        args = get_args(annotation)
        base_type = args[0]
        schema = _type_to_schema(base_type, _seen, _defs, _strict=_strict)
        is_array = schema.get("type") == "array"
        for meta in args[1:]:
            if isinstance(meta, Positional):
                if "x-milo-cli" in schema:
                    raise ValueError("Use only one Positional or Option marker per parameter")
                schema["x-milo-cli"] = {
                    "kind": "positional",
                    **({"metavar": meta.metavar} if meta.metavar else {}),
                }
                continue
            if isinstance(meta, Option):
                if "x-milo-cli" in schema:
                    raise ValueError("Use only one Positional or Option marker per parameter")
                schema["x-milo-cli"] = {
                    "kind": "option",
                    **({"aliases": list(meta.aliases)} if meta.aliases else {}),
                    **({"metavar": meta.metavar} if meta.metavar else {}),
                }
                continue
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
        values = list(get_args(annotation))
        schema: dict[str, Any] = {"enum": values}
        if values and all(isinstance(v, bool) for v in values):
            schema["type"] = "boolean"
        elif values and all(isinstance(v, int) and not isinstance(v, bool) for v in values):
            schema["type"] = "integer"
        elif values and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in values
        ):
            schema["type"] = "number"
        elif values and all(isinstance(v, str) for v in values):
            schema["type"] = "string"
        return schema

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
            props[f.name] = _type_to_schema(field_type, _seen, _defs, _strict=_strict)
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
            props[fname] = _type_to_schema(ftype, _seen, _defs, _strict=_strict)
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
            return {"anyOf": [_type_to_schema(a, _seen, _defs, _strict=_strict) for a in non_none]}
        if len(non_none) == 1:
            return _type_to_schema(non_none[0], _seen, _defs, _strict=_strict)

    # list[T] with recursive item schema
    if origin is list:
        args = get_args(annotation)
        if args:
            return {
                "type": "array",
                "items": _type_to_schema(args[0], _seen, _defs, _strict=_strict),
            }
        return {"type": "array"}

    # tuple[T, ...] → array with items
    if origin is tuple:
        args = get_args(annotation)
        if args:
            # tuple[T, ...] (homogeneous) or tuple[T] (single-element)
            non_ellipsis = [a for a in args if a is not Ellipsis]
            if non_ellipsis:
                return {
                    "type": "array",
                    "items": _type_to_schema(non_ellipsis[0], _seen, _defs, _strict=_strict),
                }
        return {"type": "array"}

    # set[T] / frozenset[T] → array with uniqueItems
    if origin is set or origin is frozenset:
        args = get_args(annotation)
        schema: dict[str, Any] = {"type": "array", "uniqueItems": True}
        if args:
            schema["items"] = _type_to_schema(args[0], _seen, _defs, _strict=_strict)
        return schema

    # dict[str, V] with additionalProperties
    if origin is dict:
        args = get_args(annotation)
        if args and len(args) == 2:
            return {
                "type": "object",
                "additionalProperties": _type_to_schema(args[1], _seen, _defs, _strict=_strict),
            }
        return {"type": "object"}

    # Unknown type
    type_name = getattr(annotation, "__name__", None) or str(annotation)
    if _strict:
        raise TypeError(
            f"Unrecognized type {type_name!r} in strict schema mode. "
            f"Add explicit schema support or use strict=False."
        )
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
    except NameError:
        hints = {}
    except Exception:
        warnings.warn(
            f"Could not resolve return type hints for {func.__qualname__}.",
            stacklevel=2,
        )
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
