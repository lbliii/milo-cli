---
title: From Python Fire
description: Narrow automatic Python object exposure into explicit Milo command contracts.
weight: 40
draft: false
lang: en
tags: [migration, fire, cli]
keywords: [python fire, migration, automatic cli, schema]
category: migration
icon: flame
---

Python Fire is optimized for turning Python objects into CLIs with very little
code. Milo is more explicit: only registered commands become public, and every
public command should have typed parameters, documentation, tests, and an MCP
schema.

Official reference: [Python Fire guide](https://google.github.io/python-fire/guide/).

## Before

```python milo-docs:compile
import fire


class Tasks:
    def add(self, title, priority="medium"):
        return {"title": title, "priority": priority}

    def list(self):
        return []


if __name__ == "__main__":
    fire.Fire(Tasks)
```

## After

```python milo-docs:compile
from typing import Literal

from milo import CLI

cli = CLI(name="tasks", description="Task commands")


@cli.command("add", description="Add a task")
def add(title: str, priority: Literal["low", "medium", "high"] = "medium") -> dict[str, str]:
    """Add a task.

    Args:
        title: Task title.
        priority: Task priority.
    """
    return {"title": title, "priority": priority}


@cli.command("list", description="List tasks", annotations={"readOnlyHint": True})
def list_tasks() -> list[dict[str, str]]:
    return []


if __name__ == "__main__":
    cli.run()
```

## Mapping

| Fire concept | Milo equivalent |
|---|---|
| `fire.Fire()` exposing module contents | Register only the intended public commands |
| `fire.Fire(component)` | `CLI(...)` plus explicit command decorators |
| Object methods as commands | Top-level functions or grouped commands |
| Runtime value parsing | Type annotations and `Annotated[...]` schema constraints |
| Printed or stringified objects | JSON-serializable return values |

## What To Watch

- Fire can expose more than you intended. Treat migration as an allowlist: only
  decorate commands that humans and agents should call.
- Fire's value parsing is convenient for local exploration. For agent-facing
  tools, prefer explicit annotations so schemas can be validated before calls.
- Rename ambiguous methods before exposing them. Agents do better with command
  names and parameter descriptions that say what to do next.
