---
title: Build CLIs
draft: false
weight: 30
lang: en
type: doc
description: Build typed command-line tools that also expose MCP tools and llms.txt discovery.
keywords: [cli, commands, mcp, llms, schema]
tags: [cli, commands]
icon: terminal
---

Build human-facing commands and agent-facing tools from the same typed Python
functions. Start with commands and groups, then add schemas, context, output
formatting, llms.txt, and MCP.

:::{cards}
:columns: 2
:gap: medium

:::{card} Commands
:icon: terminal
:link: ./commands/
:description: Register typed command handlers and run them from argv
:::{/card}

:::{card} Groups
:icon: tree-structure
:link: ./groups/
:description: Organize commands into nested namespaces
:::{/card}

:::{card} Context and Output
:icon: list
:link: ./context/
:description: Use injected context, global options, and structured returns
:::{/card}

:::{card} MCP Server
:icon: cpu
:link: ./mcp/
:description: Expose commands as MCP tools and run the gateway
:::{/card}

:::{/cards}

:::{child-cards}
:include: pages
:fields: title, description, icon
:::
