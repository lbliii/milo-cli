---
title: Schema Contract
nav_title: Schema
description: How Milo derives JSON Schema from Python functions.
weight: 15
draft: false
lang: en
tags: [reference, schema, json-schema, annotations]
keywords: [schema, json schema, function_to_schema, return_to_schema, annotated]
category: reference
icon: code
---

`function_to_schema()` is Milo's single source of truth for MCP input schemas.
There is no parallel model layer: the Python function signature, annotations,
defaults, `Annotated[...]` metadata, and docstring determine the JSON Schema.

## Input Schema

```python
from typing import Annotated

from milo import CLI, Context, Description, MinLen

cli = CLI(name="deploy")


@cli.command("deploy", description="Deploy a service")
def deploy(
    environment: Annotated[str, MinLen(1), Description("Target environment")],
    service: Annotated[str, MinLen(1)],
    version: str = "latest",
    ctx: Context = None,
) -> dict[str, str]:
    """Deploy a service.

    Args:
        service: Service name.
        version: Version or image tag.
    """
    ctx.log(f"Deploying {service}", level=1)
    return {"environment": environment, "service": service, "version": version}
```

The MCP `inputSchema` contains `environment`, `service`, and `version`.
`ctx` is injected by Milo and is intentionally omitted.

## Required Fields

| Python parameter | Schema behavior |
|---|---|
| `name: str` | Required |
| `name: str = "World"` | Optional with `"default": "World"` |
| `name: str \| None` | Required unless it has a default; unwrapped to the base type |
| `name: str \| None = None` | Optional with `"default": null` |
| `ctx: Context = None` | Omitted from CLI and MCP schemas |

Only JSON-serializable defaults are emitted as schema defaults.

## Supported Types

| Python annotation | JSON Schema |
|---|---|
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[T]` | `{"type": "array", "items": ...}` |
| `tuple[T, ...]` | Array with item schema |
| `set[T]` / `frozenset[T]` | Array with `"uniqueItems": true` |
| `dict` | `{"type": "object"}` |
| `dict[str, T]` | Object with `additionalProperties` |
| `Enum` | String or integer enum, based on member values |
| `Literal[...]` | `{"type": ...,"enum": [...]}` when all values share a JSON type |
| `A \| B` | `{"anyOf": [...]}` |
| `dataclass` | Object with field properties |
| `TypedDict` | Object with key properties and required keys |

Unknown annotations fall back to `{"type": "string"}` and emit a warning unless
`strict=True` is passed.

## Annotated Constraints

Use `typing.Annotated` to add JSON Schema constraints without adding a model
class.

| Marker | Schema key |
|---|---|
| `MinLen(n)` | `minLength`, or `minItems` for arrays |
| `MaxLen(n)` | `maxLength`, or `maxItems` for arrays |
| `Gt(n)` | `exclusiveMinimum` |
| `Lt(n)` | `exclusiveMaximum` |
| `Ge(n)` | `minimum` |
| `Le(n)` | `maximum` |
| `Pattern(regex)` | `pattern` |
| `Description(text)` | `description` |

Docstring parameter descriptions are used when no `Description(...)` marker is
present. `milo verify` warns when public parameters are undocumented.

## Output Schema

`return_to_schema()` derives an MCP `outputSchema` from the return annotation.
Commands without a return annotation, or with `-> None`, do not get an
`outputSchema`.

```python
def status(service: str) -> dict[str, str]:
    return {"service": service, "state": "ok"}
```

For MCP calls, structured returns such as dicts, lists, numbers, and booleans
also appear as `structuredContent` in `tools/call` responses.

## Strict Mode

```python
from milo.schema import function_to_schema

schema = function_to_schema(command, strict=True)
```

Strict mode raises `TypeError` for unsupported annotations instead of falling
back to `"string"`. Use it in tests when schema drift would be worse than a hard
failure.

## Context Exclusion

A parameter named `ctx`, or annotated directly as `Context`, is not part of the
public input schema. Milo injects it at dispatch time for CLI, programmatic, and
MCP calls.

Prefer this form:

```python
def build(output: str = "_site", ctx: Context = None) -> dict[str, str]:
    ...
```

Do not expose context-like knobs to agents by adding separate schema fields.
