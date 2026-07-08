---
title: Milo vs Typer + FastMCP
description: Compare one cross-surface Milo command with a real Typer and FastMCP composition.
weight: 20
draft: false
lang: en
tags: [about, decision, comparison, cli, mcp]
keywords: [Milo, FastMCP, Typer, comparison, CLI, MCP]
category: about
icon: scale
---

Typer and FastMCP are strong, mature choices for their primary surfaces. The
real alternative to Milo is often not either project alone; it is a Typer CLI
and a FastMCP server composed around the same operation. This page compares
that composition at the contract boundary.

| If your product is primarily... | Start with |
|---|---|
| An MCP server, client, remote service, or conversational app | **FastMCP** |
| A polished human CLI | **Typer** |
| One capability that must stay aligned across CLI, Python, MCP, and llms.txt | **Milo** |

This is not a claim that Milo replaces either framework. It is an accounting
of the glue a team owns when both surfaces must describe the same capability.

## Same Deploy App, Complete Entrypoints

The repository contains two runnable fixtures for a `deploy` operation:

- [`milo_app.py`](https://github.com/lbliii/milo-cli/blob/main/benchmarks/comparison/milo_app.py)
  registers one typed function. Milo projects it to the CLI, local stdio MCP,
  direct Python dispatch, and llms.txt.
- [`typer_fastmcp_app.py`](https://github.com/lbliii/milo-cli/blob/main/benchmarks/comparison/typer_fastmcp_app.py)
  uses FastMCP for the tool and a Typer wrapper for human output, then owns the
  `--mcp`/CLI process switch.

The composed fixture was executed and inspected with Typer 0.26.8 and FastMCP
3.4.3. Reproduction commands pin those versions so a future framework change
cannot silently rewrite this evidence.

The metric counts every nonblank, non-comment physical source line in the
complete entrypoint. Imports, docstrings, registration, human presentation,
and process dispatch count. Tests recalculate these totals so the page cannot
drift from the fixtures.

| Complete same-app entrypoint | Source lines |
|---|---:|
| Milo | `24` |
| Typer + FastMCP | `44` |

The 20-line difference is a small composition-cost illustration, not a general
productivity or performance benchmark. A real project may factor wrappers into
shared modules, add richer Typer presentation, or use FastMCP's broader server
features. The fixture deliberately keeps the business operation identical and
counts the plumbing needed for both runnable entrypoints.

Reproduction commands and the counting rule live beside the
[`comparison fixtures`](https://github.com/lbliii/milo-cli/tree/main/benchmarks/comparison).

## Compared at the Contract Boundary

| Concern | Milo | Typer + FastMCP |
|---|---|---|
| Primary ownership | One registered command owns CLI, direct call, MCP, and llms.txt | Typer owns the CLI; FastMCP owns MCP; the application owns their composition |
| Typed function projection | argparse command, programmatic call, MCP schema/call, llms.txt | Click command/help plus FastMCP tool schema/call |
| Human output | Built-in terminal renderer can present structured results | Typer wrapper prints or renders the domain result |
| Agent schema | `function_to_schema()` is shared by Milo's dispatch paths | FastMCP generates and validates the MCP tool schema |
| Verification | One ten-check run covers import, registration, schema, in-process MCP, discovery, MCP Apps, gateway projection, and subprocess transport | Typer documents `CliRunner`; FastMCP provides server inspection and MCP-format metadata; the application supplies cross-surface parity tests |
| Discovery | Built-in llms.txt and MCP `tools/list` | MCP discovery through FastMCP; any separate llms.txt artifact is application-owned |
| Remote MCP breadth | Local stdio today; streamable HTTP is tracked separately | Remote transports, auth, deployment, clients, apps, providers, and transforms |
| Runtime dependency posture | One runtime dependency, `kida-templates` | Typer/Click and FastMCP's MCP/validation stack |

## The Verification Difference

FastMCP's official [`fastmcp inspect`](https://gofastmcp.com/cli/inspecting)
command is useful: it loads a local server and emits either FastMCP metadata or
the MCP protocol view. Typer's official
[`CliRunner` testing guide](https://typer.tiangolo.com/tutorial/testing/)
shows how to invoke a CLI and assert its exit code and output. Those are real
verification tools, and a composed application should use them.

What the composition does not add by itself is one conformance command for the
relationship between those independently registered surfaces. The application
must decide how to prove that CLI defaults, tool schema, visibility, errors,
and results still agree.

`milo verify app.py` owns that relationship. Its ten checks cover:

1. target import;
2. CLI discovery;
3. command registration;
4. schema generation and documentation warnings;
5. in-process MCP tool listing;
6. protocol discovery;
7. in-process MCP Apps links and resources;
8. gateway MCP Apps projection;
9. subprocess JSON-RPC discovery, initialization, and tool listing; and
10. subprocess MCP Apps negotiation and resource reads.

The list is defined in
[`src/milo/verify.py`](https://github.com/lbliii/milo-cli/blob/main/src/milo/verify.py)
and exercised by
[`tests/test_verify.py`](https://github.com/lbliii/milo-cli/blob/main/tests/test_verify.py),
not maintained as a marketing-only checklist.

## What FastMCP and Typer Do Better

Choose FastMCP when MCP itself is the product. Its current official
documentation covers remote transports, authentication, deployment, clients,
interactive apps, providers, transforms, tool versioning, rich Pydantic-backed
types, and output schemas. FastMCP also runs synchronous tools in a thread pool
by default. See the [FastMCP overview](https://gofastmcp.com/getting-started/welcome)
and [tool documentation](https://gofastmcp.com/servers/tools).

Choose Typer when the human CLI is the product. It offers automatic help,
subcommands, shell completion, prompts, progress bars, and the wider Click
ecosystem. See [Typer](https://typer.tiangolo.com/) and its
[features](https://typer.tiangolo.com/features/).

Choose Milo when drift between the CLI and agent surface is the problem you
want the framework to own. Milo is not currently the broadest remote MCP
platform or the largest CLI ecosystem.

## Scoped Performance Receipts

Milo's [`BASELINE.md`](https://github.com/lbliii/milo-cli/blob/main/benchmarks/BASELINE.md)
records local, workload-specific medians rather than competitor speed claims.
Examples include a `233ns` MCP `initialize` router dispatch and a `125ns`
cached `get_env()` lookup on the stated Apple Silicon / CPython 3.14 baseline.
It also records a `13.1µs` full local MCP round trip and approximately
`15.8µs` per command for uncached tool-schema generation.

These numbers explain Milo's own hot paths. They do **not** compare Milo with
Typer or FastMCP, and environment changes require a new baseline before making
a speed claim. The machine-readable
[`public-claims.json`](https://github.com/lbliii/milo-cli/blob/main/public-claims.json)
keeps this evidence classified as a scoped snapshot.

## Parallel HTTP Proof Is Still Pending

Milo does not yet publish the planned free-threaded parallel HTTP tool-call
claim. That evidence depends on the streamable HTTP work tracked in
[#106](https://github.com/lbliii/milo-cli/issues/106) and the shared workload
from pounce
[#229](https://github.com/lbliii/pounce/issues/229). The claims ledger marks it
`pending`; this page will link the resulting artifact instead of restating an
unverified headline.

## Migration Is Incremental

An existing Typer or argparse application does not need a flag-day rewrite.
Start with one command whose agent and human contracts must agree, prove it with
schema/direct/MCP tests and `milo verify`, then move the next command. See the
[[docs/get-started/migrate-existing-cli/|migration guides]] for concrete
patterns.

_Comparison checked against the linked official documentation on July 8, 2026._
