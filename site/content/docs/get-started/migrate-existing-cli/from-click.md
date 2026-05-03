---
title: From Click
description: Translate Click command decorators, options, groups, and context into Milo.
weight: 20
draft: false
lang: en
tags: [migration, click, cli]
keywords: [click, migration, command, option, group, context]
category: onboarding
icon: terminal
---

Click and Milo both use decorators, but they put the contract in different
places. Click attaches CLI metadata through stacked decorators such as
`@click.option`; Milo keeps the public contract in the Python signature,
`Annotated[...]` metadata, defaults, and docstring.

Official references: [Click commands and groups](https://click.palletsprojects.com/en/stable/commands-and-groups/) and [Click arguments](https://click.palletsprojects.com/en/stable/arguments/).

## Before

```python milo-docs:compile
import click


@click.group()
def cli():
    pass


@cli.command()
@click.option("--environment", required=True)
@click.option("--service", required=True)
@click.option("--version", default="latest")
def deploy(environment: str, service: str, version: str):
    click.echo({"environment": environment, "service": service, "version": version})
```

## After

```python milo-docs:compile
from typing import Annotated

from milo import CLI, Description, MinLen

cli = CLI(name="deployer", description="Deploy services")


@cli.command("deploy", description="Deploy a service")
def deploy(
    environment: Annotated[str, MinLen(1), Description("Target environment")],
    service: Annotated[str, MinLen(1), Description("Service name")],
    version: str = "latest",
) -> dict[str, str]:
    return {"environment": environment, "service": service, "version": version}


if __name__ == "__main__":
    cli.run()
```

## Mapping

| Click concept | Milo equivalent |
|---|---|
| `@click.command()` | `@cli.command("name", description="...")` |
| `@click.option("--name", default=...)` | `name: T = default` |
| `@click.option("--name", required=True)` | `name: T` |
| `@click.argument("name")` | Usually `name: T`; document any compatibility wrapper if argv shape must remain positional |
| `@click.group()` | `group = cli.group("name", description="...")` |
| `click.echo(...)` | Return structured values, or use `Context` output helpers |
| `click.Context` / `pass_context` | `ctx: Context = None` injection |

## Groups

```python milo-docs:compile
from milo import CLI

cli = CLI(name="repo")
remote = cli.group("remote", description="Manage remotes")


@remote.command("list", description="List remotes")
def list_remotes() -> list[str]:
    return ["origin"]
```

CLI users run `repo remote list`. Programmatic and MCP callers use
`remote.list`.

## What To Watch

- Click decorators can hide contract details above the function. In Milo,
  contract review starts at the function signature.
- Avoid writing normal command output with `print()` or `click.echo()` in code
  that may run under MCP. Return values are safer for agents and `--format json`.
- If you rely on Click's exact positional argument behavior, migrate that
  command with a compatibility test before changing user-facing argv shape.
