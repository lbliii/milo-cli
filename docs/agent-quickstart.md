# Agent Quickstart

This doc gets a coding agent (Claude, DORI, Copilot, etc.) from zero to
"my CLI is an MCP tool that Claude is calling" in five minutes. It is written
for the agent: copy each block, run it, verify the output, move on.

If something in this doc no longer works, that's the bug — open an issue.

## Prerequisites

- Python 3.14+ (the project uses free-threading on 3.14t; 3.14 GIL builds also work).
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
- This repo cloned or `milo-cli` installed (`uv add milo-cli`).

## Step 0 — Scaffold (optional; skip if writing manually)

```bash milo-docs:skip reason=creates-local-project
uv run milo new my_cli
```

Produces `app.py`, `tests/test_app.py`, `conftest.py`, and a `README.md` — the
same shape this doc walks through. Scaffold names must be lowercase with
underscores (`my_cli`, not `My-CLI`). If the directory exists, the command
refuses to overwrite; pick another name or delete the old one.

## Step 1 — Write the function

```python milo-docs:compile
# my_cli/app.py
from milo import CLI

cli = CLI(name="my_cli", description="What it does", version="0.1")


@cli.command("greet", description="Say hello")
def greet(name: str, loud: bool = False) -> str:
    """Greet someone.

    Args:
        name: Person to greet.
        loud: SHOUT if true.
    """
    message = f"Hello, {name}!"
    return message.upper() if loud else message


if __name__ == "__main__":
    cli.run()
```

Rules you can rely on:

- Type hints become the JSON Schema for the MCP tool — no separate schema file.
- Parameters without a default are required; parameters with defaults are optional.
- The docstring's `Args:` section becomes per-parameter `description` in the schema.
- Structured return values are serialized to JSON and returned as MCP
  `structuredContent`; string results are returned as text content.
- Add `annotations={"readOnlyHint": True}` etc. in the `@cli.command` decorator
  to set MCP behavioral hints. See `AGENTS.md`.
- Use `Annotated[T, Positional("NAME")]` or `Option(aliases=("-n",))` to
  preserve established terminal syntax without changing MCP parameter names.
- Use `surfaces=("cli",)` for long-running human commands that agents must not
  discover or call.
- Return structured values; use `terminal_renderer=` for plain human output
  instead of printing from a reusable handler.

## Step 2 — Run the CLI

```bash milo-docs:skip reason=requires-prior-scaffold
uv run python my_cli/app.py greet --name Alice
# → Hello, Alice!

uv run python my_cli/app.py greet --name Alice --loud
# → HELLO, ALICE!

uv run python my_cli/app.py --help
# → usage and command listing
```

If `--help` lists your command, `@cli.command` is wired correctly.

## Step 3 — Verify the MCP tool schema

```bash milo-docs:skip reason=requires-prior-scaffold
uv run python my_cli/app.py --llms-txt
```

Look for these lines:

```
**greet**: Say hello
  Parameters: `--name` (string, **required**), `--loud` (boolean, optional, default: False)
```

If `--name` shows `**required**` and `--loud` shows the default, the JSON Schema
is correct. If not, check that type hints are on both parameters.

## Step 4 — Register with Claude

Use the `claude` CLI (part of Claude Code) to register your CLI as an MCP server:

```bash milo-docs:skip reason=requires-claude-cli-and-user-registration
claude mcp add --transport stdio my_cli -- \
  uv run python /absolute/path/to/my_cli/app.py --mcp
```

The flag after `--` tells milo to speak JSON-RPC on stdin/stdout instead of
parsing argv. Nothing else changes about your code.

Alternative — register in the **milo gateway** (useful when you have several
CLIs and want a single MCP entrypoint):

```bash milo-docs:skip reason=mutates-user-mcp-registry
uv run python /absolute/path/to/my_cli/app.py --mcp-install
claude mcp add --transport stdio milo -- uv run python -m milo.gateway --mcp
```

The gateway namespaces tools: your `greet` becomes `my_cli.greet`.

## Step 5 — Verify from inside Claude

In a fresh Claude Code session, run:

```
/mcp
```

You should see `my_cli` listed with `greet` as a tool. Call it:

> Use the `greet` tool to greet "Bob"

If you registered the milo gateway alternative, use the namespaced
`my_cli.greet` tool instead.

Expected result: Claude calls the tool, the tool returns `"Hello, Bob!"`,
Claude echoes it back.

## Step 6 — Self-diagnose with `milo verify`

Before registering with Claude (or any time you break something), run:

```bash milo-docs:skip reason=requires-prior-scaffold
uv run milo verify my_cli/app.py
```

All ten checks should pass:

```
✓ imports: loaded app.py
✓ cli_located: found CLI instance (name='my_cli')
✓ commands_registered: 1 command(s) registered
✓ schemas_generate: 1 schema(s) generated; all params documented
✓ mcp_list_tools: 1 tool(s) listed with valid inputSchema
✓ mcp_discover: server/discover advertises 2026-07-28
✓ mcp_apps_in_process: 0 tool link(s) and 0 UI resource(s) agree; 0 resource(s) readable
✓ mcp_apps_gateway: gateway preserves 0 tool link(s) and 0 UI resource(s)
✓ mcp_transport: subprocess modern discovery and legacy fallback succeeded; 1 tool(s) over JSON-RPC
✓ mcp_apps_transport: 0 tool link(s) and 0 UI resource(s) agree over JSON-RPC; 0 resource(s) readable
```

A `⚠ schemas_generate` row listing `parameter 'X' has no description` means a
typed parameter is missing an `Args:` entry (or `Annotated[..., Description(...)]`).
A `✗` row is a failure — read the details and fix before continuing.

The three `mcp_apps_*` identities are stable CI diagnostics. They negotiate the
extension, compare tool/resource/gateway links, and read each registered UI
resource in-process and over subprocess JSON-RPC. Milo validates the URI,
MIME/profile, metadata, and `str`/base64 payload shape; it never parses or
interprets application HTML.

`milo verify` exits 0 on warnings, nonzero on failures. Wire it into CI.

## When things go wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Tool doesn't appear after `claude mcp add` | MCP server process failed to start | Run `uv run python app.py --mcp` manually; watch stderr. Any Python import error is fatal. |
| Tool appears but call returns `isError: True` with `argument: "name"` | Required arg was not supplied by the caller | Claude sometimes calls without all args — the error payload tells you which is missing. |
| Tool returns `isError: True` with no `errorData.argument` | User code raised a plain exception | Raise `milo.MiloError(ErrorCode.INP_*, "…", argument="name", constraint={…})` so error data is structured. |
| `print()` breaks the protocol | MCP uses stdout for JSON-RPC; any other stdout write corrupts the stream | Use the provided `Context` (`ctx.info`, `ctx.error`) or write to stderr. |
| Schema is missing a parameter | Parameter is typed as `Context` (or named `ctx`) | Correct — these are injected at dispatch time and intentionally excluded from the schema. See `function_to_schema` in `src/milo/schema.py`. |
| Lazy command exits with `M-CMD-004` | Its module or named attribute could not import | Use `errorData.importPath` or the terminal hint to fix the dotted path or installation. |
| Non-serializable return type | Return value can't be JSON-encoded | Return `dict`, `list`, `str`, `int`, `float`, `bool`, `None`, or a `@dataclass`. |
| Client gets JSON-RPC `-32022` | The request declared an unsupported MCP protocol version in `_meta` | Retry with one of `error.data.supported`, or use the legacy `initialize` handshake for `2025-11-25`. |

## Error data contract (important for agents)

When a tool call fails, the response includes an `errorData` dict you can
parse to repair the call without guessing:

```json
{
  "content": [{"type": "text", "text": "Error: ..."}],
  "isError": true,
  "errorData": {
    "tool": "greet",
    "argument": "name",
    "reason": "missing_required_argument",
    "suggestion": "Provide 'name'.",
    "schema": {"type": "object", "properties": {...}, "required": ["name"]}
  }
}
```

Milo enforces requiredness, types, enums, lengths, item counts, patterns, and
numeric bounds before command handlers run. The same generated schema governs
`cli.invoke()`, `cli.call()`, `cli.call_raw()`, and MCP `tools/call`; loose
string inputs are coerced when the declared type is numeric, boolean, array, or
object. Constraint failures include stable `M-INP-*` repair data:

```json
{
  "errorData": {
    "errorCode": "M-INP-007",
    "argument": "env",
    "reason": "constraint_violation",
    "constraint": {"minLength": 1},
    "example": "x",
    "suggestion": "Use at least 1 character(s)."
  }
}
```

Parse these fields. Don't rely on the error message string.

## Test your CLI

Copy `examples/greet/tests/test_greet.py` to `my_cli/tests/test_greet.py`,
rename the imports, and edit the assertions. The command-level layers (schema, direct
dispatch, MCP dispatch) cover the common regression surface; `milo new` also
adds a `milo verify` test for the full agent-facing CLI. See
[`testing.md`](./testing.md) for the full testing story.

```bash milo-docs:skip reason=requires-prior-scaffold
uv run pytest my_cli/tests/ -v
uv run milo verify my_cli/app.py
```

## Next

- Rich schema constraints: `Annotated[str, MinLen(1), MaxLen(100)]`. See `AGENTS.md`.
- Streaming progress: yield `Progress(step, total, status)` from a generator command.
- Tool annotations: `@cli.command("deploy", annotations={"destructiveHint": True})`.
- Optional embedded UI: pair `@cli.ui_resource("ui://...")` with
  `ui=MCPAppToolMeta("ui://...")`; keep the command's text/structured fallback.
  The Milo gateway negotiates child UI support and rewrites resource links per
  CLI, so identical child URIs stay collision-free.
- Groups and subcommands: `cli.group("db")` + `@db.command("migrate")`.
- Middleware: `cli.before_command(hook)` / `cli.after_command(hook)`.

For the architecture and design constraints you must respect when extending
milo itself, read [`AGENTS.md`](../AGENTS.md).
