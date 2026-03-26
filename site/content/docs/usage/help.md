---
title: Help Rendering
nav_title: Help
description: Drop-in argparse HelpFormatter using Kida templates.
weight: 90
draft: false
lang: en
tags: [help, argparse, cli]
keywords: [help, argparse, formatter, cli, help text]
category: usage
icon: question
---

Milo provides `HelpRenderer`, a drop-in `argparse.HelpFormatter` subclass that renders help output through [[ext:kida:|Kida]] templates for styled terminal output.

## Usage

```python
import argparse
from milo import HelpRenderer

parser = argparse.ArgumentParser(
    prog="myapp",
    description="My CLI tool",
    formatter_class=HelpRenderer,
)
parser.add_argument("--verbose", help="Enable verbose output")
parser.add_argument("command", help="Command to run")
parser.parse_args()
```

When the user runs `myapp --help`, the output is rendered through the `help.txt` Kida template instead of argparse's default plain-text formatter.

## Customization

Override the built-in `help.txt` template by placing your own in your template directory. The template receives the full argparse structure as context.

:::{dropdown} Template context variables
:icon: code

The `help.txt` template receives:

| Variable | Type | Description |
|----------|------|-------------|
| `prog` | `str` | Program name |
| `description` | `str` | Parser description |
| `usage` | `str` | Usage string |
| `positionals` | `list` | Positional argument specs |
| `optionals` | `list` | Optional argument specs |
| `subcommands` | `list` | Subparser commands |

:::

## Fallback

:::{note}
If template rendering fails for any reason, `HelpRenderer` falls back to the default argparse formatting silently. Your CLI will always show help — it just won't be styled.
:::
