---
title: Error Codes
nav_title: Errors
description: Structured errors for terminal output, tests, and MCP repair loops.
weight: 20
draft: false
lang: en
tags: [reference, errors, diagnostics]
keywords: [errors, error codes, exceptions, debugging, errorData]
category: reference
icon: warning
---

Milo errors carry namespaced codes and optional repair context. Human CLIs format
them for the terminal; MCP `tools/call` responses expose the same context in
`errorData` so agents can retry with corrected arguments.

## Base Type

All Milo errors derive from `MiloError`:

```python
from milo import ErrorCode, MiloError

raise MiloError(
    ErrorCode.FRM_VALIDATION,
    "Environment is required",
    argument="environment",
    constraint={"minLength": 1},
    suggestion="Provide a non-empty environment name.",
)
```

Constructor fields:

| Field | Type | Purpose |
|---|---|---|
| `code` | `ErrorCode` | Stable namespaced error code |
| `message` | `str` | Human-readable explanation |
| `suggestion` | `str` | Optional next step |
| `context` | `dict[str, object]` | Extra structured diagnostics |
| `docs_url` | `str` | Optional documentation link |
| `argument` | `str | None` | Parameter that failed |
| `constraint` | `dict | None` | JSON-Schema-style constraint that failed |

## Error Classes

| Exception | Subsystem |
|---|---|
| `InputError` | Command arguments, raw mode, key reading, escape parsing |
| `StateError` | Reducers, dispatch, sagas, combined state |
| `FormError` | Form fields, validation, submit behavior |
| `AppError` | App lifecycle, rendering, templates |
| `FlowError` | Flow screens and transitions |
| `DevError` | Dev server, file watching, hot reload |
| `ConfigError` | Config parsing, merging, validation, missing files |
| `PipelineError` | Pipeline phases, timeouts, dependencies |
| `PluginError` | Plugin loading and hooks |

## Error Codes

| Code | Name | Meaning |
|---|---|---|
| `M-INP-001` | `INP_RAW_MODE` | Failed to enter or restore raw terminal mode |
| `M-INP-002` | `INP_ESCAPE_PARSE` | Failed to parse an escape sequence |
| `M-INP-003` | `INP_READ` | Failed while reading terminal input |
| `M-INP-004` | `INP_REQUIRED_ARGUMENT` | Required command argument was omitted |
| `M-INP-005` | `INP_UNEXPECTED_ARGUMENT` | Command argument is not present in the generated schema |
| `M-INP-006` | `INP_ARGUMENT_TYPE` | Command argument could not be coerced to its schema type |
| `M-INP-007` | `INP_ARGUMENT_CONSTRAINT` | Command argument violates a schema constraint |
| `M-STA-001` | `STA_REDUCER` | Reducer raised or returned invalid state |
| `M-STA-002` | `STA_DISPATCH` | Dispatch failed |
| `M-STA-003` | `STA_SAGA` | Saga execution failed |
| `M-STA-004` | `STA_COMBINE` | Combined reducer failed |
| `M-APP-001` | `APP_LIFECYCLE` | App lifecycle failure |
| `M-APP-002` | `APP_RENDER` | Render failure |
| `M-APP-003` | `APP_TEMPLATE` | Template setup or lookup failure |
| `M-FRM-001` | `FRM_VALIDATION` | Form validation failure |
| `M-FRM-002` | `FRM_FIELD` | Invalid form field configuration |
| `M-FRM-003` | `FRM_SUBMIT` | Form submit failure |
| `M-FLW-001` | `FLW_TRANSITION` | Invalid or missing transition |
| `M-FLW-002` | `FLW_SCREEN` | Invalid screen |
| `M-FLW-003` | `FLW_DUPLICATE` | Duplicate flow entry |
| `M-DEV-001` | `DEV_WATCH` | File watching failure |
| `M-DEV-002` | `DEV_RELOAD` | Hot reload failure |
| `M-CFG-001` | `CFG_PARSE` | Config parse failure |
| `M-CFG-002` | `CFG_MERGE` | Config merge failure |
| `M-CFG-003` | `CFG_VALIDATE` | Config validation failure |
| `M-CFG-004` | `CFG_MISSING` | Required config value or file missing |
| `M-PIP-001` | `PIP_PHASE` | Pipeline phase failure |
| `M-PIP-002` | `PIP_TIMEOUT` | Pipeline timeout |
| `M-PIP-003` | `PIP_DEPENDENCY` | Pipeline dependency failure |
| `M-PLG-001` | `PLG_LOAD` | Plugin load failure |
| `M-PLG-002` | `PLG_HOOK` | Plugin hook failure |
| `M-CMD-001` | `CMD_NOT_FOUND` | Command was not found |
| `M-CMD-002` | `CMD_AMBIGUOUS` | Command resolution was ambiguous |
| `M-CMD-003` | `CMD_HOOK` | A before-command hook failed |
| `M-CMD-004` | `CMD_IMPORT` | A lazy command module or attribute failed to import |

## Terminal Formatting

`MiloError.format_compact()` keeps terminal output short and actionable:

```text
M-FRM-001 `environment`: Environment is required
  constraint: {'minLength': 1}
  hint: Provide a non-empty environment name.
```

Use `format_error(exc)` when boundary code needs to render arbitrary exceptions.
It uses `format_compact()` when available and falls back to `TypeError: ...`
style text for plain exceptions.

## MCP Tool Errors

MCP `tools/call` errors are returned as tool results, not JSON-RPC protocol
errors:

```json
{
  "content": [{"type": "text", "text": "Error: ..."}],
  "isError": true,
  "errorData": {
    "tool": "deploy",
    "errorCode": "M-FRM-001",
    "type": "MiloError",
    "argument": "environment",
    "constraint": {"minLength": 1},
    "example": "x",
    "suggestion": "Provide a non-empty environment name.",
    "schema": {"type": "object", "properties": {"environment": {"type": "string"}}}
  }
}
```

For plain Python `TypeError` from a missing required argument, Milo parses the
argument name and adds:

```json
{
  "argument": "name",
  "reason": "missing_required_argument",
  "suggestion": "Provide 'name'."
}
```

Agents should use `errorData.argument`, `errorData.constraint`,
`errorData.reason`, and `errorData.schema` to repair the next call. The
`content[0].text` field is for humans.

## JSON-RPC Protocol Errors

The stdin/stdout MCP server maps exceptions that escape method dispatch to
JSON-RPC error codes:

| Condition | JSON-RPC code |
|---|---|
| Invalid JSON | `-32700` parse error |
| Validation/config/form/input `MiloError` | `-32602` invalid params |
| `CMD_NOT_FOUND` | `-32601` method not found |
| Other exceptions | `-32603` internal error |

Most command handler failures should stay inside `tools/call` as `isError`
tool results with `errorData`.

## Raising Repairable Errors

Prefer structured errors at validation boundaries:

```python
from milo import ErrorCode, MiloError


def require_env(environment: str) -> None:
    if not environment:
        raise MiloError(
            ErrorCode.FRM_VALIDATION,
            "Environment is required",
            argument="environment",
            constraint={"minLength": 1},
            suggestion="Pass --environment staging or another non-empty value.",
        )
```

Do not raise broad plain exceptions when an agent could repair the call from a
specific argument and constraint.
