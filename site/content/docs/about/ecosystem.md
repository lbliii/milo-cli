---
title: Ecosystem
description: How Milo fits with Kida templates, Bengal docs, and agent-facing CLIs.
weight: 20
draft: false
lang: en
tags: [about, ecosystem]
keywords: [ecosystem, kida, bengal, mcp]
category: about
icon: network
---

Milo sits in a small Python tooling ecosystem:

- [[ext:kida:|Kida]] renders terminal templates.
- Bengal builds this documentation site.
- MCP hosts call Milo commands through stdin/stdout JSON-RPC.
- llms.txt gives agents a readable command catalog.

The runtime dependency remains `kida-templates`; documentation and site tooling
stay outside the runtime install.
