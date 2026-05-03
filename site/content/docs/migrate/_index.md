---
title: Migrate
nav_title: Migrate
description: Translate existing CLI patterns from argparse, Click, Typer, Fire, and Cobra into Milo.
weight: 25
draft: false
lang: en
type: doc
tags: [migration, comparison, cli]
keywords: [migration, argparse, click, typer, fire, cobra, comparison]
category: migration
icon: arrows-right-left
---

Milo is not a drop-in replacement for every CLI framework. It is a good fit when
the command contract must be shared by humans, programmatic callers, MCP agents,
and llms.txt discovery.

:::{child-cards}
:include: pages
:fields: title, description, icon
:::

## Migration Rule

Move behavior first, then output polish:

1. Convert one command handler into a typed Python function.
2. Register it with `@cli.command`.
3. Add docstring `Args:` entries or `Annotated[..., Description(...)]`.
4. Run `uv run milo verify app.py`.
5. Add the four command contract tests before migrating the next command.

Keep old CLI compatibility wrappers only where users depend on exact argv
shape. Milo's main contract is the function signature; schema, MCP, and llms.txt
are derived from that signature.

## Start With Comparison

Read [[docs/migrate/comparison|Choosing Milo]] first if you are deciding
whether Milo is the right fit. Use the framework-specific pages when you already
know what you are porting.

Recipe pages:

- [[docs/migrate/from-argparse|From argparse]]
- [[docs/migrate/from-click|From Click]]
- [[docs/migrate/from-typer|From Typer]]
- [[docs/migrate/from-fire|From Python Fire]]
- [[docs/migrate/from-cobra|From Cobra]]

## Comparison At A Glance

| Library | Native strength | Milo migration focus |
|---|---|---|
| `argparse` | Standard-library parser with explicit argument definitions | Replace parser construction with typed handler signatures |
| Click | Mature command/group model with decorators and context | Move option metadata into annotations, defaults, and docstrings |
| Typer | Python type-hint driven CLI ergonomics | Add MCP, llms.txt, `milo verify`, and structured error tests |
| Python Fire | Very fast exposure of Python objects as CLIs | Narrow the public surface and make schemas explicit through types |
| Cobra | Large Go CLI applications with generated command files and flags | Map command trees and persistent behavior into Milo groups and context |

## Official References Checked

- [argparse documentation](https://docs.python.org/3/library/argparse.html)
- [Click commands and groups](https://click.palletsprojects.com/en/stable/commands-and-groups/)
- [Typer first steps](https://typer.tiangolo.com/tutorial/first-steps/)
- [Python Fire guide](https://google.github.io/python-fire/guide/)
- [Cobra getting started](https://cobra.dev/docs/tutorials/getting-started/)
