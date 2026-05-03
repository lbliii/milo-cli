---
title: From Typer
description: Move from type-hint CLI ergonomics to Milo's CLI/MCP/llms.txt contract.
weight: 30
draft: false
lang: en
tags: [migration, typer, cli, mcp]
keywords: [typer, migration, type hints, commands]
category: onboarding
icon: terminal
---

Typer and Milo both make Python type hints central to CLI authoring. The main
migration question is not syntax; it is contract surface. Milo adds MCP
`tools/list`, MCP `tools/call`, llms.txt discovery, structured error data, and
`milo verify` to the same typed function.

Official references: [Typer first steps](https://typer.tiangolo.com/tutorial/first-steps/) and [Typer command arguments](https://typer.tiangolo.com/tutorial/commands/arguments/).

## Before

```python milo-docs:compile
import typer

app = typer.Typer()


@app.command()
def greet(name: str, loud: bool = False):
    message = f"Hello, {name}!"
    print(message.upper() if loud else message)


if __name__ == "__main__":
    app()
```

## After

```python milo-docs:compile
from milo import CLI

cli = CLI(name="greeter", description="Greeting commands")


@cli.command("greet", description="Return a greeting")
def greet(name: str, loud: bool = False) -> str:
    """Greet someone.

    Args:
        name: Person to greet.
        loud: If true, SHOUT.
    """
    message = f"Hello, {name}!"
    return message.upper() if loud else message


if __name__ == "__main__":
    cli.run()
```

## Mapping

| Typer concept | Milo equivalent |
|---|---|
| `typer.run(main)` | `cli = CLI(...); @cli.command(...); cli.run()` |
| `app = typer.Typer()` | `cli = CLI(...)` |
| `@app.command()` | `@cli.command("name", description="...")` |
| Required argument from `name: str` | Required schema field from `name: str` |
| Option from `flag: bool = False` | Optional flag from `flag: bool = False` |
| Function docstring help | Function docstring plus `Args:` parameter descriptions |

## Add The Agent Contract

After migrating a Typer command, add these checks:

```bash
uv run python app.py --llms-txt
uv run milo verify app.py
uv run pytest tests/ -q
```

And test MCP dispatch directly:

```python milo-docs:compile
from milo.mcp import _call_tool


def test_mcp_dispatch():
    result = _call_tool(cli, {"name": "greet", "arguments": {"name": "Agent"}})
    assert result["content"][0]["text"] == "Hello, Agent!"
```

## What To Watch

- Replace output-first handlers with return values when agents need structured
  data.
- Document every public parameter. `milo verify` warns when schema fields lack
  descriptions.
- Keep interactive behavior behind `ctx.is_interactive` so MCP calls remain
  deterministic.
