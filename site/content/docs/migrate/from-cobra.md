---
title: From Cobra
description: Map Cobra command trees, flags, and generated app structure into Milo groups.
weight: 50
draft: false
lang: en
tags: [migration, cobra, cli, go]
keywords: [cobra, migration, go cli, groups, flags]
category: migration
icon: network
---

Cobra is a Go CLI framework built around command structs, generated files, and
flag binding. Milo is a Python framework built around typed functions. Migrating
from Cobra is usually a rewrite of command handlers, not a mechanical port.

Official references: [Cobra getting started](https://cobra.dev/docs/tutorials/getting-started/) and [Cobra flags guide](https://cobra.dev/docs/how-to-guides/working-with-flags/).

## Command Trees

Cobra command trees map cleanly to Milo groups:

```python milo-docs:compile
from milo import CLI

cli = CLI(name="cloud", description="Cloud operations")
cluster = cli.group("cluster", description="Cluster commands")
node = cluster.group("node", description="Node commands")


@node.command("drain", description="Drain a node")
def drain(name: str, force: bool = False) -> dict[str, str | bool]:
    """Drain a node.

    Args:
        name: Node name.
        force: Skip confirmation checks.
    """
    return {"name": name, "force": force, "status": "draining"}
```

| Surface | Name |
|---|---|
| CLI | `cloud cluster node drain --name node-1 --force` |
| Programmatic | `cli.call("cluster.node.drain", name="node-1", force=True)` |
| MCP | `{"name": "cluster.node.drain", "arguments": {"name": "node-1", "force": true}}` |

## Mapping

| Cobra concept | Milo equivalent |
|---|---|
| Root command | `CLI(name=..., description=...)` |
| Subcommand | `cli.group(...)` or `@group.command(...)` |
| Local flag | Function parameter with a default |
| Required flag | Function parameter without a default |
| Persistent flag | `Context`, config loading, or explicit parameter passed to each command |
| `RunE` returning error | Raise `MiloError` or another exception; MCP receives structured tool errors |
| Generated command file | Plain Python module with typed command functions |

## What To Watch

- Cobra's persistent flags are convenient but can hide command contracts. In
  Milo, prefer explicit parameters when agents need to see the value in schema.
- If a Cobra command relies on global mutable state, move that state to config,
  injected context, or an explicit boundary before making MCP calls concurrent.
- Preserve command names and aliases only when users depend on them. Agents care
  more about clear names, descriptions, and repairable errors than exact legacy
  flag layout.
