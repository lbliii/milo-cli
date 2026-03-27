---
title: CLI & Commands
nav_title: CLI
description: AI-native CLI with typed commands, automatic argparse, MCP tools, and llms.txt.
weight: 50
draft: false
lang: en
tags: [cli, commands, ai-native, mcp]
keywords: [cli, command, decorator, argparse, mcp, llms-txt, ai-native]
category: usage
icon: terminal
---

Milo's `CLI` class turns decorated Python functions into CLI commands, MCP tools, and llms.txt entries — all from a single definition. Type annotations drive argument parsing, schema generation, and help text.

## Creating a CLI

```python
from milo import CLI

cli = CLI(name="myapp", description="My tool", version="1.0.0")
```

The `CLI` is the entry point for your application. It manages commands, groups, global options, and dispatches to handlers.

## Registering commands

Use the `@cli.command` decorator to register functions as CLI subcommands:

```python
@cli.command("greet", description="Say hello")
def greet(name: str, loud: bool = False) -> str:
    msg = f"Hello, {name}!"
    return msg.upper() if loud else msg
```

Type annotations are used to:

- Generate argparse arguments (`--name`, `--loud`)
- Generate MCP tool schemas for AI agents
- Determine required vs optional parameters (parameters with defaults are optional)

```
myapp greet --name Alice
myapp greet --name Alice --loud
```

## Command options

```python
@cli.command(
    "deploy",
    description="Deploy the application",
    aliases=("d",),          # Alternative names
    tags=("ops",),           # Grouping in llms.txt
    hidden=True,             # Omit from help and llms.txt
)
def deploy(target: str, dry_run: bool = False) -> dict: ...
```

## Supported parameter types

| Python type | argparse | JSON Schema |
|---|---|---|
| `str` | `--flag VALUE` | `"string"` |
| `int` | `--flag N` (type=int) | `"integer"` |
| `float` | `--flag N` (type=float) | `"number"` |
| `bool` | `--flag` (store_true) | `"boolean"` |
| `list[str]` | `--flag A B C` (nargs=*) | `"array"` |
| `X \| None` | optional | unwrapped to base type |

## Output formatting

Every command gets a `--format` flag automatically:

```
myapp greet --name Alice --format json
myapp greet --name Alice --format table
myapp greet --name Alice --format plain   # default
```

The handler's return value is serialized based on the chosen format. See [[docs/usage/output|Output Formatting]] for details.

## Running the CLI

```python
if __name__ == "__main__":
    cli.run()
```

`cli.run()` parses `sys.argv`, resolves the command, injects context, calls the handler, and formats the output.

## Built-in flags

Every CLI gets these flags automatically:

| Flag | Description |
|---|---|
| `--version` | Print version and exit |
| `--llms-txt` | Output an llms.txt AI discovery document |
| `--mcp` | Run as an MCP server (JSON-RPC on stdin/stdout) |
| `-v` / `--verbose` | Increase verbosity (stackable: `-vv` for debug) |
| `-q` / `--quiet` | Suppress non-error output |
| `--no-color` | Disable color output |

## Programmatic invocation

Call commands directly without going through argparse:

```python
result = cli.call("greet", name="Alice")
result = cli.call("site.build", output="_site")  # dotted paths for group commands
```

This is how the MCP server dispatches tool calls internally.

## Fuzzy matching

If a user mistypes a command, the CLI suggests the closest match:

```
$ myapp gret
Unknown command: 'gret'. Did you mean 'greet'?
```

:::{tip}
See [[docs/usage/groups|Command Groups]] for organizing commands into nested namespaces, [[docs/usage/context|Context]] for injecting execution context into handlers, and [[docs/usage/lazy|Lazy Loading]] for deferred imports.
:::
