---
title: Choosing Milo
description: Compare Milo's documentation and contracts with argparse, Click, Typer, Fire, and Cobra.
weight: 5
draft: false
lang: en
tags: [comparison, migration, cli, docs]
keywords: [cli comparison, argparse, click, typer, fire, cobra, mcp]
category: migration
icon: scale
---

This comparison is about documentation posture and command contracts, not a
claim that one library is universally better. Pick Milo when the same Python
function must serve humans, tests, programmatic callers, MCP agents, and
llms.txt discovery.

## What Each Library Teaches First

| Library | First lesson in its docs | What that optimizes for |
|---|---|---|
| `argparse` | Build an `ArgumentParser`, add arguments, parse argv | Standard-library explicit parsing |
| Click | Compose commands, groups, context, options, and arguments | Mature human CLI ergonomics |
| Typer | Use Python type hints to define arguments and options | Fast Python CLI authoring with annotations |
| Python Fire | Turn a Python object into a CLI with `Fire(...)` | Exploration and very low ceremony |
| Cobra | Generate a Go CLI project and add command files | Large compiled Go command trees |
| Milo | Write one typed function and verify CLI, schema, MCP, and llms.txt | Shared human/agent command contracts |

Official sources checked: [argparse](https://docs.python.org/3/library/argparse.html), [Click](https://click.palletsprojects.com/en/stable/commands-and-groups/), [Typer](https://typer.tiangolo.com/tutorial/first-steps/), [Python Fire](https://google.github.io/python-fire/guide/), and [Cobra](https://cobra.dev/docs/tutorials/getting-started/).

## Where Milo Should Feel Stronger

Milo docs should be stronger when the reader asks:

- "What schema will an agent see?"
- "Does CLI dispatch match MCP dispatch?"
- "Can I verify this app before registering it with an MCP host?"
- "What error data can an agent use to repair a bad call?"
- "Can I return structured values instead of scraping terminal text?"

Those are first-class docs in Milo:

- [[docs/reference/schema|Schema Contract]]
- [[docs/reference/dispatch|Dispatch Contract]]
- [[docs/reference/errors|Errors]]
- [[docs/usage/testing|Testing]]
- [[docs/usage/mcp|MCP]]

## Where Other Docs Are Still Better

| Area | Stronger external model | Milo follow-up |
|---|---|---|
| Decades of parser edge cases | `argparse` | Expand argv compatibility notes and parser edge-case examples |
| Mature human CLI cookbook | Click | Add more real-world recipes for env vars, aliases, deprecation, prompts, and shell behavior |
| Beginner-friendly Python walkthroughs | Typer | Keep quickstarts command-first and add more small tutorial branches |
| REPL/exploration workflows | Python Fire | Document when Milo is intentionally more explicit than exploratory |
| Enterprise-scale command trees | Cobra | Add a larger multi-module CLI example with groups, config, and gateway registration |

The migration pages exist to close that gap without copying another framework's
mental model into Milo.

## Choose Milo When

- Your CLI is also an MCP server.
- The JSON Schema has to be truthful and testable.
- You want `--llms-txt` and `tools/list` generated from the same function.
- You need structured returns for agents, CI, or dashboards.
- You want `milo verify` to catch import, schema, and transport problems before
  users register the tool.

## Keep Another Library When

- You only need a local human CLI and already have a stable Click or argparse
  surface.
- You depend on a library-specific plugin ecosystem or exact argv behavior.
- You are building a Go binary and Cobra's generated command structure is the
  right fit.
- You are exploring arbitrary Python objects and explicit public contracts would
  slow you down.

## Migration Path

Start with the smallest command that agents should call:

1. Port the handler to a typed Milo function.
2. Return a JSON-serializable value.
3. Add parameter descriptions.
4. Run `uv run milo verify app.py`.
5. Add schema, `cli.invoke`, MCP, and verify tests.

Then migrate adjacent commands only after the first command's contract is stable.
