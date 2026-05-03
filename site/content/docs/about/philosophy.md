---
title: Philosophy
description: The design constraints behind Milo's command and app model.
weight: 5
draft: false
lang: en
tags: [about, philosophy]
keywords: [philosophy, design, cli, mcp]
category: about
icon: compass
---

Milo starts from one constraint: a typed Python function should safely become a
human CLI command, an MCP tool with a truthful JSON Schema, and an llms.txt
entry.

That leads to a few practical choices:

- The function signature is the contract.
- Schema generation has one source of truth.
- Reducers stay pure and deterministic.
- Protocol code stays sans-I/O until the transport boundary.
- Runtime state is explicit enough to test, replay, and debug.

Milo keeps the default install small: pure Python plus `kida-templates`.
