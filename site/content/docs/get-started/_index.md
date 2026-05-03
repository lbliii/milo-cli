---
title: Get Started
draft: false
weight: 10
lang: en
type: doc
description: Install Milo and build your first typed CLI command.
keywords: [get started, installation, quickstart]
tags: [onboarding]
icon: rocket
---

Install Milo with `pip install milo-cli` (requires Python 3.14+), then scaffold
a typed command that works as a human CLI, MCP tool, and llms.txt entry.

:::{cards}
:columns: 1-2
:gap: medium

:::{card} Installation
:icon: download
:link: ./installation
:description: Install with uv, pip, or from source
:badge: Step 1
Set up Milo and verify your Python 3.14t environment.
:::{/card}

:::{card} Quickstart
:icon: play
:link: ./quickstart
:description: Build a typed CLI/MCP command in 5 minutes
:badge: Step 2
Scaffold a command, run it, inspect schemas, test it, and verify MCP transport.
:::{/card}

:::{/cards}

## Next steps

- [[docs/usage/cli|CLI and commands]] — Typed command definitions and dispatch
- [[docs/usage/mcp|MCP server]] — Expose commands as tools
- [[docs/usage/testing|Testing]] — Schema, CLI, MCP, and verify layers
- [[docs/tutorials/build-a-counter|Interactive apps]] — Build a reducer-driven terminal app
