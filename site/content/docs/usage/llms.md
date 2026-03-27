---
title: llms.txt Generation
nav_title: llms.txt
description: Generate AI discovery documents from CLI command definitions.
weight: 76
draft: false
lang: en
tags: [llms, ai, discovery]
keywords: [llms, llms-txt, ai, discovery, agent, documentation]
category: usage
icon: file-text
---

Milo can generate an [llms.txt](https://llmstxt.org/) document from your CLI's registered commands. This gives AI agents a curated Markdown overview of what your tool can do.

## Generating llms.txt

```
myapp --llms-txt
```

Output:

```markdown
# myapp

> My tool

Version: 1.0.0

## Commands

- **greet**: Say hello
  Parameters: `--name` (string, required), `--loud` (boolean)

## Site Operations

- **build**: Build the site
  Parameters: `--output` (string)
- **serve**: Start dev server
  Parameters: `--port` (integer)
```

## Structure

The output follows the llms.txt specification:

1. **Title** — CLI name as `# heading`
2. **Description** — CLI description as a blockquote
3. **Version** — if set
4. **Commands** — grouped by tag, then by command group
5. **Parameters** — with types and required markers

## Tags

Commands with tags are grouped under tag-derived headings:

```python
@cli.command("deploy", description="Deploy the app", tags=("ops",))
def deploy(target: str) -> str: ...

@cli.command("rollback", description="Rollback", tags=("ops",))
def rollback(steps: int = 1) -> str: ...
```

Produces:

```markdown
## Ops

- **deploy**: Deploy the app
  Parameters: `--target` (string, required)
- **rollback**: Rollback
  Parameters: `--steps` (integer)
```

## Groups

Command groups produce nested headings:

```markdown
## Site Operations

- **build**: Build the site

### Config Management

- **show**: Show merged config
- **set**: Update a config value
```

## Programmatic generation

```python
from milo import generate_llms_txt

text = generate_llms_txt(cli)
```

## Hidden commands

Commands with `hidden=True` are excluded from the output.

## Aliases

Command aliases appear in parentheses:

```markdown
- **list** (ls): List all items
```

:::{tip}
Pair `--llms-txt` with `--mcp` to give AI agents both a discovery document and a tool invocation interface. See [[docs/usage/mcp|MCP Server]] for the full MCP setup, including the gateway for multi-CLI projects.
:::
