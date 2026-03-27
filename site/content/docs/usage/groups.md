---
title: Command Groups
nav_title: Groups
description: Nested command groups for hierarchical CLI structures.
weight: 55
draft: false
lang: en
tags: [groups, commands, nesting, hierarchy]
keywords: [groups, nested, subcommands, hierarchy, namespace]
category: usage
icon: folder-tree
---

Groups organize commands into namespaces, creating a hierarchical CLI structure. Each group becomes a subcommand that has its own subcommands.

## Creating groups

```python
from milo import CLI

cli = CLI(name="myapp", description="My tool")

site = cli.group("site", description="Site operations")

@site.command("build", description="Build the site")
def build(output: str = "_site") -> str:
    return f"Building to {output}"

@site.command("serve", description="Start dev server")
def serve(port: int = 8080) -> str:
    return f"Serving on port {port}"
```

```
myapp site build --output dist
myapp site serve --port 3000
```

## Nesting groups

Groups can contain sub-groups to any depth:

```python
config = site.group("config", description="Config management")

@config.command("show", description="Show merged config")
def config_show() -> dict:
    return {"theme": "dark", "lang": "en"}

@config.command("set", description="Update a config value")
def config_set(key: str, value: str) -> dict:
    return {"updated": key, "value": value}
```

```
myapp site config show
myapp site config set --key theme --value light
```

## Group aliases

Groups support aliases just like commands:

```python
site = cli.group("site", description="Site operations", aliases=("s",))
config = site.group("config", description="Config management", aliases=("cfg",))
```

```
myapp s build              # same as: myapp site build
myapp s cfg show           # same as: myapp site config show
```

## Dotted paths

Commands in groups are addressable via dotted paths for programmatic access:

```python
cmd = cli.get_command("site.build")
cmd = cli.get_command("site.config.show")

result = cli.call("site.build", output="dist")
```

## Walking all commands

`walk_commands()` traverses the entire command tree, yielding dotted paths:

```python
for path, cmd in cli.walk_commands():
    print(f"{path}: {cmd.description}")

# Output:
# greet: Say hello
# site.build: Build the site
# site.serve: Start dev server
# site.config.show: Show merged config
```

This is used by `--llms-txt` and `--mcp` to discover all commands including those inside groups.

## Adding external groups

Groups can be defined separately and added later:

```python
from milo import Group

db = Group("db", description="Database operations")

@db.command("migrate", description="Run migrations")
def migrate() -> str: ...

@db.command("seed", description="Seed test data")
def seed() -> str: ...

cli.add_group(db)
```

## Freezing groups

Convert a mutable `Group` to an immutable `GroupDef` snapshot:

```python
frozen = site.to_def()
print(frozen.name)      # "site"
print(frozen.commands)   # {"build": CommandDef(...), ...}
print(frozen.groups)     # {"config": GroupDef(...)}
```

:::{tip}
Groups integrate fully with `--llms-txt` (nested headings), `--mcp` (dot-notation tool names), and help output. All commands in groups are discoverable by AI agents.
:::
