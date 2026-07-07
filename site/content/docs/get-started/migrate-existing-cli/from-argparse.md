---
title: From argparse
description: Replace parser-first argparse code with typed Milo command handlers.
weight: 10
draft: false
lang: en
tags: [migration, argparse, cli]
keywords: [argparse, migration, parser, ArgumentParser]
category: onboarding
icon: terminal
---

`argparse` is parser-first: you create an `ArgumentParser`, attach arguments,
parse `sys.argv`, then call your own function. Milo is handler-first: write the
function contract once, then let Milo derive argv parsing, MCP schema, and
llms.txt.

Official reference: [argparse documentation](https://docs.python.org/3/library/argparse.html).

## Before

```python milo-docs:compile
import argparse


def deploy(environment: str, service: str, version: str) -> dict[str, str]:
    return {"environment": environment, "service": service, "version": version}


parser = argparse.ArgumentParser(prog="deployer")
parser.add_argument("environment")
parser.add_argument("service")
parser.add_argument("--version", default="latest")
args = parser.parse_args()
print(deploy(args.environment, args.service, args.version))
```

## After

```python milo-docs:compile
from typing import Annotated

from milo import CLI, Positional

cli = CLI(name="deployer", description="Deploy services")


@cli.command("deploy", description="Deploy a service")
def deploy(
    environment: Annotated[str, Positional("ENVIRONMENT")],
    service: Annotated[str, Positional("SERVICE")],
    version: str = "latest",
) -> dict[str, str]:
    """Deploy a service.

    Args:
        environment: Target environment.
        service: Service name.
        version: Version or image tag.
    """
    return {"environment": environment, "service": service, "version": version}


if __name__ == "__main__":
    cli.run()
```

Run it:

```bash
uv run python app.py deploy staging api
uv run python app.py deploy staging api --format json
uv run python app.py --llms-txt
uv run milo verify app.py
```

## Mapping

| argparse concept | Milo equivalent |
|---|---|
| `ArgumentParser(prog=..., description=...)` | `CLI(name=..., description=...)` |
| `add_argument("name")` | `name: Annotated[str, Positional("NAME")]` |
| `add_argument("--name", default="x")` | Defaulted parameter: `name: str = "x"` |
| `type=int` | Annotation: `count: int` |
| `choices=[...]` | `Literal[...]` or `Enum` |
| `parser.parse_args()` | `cli.run()` for processes, `cli.invoke([...])` for tests |
| `Namespace` | Function parameters |

## What To Watch

- Parameters become named CLI options by default. Use `Positional(...)` to
  preserve established argv; MCP and programmatic callers still use the Python
  parameter name.
- Use `Option(aliases=("-x",))` to preserve existing option spellings and
  `surfaces=("cli",)` for long-running commands that should not be MCP tools.
- `print()` output is process output. For agent-facing commands, prefer
  structured returns and `Context` output helpers.
- Parser errors become structured Milo/MCP diagnostics when the command is
  called through `tools/call`.
