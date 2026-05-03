---
title: Return Values
description: How command return values become CLI output and MCP content.
weight: 10
draft: false
lang: en
tags: [about, output, mcp]
keywords: [return values, structured content, output, json]
category: about
icon: reply
---

Prefer returning structured values from command handlers. Milo can format those
values for humans, serialize them for `--format json`, and expose them as MCP
`structuredContent`.

| Return value | Use it for |
|---|---|
| `str` | Short human-readable text |
| `dict` | Named structured result |
| `list` | Collections and tables |
| `int` / `float` / `bool` | Counters, measurements, and flags |
| `None` | Commands whose useful result is an explicit side effect |

For agent-facing commands, avoid requiring clients to scrape terminal prose.
Return data and use `Context` helpers for optional human-facing logs.
