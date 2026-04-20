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

```bash
uv run milo new my_cli
cd my_cli
```

Produces `app.py`, `tests/test_app.py`, `conftest.py`, and a `README.md` — the
same shape this doc walks through. Scaffold names must be lowercase with
underscores (`my_cli`, not `My-CLI`). If the directory exists, the command
refuses to overwrite; pick another name or delete the old one.

## Step 1 — Write the function

```python
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
- Return value is serialized to JSON and returned as MCP `structuredContent`.
- Add `annotations={"readOnlyHint": True}` etc. in the `@cli.command` decorator
  to set MCP behavioral hints. See `AGENTS.md`.

## Step 2 — Run the CLI

```bash
uv run python my_cli/app.py greet --name Alice
# → Hello, Alice!

uv run python my_cli/app.py greet --name Alice --loud
# → HELLO, ALICE!

uv run python my_cli/app.py --help
# → usage and command listing
```

If `--help` lists your command, `@cli.command` is wired correctly.

## Step 3 — Verify the MCP tool schema

```bash
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

```bash
claude mcp add my_cli -- uv run python /absolute/path/to/my_cli/app.py --mcp
```

The flag after `--` tells milo to speak JSON-RPC on stdin/stdout instead of
parsing argv. Nothing else changes about your code.

Alternative — register in the **milo gateway** (useful when you have several
CLIs and want a single MCP entrypoint):

```bash
uv run python /absolute/path/to/my_cli/app.py --mcp-install
claude mcp add milo -- uv run python -m milo.gateway --mcp
```

The gateway namespaces tools: your `greet` becomes `my_cli.greet`.

## Step 5 — Verify from inside Claude

In a fresh Claude Code session, run:

```
/mcp
```

You should see `my_cli` listed with `greet` as a tool. Call it:

> Use the `my_cli.greet` tool to greet "Bob"

Expected result: Claude calls the tool, the tool returns `"Hello, Bob!"`,
Claude echoes it back.

## Step 6 — Self-diagnose with `milo verify`

Before registering with Claude (or any time you break something), run:

```bash
uv run milo verify my_cli/app.py
```

All six checks should pass:

```
✓ imports: loaded app.py
✓ cli_located: found CLI instance (name='my_cli')
✓ commands_registered: 1 command(s) registered
✓ schemas_generate: 1 schema(s) generated; all params documented
✓ mcp_list_tools: 1 tool(s) listed with valid inputSchema
✓ mcp_transport: subprocess handshake succeeded; 1 tool(s) over JSON-RPC
```

A `⚠ schemas_generate` row listing `parameter 'X' has no description` means a
typed parameter is missing an `Args:` entry (or `Annotated[..., Description(...)]`).
A `✗` row is a failure — read the details and fix before continuing.

`milo verify` exits 0 on warnings, nonzero on failures. Wire it into CI.

## When things go wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Tool doesn't appear after `claude mcp add` | MCP server process failed to start | Run `uv run python app.py --mcp` manually; watch stderr. Any Python import error is fatal. |
| Tool appears but call returns `isError: True` with `argument: "name"` | Required arg was not supplied by the caller | Claude sometimes calls without all args — the error payload tells you which is missing. |
| Tool returns `isError: True` with no `errorData.argument` | User code raised a plain exception | Raise `milo.MiloError(ErrorCode.INP_*, "…", argument="name", constraint={…})` so error data is structured. |
| `print()` breaks the protocol | MCP uses stdout for JSON-RPC; any other stdout write corrupts the stream | Use the provided `Context` (`ctx.info`, `ctx.error`) or write to stderr. |
| Schema is missing a parameter | Parameter is typed as `Context` (or named `ctx`) | Correct — these are injected at dispatch time and intentionally excluded from the schema. See `function_to_schema` in `src/milo/schema.py`. |
| Non-serializable return type | Return value can't be JSON-encoded | Return `dict`, `list`, `str`, `int`, `float`, `bool`, `None`, or a `@dataclass`. |

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

For validation failures raised via `MiloError(argument="env", constraint={"minLength": 1})`:

```json
{
  "errorData": {
    "errorCode": "M-INP-001",
    "argument": "env",
    "constraint": {"minLength": 1},
    "example": "x",
    "suggestion": "..."
  }
}
```

Parse these fields. Don't rely on the error message string.

## Test your CLI

Copy `examples/greet/tests/test_greet.py` next to your `app.py`, rename the
imports, and edit the assertions. The three test layers (schema, direct
dispatch, MCP dispatch) cover the common regression surface. See
[`testing.md`](./testing.md) for the full testing story.

```bash
uv run pytest my_cli/tests/ -v
```

## Next

- Rich schema constraints: `Annotated[str, MinLen(1), MaxLen(100)]`. See `AGENTS.md`.
- Streaming progress: yield `Progress(step, total, status)` from a generator command.
- Tool annotations: `@cli.command("deploy", annotations={"destructiveHint": True})`.
- Groups and subcommands: `cli.group("db")` + `@db.command("migrate")`.
- Middleware: `cli.before_command(hook)` / `cli.after_command(hook)`.

For the architecture and design constraints you must respect when extending
milo itself, read [`AGENTS.md`](../AGENTS.md).
