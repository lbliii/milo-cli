---
title: Dispatch Contract
nav_title: Dispatch
description: How CLI, programmatic, and MCP command calls agree.
weight: 18
draft: false
lang: en
tags: [reference, dispatch, cli, mcp]
keywords: [dispatch, invoke, call, call_raw, tools/call, command resolution]
category: reference
icon: workflow
---

Milo command handlers are resolved through one command registry. Human CLI
dispatch, programmatic dispatch, and MCP `tools/call` should agree on command
names, argument behavior, context injection, and returned values.

## One Command, Several Surfaces

```python
from milo import CLI, Context

cli = CLI(name="contract")


@cli.command("deploy", description="Deploy a service")
def deploy(environment: str, service: str, version: str = "latest",
           ctx: Context = None) -> dict[str, str]:
    return {"environment": environment, "service": service, "version": version}
```

| Surface | Example | Primary use |
|---|---|---|
| `cli.run()` | `python app.py deploy --environment staging --service api` | Real process CLI |
| `cli.invoke(argv)` | `cli.invoke(["deploy", "--environment", "staging", "--service", "api"])` | Tests and in-process argv dispatch |
| `cli.call(name, **kwargs)` | `cli.call("deploy", environment="staging", service="api")` | Programmatic public dispatch |
| `cli.call_raw(name, **kwargs)` | `cli.call_raw("deploy", environment="staging", service="api")` | Internal/raw dispatch used by MCP |
| MCP `tools/call` | `{"name": "deploy", "arguments": {...}}` | Agent tool invocation |

`cli.invoke()` returns an `InvokeResult` with `output`, `stderr`, `exit_code`,
`result`, and `exception`. `cli.call()` and `call_raw()` return the handler's
plain value or raise.

## Argument Contract

Every dispatch surface uses the command's `function_to_schema()` result before
the handler runs. Milo rejects missing and unexpected arguments, type errors,
enum mismatches, `Annotated` length and item limits, patterns, uniqueness, and
numeric bounds. Programmatic and MCP calls also coerce string-sourced integers,
numbers, booleans, JSON arrays, and JSON objects. Defaults and injected
`Context` parameters retain their normal Python behavior.

Unknown keyword arguments are errors rather than being silently discarded.
Programmatic calls raise `InputError`; CLI dispatch exits nonzero; MCP returns
structured `errorData`. Middleware may repair or inject arguments before the
shared validation step, but invalid values never reach the command handler.

## Groups

Grouped commands use spaces in argv and dot notation in programmatic/MCP calls.

```python
site = cli.group("site", description="Site commands")


@site.command("build", description="Build the site")
def build(output: str = "_site", clean: bool = False) -> dict[str, str | bool]:
    return {"output": output, "clean": clean}
```

| Surface | Name |
|---|---|
| CLI argv | `site build --output public --clean` |
| Programmatic | `cli.call("site.build", output="public", clean=True)` |
| MCP | `{"name": "site.build", "arguments": {"output": "public", "clean": true}}` |

## Context Injection

`Context` parameters are injected by dispatch and excluded from argparse and MCP
schemas. A handler can use `ctx.log()`, `ctx.error()`, `ctx.progress()`, or
`ctx.run_app()` without exposing `ctx` as a user argument.

## Return Values

| Return value | CLI default output | MCP `tools/call` |
|---|---|---|
| `str` | Printed as text | `content[0].text` |
| `dict` / `list` | Formatted by `--format` | Text plus `structuredContent` |
| `int` / `float` / `bool` | Formatted by `--format` | Text plus `structuredContent` |
| `None` | No structured value | Text content from serialization |
| Generator yielding `Progress` | Progress output, then final value | `notifications/progress`, then final value |

Use JSON-serializable return values for commands that agents or `--format json`
will consume.

## Error Behavior

`cli.invoke()` captures exceptions in `InvokeResult.exception` and sets a
nonzero `exit_code`. Programmatic calls raise exceptions. MCP `tools/call`
returns a tool error response:

```json
{
  "content": [{"type": "text", "text": "Error: ..."}],
  "isError": true,
  "errorData": {
    "tool": "deploy",
    "argument": "environment",
    "reason": "missing_required_argument",
    "schema": {"type": "object", "properties": {"environment": {"type": "string"}}}
  }
}
```

Agents should repair calls from `errorData`, not by parsing the human-readable
error text.

## Contract Tests

Use the four-layer testing pattern:

1. `function_to_schema(handler)` for schema truth.
2. `cli.invoke([...])` for argv parsing and formatted output.
3. `cli.call(...)` or `cli.call_raw(...)` for plain value dispatch.
4. `_call_tool(cli, {"name": ..., "arguments": ...})` for MCP behavior and
   structured `errorData`.

See [[docs/quality/testing|Testing]] for examples.
