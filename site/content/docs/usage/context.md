---
title: Context & Global Options
nav_title: Context
description: Execution context with verbosity levels, output format, and custom global options.
weight: 56
draft: false
lang: en
tags: [context, global-options, verbosity]
keywords: [context, global, options, verbosity, verbose, quiet, color]
category: usage
icon: sliders
---

The `Context` carries execution metadata — verbosity level, output format, color preference, and user-defined global options — to every command handler.

## Injecting context

Add a `ctx: Context` parameter to any command handler. The CLI dispatcher injects it automatically and excludes it from argparse and MCP schemas:

```python
from milo import CLI, Context

cli = CLI(name="myapp")

@cli.command("build", description="Build the site")
def build(output: str = "_site", ctx: Context = None) -> str:
    ctx.log("Starting build...", level=1)  # only shown with --verbose
    ctx.log(f"Output dir: {output}", level=2)  # only shown with -vv
    return f"Built to {output}"
```

## Verbosity levels

The CLI maps flags to verbosity integers:

| Flag | `ctx.verbosity` | Property |
|---|---|---|
| `-q` / `--quiet` | -1 | `ctx.quiet == True` |
| *(default)* | 0 | — |
| `-v` / `--verbose` | 1 | `ctx.verbose == True` |
| `-vv` | 2 | `ctx.debug == True` |

Use `ctx.log()` to print messages at specific verbosity levels:

```python
ctx.log("Always shown unless quiet", level=0)
ctx.log("Verbose detail", level=1)
ctx.log("Debug trace", level=2)
```

Messages go to stderr, keeping stdout clean for structured output.

## Global options

Register CLI-wide options that are available on every command via `ctx.globals`:

```python
cli.global_option("environment", short="-e", default="local",
                  description="Target environment")
cli.global_option("dry_run", is_flag=True,
                  description="Simulate without making changes")
```

Access them in handlers:

```python
@cli.command("deploy", description="Deploy the app")
def deploy(service: str, ctx: Context = None) -> dict:
    env = ctx.globals.get("environment", "local")
    dry = ctx.globals.get("dry_run", False)
    if dry:
        return {"action": "dry-run", "service": service, "env": env}
    return {"action": "deployed", "service": service, "env": env}
```

```
myapp deploy --service api -e staging --dry-run
```

## get_context()

For library code that doesn't have direct access to the `ctx` parameter, use `get_context()`:

```python
from milo import get_context

def helper():
    ctx = get_context()
    ctx.log("Called from library code", level=1)
```

`get_context()` uses a `ContextVar` set by the CLI dispatcher. If no context has been set, it returns a default `Context`.

## Running interactive apps from commands

Use `ctx.run_app()` to launch an interactive `App` from within a CLI command handler. The command blocks while the app runs and receives the final state when it exits:

```python
from dataclasses import dataclass
from milo import CLI, Context, quit_on, with_cursor, with_confirm, SpecialKey

cli = CLI(name="picker")

@dataclass(frozen=True, slots=True)
class PickState:
    items: tuple[str, ...] = ("alpha", "beta", "gamma")
    cursor: int = 0

@with_confirm()
@with_cursor("items", wrap=True)
@quit_on(SpecialKey.ESCAPE)
def reducer(state, action):
    if state is None:
        return PickState()
    return state

@cli.command("pick", description="Pick an item")
def pick(ctx: Context = None) -> str:
    state = ctx.run_app(reducer, template="pick.kida", initial_state=PickState())
    return state.items[state.cursor]
```

This bridges the CLI dispatch layer with the Elm Architecture event loop — the command defines *what* to run, the app handles *how* to interact.

## Context fields

| Field | Type | Description |
|---|---|---|
| `verbosity` | `int` | -1=quiet, 0=normal, 1=verbose, 2=debug |
| `format` | `str` | Output format: `"plain"`, `"json"`, `"table"` |
| `color` | `bool` | Whether color output is enabled |
| `globals` | `dict` | Values from user-defined global options |

:::{tip}
Combine with [[docs/usage/config|Configuration]] to let global options control config loading — for example, a `--profile` option that selects a config profile.
:::
