---
title: Migrate Existing CLIs
nav_title: Migrate
description: Translate existing CLI patterns from argparse, Click, Typer, Fire, and Cobra into Milo.
weight: 25
draft: false
lang: en
type: doc
tags: [migration, cli]
keywords: [migration, argparse, click, typer, fire, cobra]
category: onboarding
icon: arrows-right-left
---

Use these recipes when you already have a CLI command and want to move it to
Milo's typed function contract. Each page shows a small before/after and the
specific concepts to translate.

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

## Recipes

- [[docs/get-started/migrate-existing-cli/from-argparse|From argparse]]
- [[docs/get-started/migrate-existing-cli/from-click|From Click]]
- [[docs/get-started/migrate-existing-cli/from-typer|From Typer]]
- [[docs/get-started/migrate-existing-cli/from-fire|From Python Fire]]
- [[docs/get-started/migrate-existing-cli/from-cobra|From Cobra]]

## Official References Checked

- [argparse documentation](https://docs.python.org/3/library/argparse.html)
- [Click commands and groups](https://click.palletsprojects.com/en/stable/commands-and-groups/)
- [Typer first steps](https://typer.tiangolo.com/tutorial/first-steps/)
- [Python Fire guide](https://google.github.io/python-fire/guide/)
- [Cobra getting started](https://cobra.dev/docs/tutorials/getting-started/)
