---
title: Adopt Milo in a Mature CLI
description: Migrate an established framework CLI without losing argv, output, exit, startup, or agent contracts.
weight: 5
draft: false
lang: en
tags: [migration, cli, framework, compatibility, mcp]
keywords: [framework adoption, argparse migration, compatibility, parity, downstream canary]
category: onboarding
icon: workflow
---

A mature CLI migration is a compatibility project, not a decorator rewrite.
Users and automation already depend on argv spellings, help meaning, output
channels, exit codes, import cost, and failure behavior. Milo adds programmatic,
MCP, and llms.txt surfaces, so the migration must prove those new surfaces
without silently changing the old one.

Use this workflow for framework CLIs, developer tools, and other command trees
where a clean-slate recipe is not enough. For a single small parser, start with
[[docs/get-started/migrate-existing-cli/from-argparse|From argparse]].

## 1. Freeze the compatibility inventory

Record behavior from the released CLI before changing registration. Pin the
source tag or commit used for the inventory.

| Surface | What to record | Minimum proof |
| --- | --- | --- |
| Command tree | Names, groups, aliases, ordering | Root and subcommand help |
| Parameters | Positional/option shape, defaults, choices | Valid and invalid argv |
| Process contract | stdout, stderr, exit `0`/`1`/`2` | Black-box subprocess tests |
| Structured output | JSON keys and version | Parse and exact-key assertions |
| Startup | Modules imported by help/version | Fresh-process import receipt |
| Side effects | Filesystem, network, database, server lifecycle | Explicit command classification |
| Agent surface | Commands safe for discovery and invocation | MCP and llms.txt allowlist |

Do not update a golden output merely because the new parser differs. Classify
each difference as preserved, intentionally migrated with release notes, or a
bug in one implementation.

## 2. Build typed adapters before switching entry points

Keep domain behavior in the downstream project. Add thin typed functions that
accept ordinary Python values, call that behavior, and return structured
values. Do not pass an `argparse.Namespace`, parser object, or captured terminal
text into Milo.

This representative adapter preserves positionals, a legacy option spelling,
custom version flags, terminal presentation, grouping, and command visibility:

```python milo-docs:compile
from typing import Annotated

from milo import CLI, Context, Option, Positional


def version_report() -> str:
    return "framework 4.2.0\nPython 3.14"


def render_check(result: dict[str, object], _ctx: Context) -> str:
    return f"Checked {result['app']}: {result['issues']} issue(s)"


cli = CLI(
    name="framework",
    description="Framework developer commands",
    version="4.2.0",
    version_flags=("-V", "--version"),
    version_report=version_report,
)


@cli.command(
    "check",
    description="Validate an application",
    annotations={"readOnlyHint": True},
    terminal_renderer=render_check,
)
def check(
    app: Annotated[str, Positional("APP")],
    warnings_as_errors: bool = False,
    baseline: Annotated[
        str | None,
        Option(aliases=("-b",), metavar="PATH"),
    ] = None,
    ctx: Context = None,
) -> dict[str, object]:
    """Validate one application.

    Args:
        app: Import path of the application.
        warnings_as_errors: Treat warnings as failures.
        baseline: Optional compatibility baseline.
        ctx: Milo's injected host context.
    """
    return {
        "app": app,
        "issues": 0,
        "warnings_as_errors": warnings_as_errors,
        "baseline": baseline,
    }


@cli.command("serve", description="Run the server", surfaces=("cli",))
def serve(app: Annotated[str, Positional("APP")]) -> dict[str, str]:
    """Run the downstream-owned server lifecycle.

    Args:
        app: Import path of the application.
    """
    return {"app": app, "status": "starting"}


database = cli.group("database", description="Database operations")


@database.command(
    "migrate",
    description="Apply database migrations",
    surfaces=("cli",),
    annotations={"destructiveHint": True, "idempotentHint": True},
)
def migrate(database_url: Annotated[str, Positional("DATABASE_URL")]) -> dict[str, str]:
    """Apply pending migrations.

    Args:
        database_url: Database connection URL.
    """
    # Call the downstream-owned migration service here. Do not return the URL.
    return {"status": "migrated"}
```

`Context` is injected by dispatch and omitted from JSON Schema. Keep host-owned
diagnostics, progress, and confirmation on `Context`; keep reusable command
results in return values. A `terminal_renderer` formats only plain human output,
while `call()`, `call_raw()`, JSON output, and MCP retain the structured value.

## 3. Preserve lazy startup deliberately

For large command trees, use public `CLI.lazy_command()` to register a deferred
import with a precomputed schema.
Help, MCP discovery, and llms.txt can then inspect the contract without loading
the handler module:

```python milo-docs:compile
cli.lazy_command(
    "inspect",
    "framework_cli.inspect:inspect_app",
    description="Inspect an application",
    schema={
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": "Application import path.",
                "x-milo-cli": {"kind": "positional", "metavar": "APP"},
            }
        },
        "required": ["app"],
    },
    annotations={"readOnlyHint": True},
)
```

Treat the precomputed schema as a generated or reviewed contract artifact. Test
it against the handler signature so it cannot become a second, drifting schema
source. Lazy import failures exit nonzero and retain structured repair data;
do not replace them with a silent fallback.

## 4. Classify commands before agent exposure

CLI availability does not imply that a command is safe for agents.

- Expose finite inspection commands through `("cli", "mcp", "llms")` and
  declare `readOnlyHint` when truthful.
- Keep servers, watchers, interactive shells, and unreviewed mutations on
  `surfaces=("cli",)`.
- Add `destructiveHint` and human/host confirmation policy before exposing a
  mutation through MCP.
- Never put credentials, private paths, or raw database URLs in schemas,
  snapshots, logs, or structured errors.

Milo enforces the allowlist consistently: a CLI-only command is absent from
`tools/list` and llms.txt and cannot be reached through `tools/call`.

## 5. Prove every dispatch surface

Use public test helpers and assert values rather than scraping human output:

```python milo-docs:compile
import json

from app import cli
from milo import generate_llms_txt
from milo.testing import MCPClient


def test_framework_command_parity() -> None:
    terminal = cli.invoke(["check", "project:app", "--format", "json"])
    assert terminal.exit_code == 0
    assert json.loads(terminal.output)["app"] == "project:app"

    called = cli.call_raw("check", app="project:app", warnings_as_errors=True)
    assert called["warnings_as_errors"] is True

    mcp = MCPClient(cli)
    assert [tool.name for tool in mcp.list_tools()] == ["check"]
    result = mcp.call("check", app="project:app")
    assert result.is_error is False
    assert result.structured["issues"] == 0

    llms = generate_llms_txt(cli)
    assert "**check**" in llms
    assert "**serve**" not in llms


def test_usage_errors_remain_process_errors() -> None:
    result = cli.invoke(["check", "--unknown-option"])
    assert result.exit_code == 2
    assert result.output == ""
    assert "error:" in result.stderr
```

The release gate should cover this parity matrix:

| Surface | Required assertion |
| --- | --- |
| Legacy subprocess | Golden help, channels, and exit codes |
| `CLI.invoke` | Equivalent parsing, result, output, stderr, and exit |
| `CLI.call` / `call_raw` | Structured values without terminal prints |
| Schema | Requiredness, defaults, aliases, constraints, descriptions |
| MCP `tools/list` | Only reviewed tools with truthful schemas/annotations |
| MCP `tools/call` | Same defaults, validation, results, and structured errors |
| llms.txt | Same finite discovery set and parameter descriptions |
| Lazy startup | Help/version/discovery do not import handler modules |
| Free-threading | Registration, discovery, and calls pass with `PYTHON_GIL=0` |

Run `milo verify` against the assembled application before switching the
packaged entry point. The verifier complements downstream golden tests; it does
not replace them.

## 6. Cut over in reversible phases

1. Land the black-box inventory while the old parser still owns the entry
   point.
2. Add typed adapters and programmatic tests without changing user-visible
   dispatch.
3. Migrate finite read-only commands first.
4. Migrate filesystem/database commands after annotations and confirmation
   policy are reviewed.
5. Migrate long-running commands last and keep them CLI-only.
6. Switch the packaged entry point only when both implementations pass the
   same golden suite.
7. Keep a short rollback window; remove the old parser after a released canary
   proves the new path.

If an old option spelling must remain, preserve it with `Option(aliases=...)`.
Milo normalizes aliases before the handler runs, so a spelling-specific
deprecation warning belongs in a temporary argv compatibility shim, not in the
domain function. Publish the removal release before deleting that shim.

## 7. Version the downstream proof

A canary must identify what it tested. Pin exact released versions and an
immutable downstream source identity; do not follow either default branch.
Advance a compatible dependency range only after more than one exact pair has
passed and release notes explain downstream-visible changes.

Milo's first mature-framework receipt is
[the Chirp downstream canary](https://github.com/lbliii/milo-cli/blob/main/docs/chirp-downstream-canary.md).
It pins `milo-cli==0.4.1`, `bengal-chirp==0.9.0`, and Chirp commit
`9ada3ba4b26ed37fbfde0ef69b60c3897830d3d3`. The deeper
[compatibility inventory](https://github.com/lbliii/milo-cli/blob/main/docs/chirp-adoption-contract.md)
maps all eleven commands and ownership boundaries. Chirp's actual packaged
entry-point migration remains tracked in
[Chirp issue #572](https://github.com/lbliii/chirp/issues/572); the canary is
evidence that released Milo supports the contract, not a claim that Chirp has
already switched.

## Next references

- [[docs/build-clis/commands|Commands]] — groups, positionals, aliases, version reports, and visibility
- [[docs/build-clis/lazy|Lazy Commands]] — deferred imports and structured failures
- [[docs/build-clis/output|Output]] — terminal renderers and structured values
- [[docs/build-clis/context|Context]] — host-owned I/O and interaction policy
- [[docs/build-clis/mcp|MCP]] — annotations, resources, and protocol behavior
- [[docs/reference/dispatch|Dispatch Reference]] — `invoke`, `call`, `call_raw`, and MCP parity
- [[docs/quality/testing|Testing]] — free-threaded and cross-surface proof
