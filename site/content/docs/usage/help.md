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

When the user runs `myapp --help`, the output is rendered through the `help.kida` Kida template instead of argparse's default plain-text formatter.

## Customization

Override the built-in `help.kida` template by placing your own in your template directory. The template receives the full argparse structure as context.

:::{dropdown} Template context variables
:icon: code

The `help.kida` template receives:

| Variable | Type | Description |
|----------|------|-------------|
| `state.prog` | `str` | Program name |
| `state.description` | `str` | Parser description captured from argparse |
| `state.epilog` | `str` | Parser epilog, when populated |
| `state.usage` | `str` | Usage string, when populated |
| `state.groups` | `tuple[dict]` | Captured argparse action groups |
| `state.examples` | `tuple[dict]` | Optional examples supplied by `help_formatter_with_examples()` |
| `state.commands` | `tuple[dict]` | Reserved for command summaries |
| `state.options` | `tuple[dict]` | Reserved for option summaries |

:::

## Fallback

:::{note}
If template rendering fails, `HelpRenderer` emits a `UserWarning` and falls
back to argparse's default formatter. Your CLI will still show help, but it will
not use the styled Kida template.
:::
