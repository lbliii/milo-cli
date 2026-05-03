---
title: When to Use Milo
description: Choose Milo for typed CLIs, MCP tools, and reducer-driven terminal apps.
weight: 15
draft: false
lang: en
tags: [about, decision]
keywords: [when to use, cli, mcp, terminal apps]
category: about
icon: compass
---

Use Milo when the same code must serve more than one surface:

- A human command-line interface.
- A programmatic Python call.
- An MCP tool call from an agent.
- A discoverable llms.txt entry.
- A reducer-driven terminal app.

Milo is especially useful when schemas, structured returns, and repairable
errors matter. For a one-off local script that only parses argv and prints text,
the standard library may be enough.
