---
title: Milo, FastMCP, and Typer
description: Choose the smallest framework whose primary surface matches the product you are building.
weight: 20
draft: false
lang: en
tags: [about, decision, comparison, cli, mcp]
keywords: [Milo, FastMCP, Typer, comparison, CLI, MCP]
category: about
icon: scale
---

Milo, FastMCP, and Typer all use typed Python functions, but they optimize for
different products. Choose based on the surface that must remain authoritative.

| If your product is primarily... | Start with |
|---|---|
| An MCP server, client, or conversational app | **FastMCP** |
| A polished human CLI | **Typer** |
| One capability that must stay aligned across CLI, Python, MCP, and llms.txt | **Milo** |

This is not a feature-count contest. FastMCP and Typer are mature choices in
their domains. Milo is intentionally narrower: it owns the seam between a human
command and an agent tool.

## Compared at the Contract Boundary

| Concern | Milo | FastMCP | Typer |
|---|---|---|---|
| Primary surface | Human CLI and MCP tool from one command | MCP servers, clients, and apps | Human CLI |
| Typed function projection | argparse command, programmatic call, MCP schema/call, llms.txt | MCP tool schema/call | Click command and help |
| Runtime input validation | Milo's generated schema, shared by dispatch paths | Flexible or strict validation, including Pydantic types | CLI parsing and Click/Typer validation |
| Human terminal UX | Commands, prompts, forms, reducer-driven apps | Not its primary job | Rich CLI help, prompts, completion, command trees |
| MCP breadth | Local stdio server, resources, progress, gateway | Broad server/client/app, auth, transport, and deployment surface | Requires an MCP adapter |
| Runtime dependencies | `kida-templates` | A larger MCP and validation stack | Click and its presentation stack |

## Choose FastMCP When MCP Is the Product

FastMCP is designed for MCP servers, clients, and applications. Its current
documentation covers remote transports, authentication, deployment, MCP Apps,
clients, timeouts, and broad Pydantic-backed types. Choose it when those MCP
capabilities matter more than exposing the same operation as a first-class
human CLI.

FastMCP also generates schemas and validates tool arguments. Milo's distinction
is not “typed tools versus untyped tools”; it is that the same registered
definition also owns argparse behavior, programmatic dispatch, and llms.txt.

Official reference: [FastMCP overview](https://gofastmcp.com/getting-started/welcome)
and [FastMCP tools](https://gofastmcp.com/servers/tools).

## Choose Typer When the CLI Is the Product

Typer is built for human-facing command-line applications. It offers automatic
help, subcommands, shell completion, prompts, progress bars, and the wider Click
ecosystem. Choose it when MCP is not a requirement or when a separately owned
MCP layer is acceptable.

You can place an MCP adapter beside a Typer app. The cost is governance: command
defaults, schemas, errors, hidden commands, and documentation now have two
registration paths unless your adapter deliberately centralizes them. Milo
exists for teams that want that parity to be the framework's default contract.

Official reference: [Typer](https://typer.tiangolo.com/) and
[Typer features](https://typer.tiangolo.com/features/).

## Choose Milo When One Definition Must Serve Both

Choose Milo when all of these are requirements:

- A command must be pleasant for a person to run from a terminal.
- An agent must discover and call it over MCP without a second schema.
- Python callers need the same defaults, coercion, constraints, and structured
  failures.
- Startup, free-threading, and a small pure-Python runtime are product concerns.
- `milo verify` should catch schema or transport drift before registration.

Milo is not currently the broadest remote MCP platform or the largest CLI
ecosystem. If only one surface matters, use the framework specialized for that
surface. If drift between the two surfaces is the problem, that is Milo's job.

## Migration Is Incremental

An existing Typer or argparse application does not need a flag-day rewrite.
Start with one command whose agent and human contracts must agree, prove it with
schema/direct/MCP tests and `milo verify`, then move the next command. See the
[[docs/get-started/migrate-existing-cli/|migration guides]] for concrete
patterns.

_Comparison checked against the linked official documentation on July 7, 2026._
