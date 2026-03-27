---
title: Output Formatting
nav_title: Output
description: Structured output with plain, JSON, table, and template formats.
weight: 52
draft: false
lang: en
tags: [output, formatting, json, table]
keywords: [output, format, plain, json, table, template, formatting]
category: usage
icon: layout
---

Milo formats command return values based on the `--format` flag. Every command registered with `@cli.command` automatically supports `--format plain|json|table`.

## Formats

### Plain (default)

Human-readable output. Dicts show aligned key-value pairs, lists show one item per line:

```python
@cli.command("info", description="Show info")
def info() -> dict:
    return {"name": "myapp", "version": "1.0.0", "status": "healthy"}
```

```
$ myapp info
  name     myapp
  version  1.0.0
  status   healthy
```

### JSON

Structured JSON output for piping to other tools:

```
$ myapp info --format json
{
  "name": "myapp",
  "version": "1.0.0",
  "status": "healthy"
}
```

### Table

Tabular output for lists of dicts. Uses kida's table filter when available, with a simple column-aligned fallback:

```python
@cli.command("list", description="List items")
def list_items() -> list[dict]:
    return [
        {"id": 1, "name": "Alpha", "status": "active"},
        {"id": 2, "name": "Beta", "status": "pending"},
    ]
```

```
$ myapp list --format table
id  name   status
--  -----  -------
1   Alpha  active
2   Beta   pending
```

### Template

Render through a kida template:

```python
from milo import format_output

output = format_output(data, fmt="template", template="report.kida")
```

## Using format_output directly

For custom formatting outside the CLI dispatcher:

```python
from milo import format_output

text = format_output({"key": "value"}, fmt="json")
```

## write_output

`write_output` formats and writes to stdout in one call:

```python
from milo import write_output

write_output(data, fmt="table")
```

This is what the CLI dispatcher calls after each command handler returns.
