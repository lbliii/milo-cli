# Draft: Every CLI Should Be an MCP Server

The command line already contains thousands of useful capabilities. They know
how to deploy services, inspect systems, transform data, and repair projects.
Humans can compose them because they have names, arguments, help, exit codes,
and predictable output. Agents need the same things, expressed as a protocol.

The usual answer is to build an MCP server beside the CLI. That works, but it
creates two contracts:

- The CLI parser owns flags, defaults, and human help.
- The MCP server owns JSON Schema, tool metadata, and protocol errors.

The first version looks identical. Then one side adds a default, hides a
dangerous command, renames an option, or tightens a constraint. The adapter
still runs, but it is no longer true.

Milo starts from a different premise: a command and a tool are two projections
of one typed Python function.

```python milo-docs:compile
from typing import Annotated

from milo import CLI, Context, MinLen

cli = CLI(name="deployer", description="Deploy services")


@cli.command(
    "deploy",
    description="Deploy a service",
    annotations={"destructiveHint": True},
)
def deploy(
    environment: Annotated[str, MinLen(1)],
    service: Annotated[str, MinLen(1)],
    ctx: Context = None,
) -> dict[str, str]:
    """Deploy a service to an environment.

    Args:
        environment: Target environment.
        service: Service to deploy.
        ctx: Milo's injected execution context.
    """
    if ctx and ctx.is_interactive and not ctx.confirm(
        f"Deploy {service} to {environment}?"
    ):
        return {"status": "cancelled"}
    return {"status": "deployed", "service": service, "environment": environment}
```

That one definition supplies:

- An argparse command for a person at a terminal.
- A direct Python call for tests and composition.
- An MCP tool with generated and enforced JSON Schema.
- An llms.txt entry for inexpensive discovery.
- Behavioral hints such as `destructiveHint`.

The dual-mode detail matters. A person can receive a confirmation prompt. An
agent gets structured input, a non-interactive execution path, and a structured
result. The business operation is shared; the presentation boundary is not.

## Trust Is the Feature

Generating a schema is easy. Keeping it honest is the work.

Milo validates the generated contract before every handler call, rejects
unknown arguments instead of silently dropping them, keeps injected `Context`
out of agent-visible schemas, and makes hidden tools uncallable over MCP.
Failures carry stable error codes, the failing argument, the violated
constraint, and a repair suggestion.

`milo verify app.py` then tests the assembled application: import, command
registration, schema generation, tools/list, protocol discovery, and a real
subprocess JSON-RPC handshake. If verification fails, the tool should not be
registered with an agent.

## This Is Not “MCP Replaces CLIs”

CLIs remain a superb interface for humans, scripts, CI, and incident response.
MCP adds a typed discovery and invocation surface for agents. The useful move is
not replacing one with the other; it is refusing to maintain the same
capability twice.

FastMCP is a stronger fit when the product is a broad MCP server, client, or
application platform. Typer is a stronger fit when the product is solely a
polished CLI and MCP is not part of its contract. Milo is for the seam: one
operation, two audiences, one source of truth.

The public
[Typer + FastMCP comparison](https://lbliii.github.io/milo-cli/docs/about/comparisons/)
shows the complete same-app source, line-count method, verification boundary,
and scoped Milo benchmark receipts. The repository's
[claims ledger](../public-claims.json) records which launch claims are proven,
scoped snapshots, or still pending.

## The Small Bet

Take one internal CLI command that an agent should be able to use. Give its
parameters types and descriptions. Run it by hand. Run `milo verify`. Register
the same file as a local MCP server. Ask the agent to call it.

If the command stays useful to both audiences without an adapter schema, the
idea has earned the next command.

That is the position: every durable CLI capability should be ready to become an
MCP tool, and doing so should not require a second implementation.

## Publication Checklist

- Replace “Draft” after the release containing #85 and #86 is published.
- Link the final 60–90 second demo at the top.
- Add the release version and launch date.
- Run every command from [the recording script](./launch-demo-script.md) on a
  clean machine immediately before publication.
- Link the public comparison page and the final Show HN repository URL.
