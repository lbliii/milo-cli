---
title: Core Concepts
description: The main ideas shared by Milo CLIs and interactive apps.
weight: 30
draft: false
lang: en
tags: [about, concepts]
keywords: [core concepts, cli, app, reducer, schema, mcp]
category: about
icon: layers
---

Milo has two related building blocks:

- `CLI` turns typed functions into commands, schemas, MCP tools, and llms.txt.
- `App` runs a reducer-driven terminal interface with templates and input.

The shared concepts are:

| Concept | Role |
|---|---|
| Command handler | Typed Python function exposed to humans and agents |
| Schema | JSON Schema derived from annotations and docstrings |
| Context | Injected runtime object for output, global options, and app bridges |
| State | Serializable model for interactive apps |
| Reducer | Pure function that turns actions into new state |
| Saga / Cmd | Explicit side-effect boundary |
| Template | Kida view rendered from state |

:::{child-cards}
:include: pages
:fields: title, description, icon
:::
