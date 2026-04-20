# greet — minimal milo CLI template

The smallest milo CLI that exercises all three protocols: CLI dispatch, MCP tool,
and llms.txt. Use this as the starting point for a new CLI — copy the folder,
rename, edit `app.py`.

## Run

```bash
# CLI
uv run python examples/greet/app.py greet --name Alice
uv run python examples/greet/app.py greet --name Alice --loud

# llms.txt (agent-readable catalog)
uv run python examples/greet/app.py --llms-txt

# MCP server (stdin/stdout JSON-RPC, for Claude et al.)
uv run python examples/greet/app.py --mcp
```

## Test

```bash
uv run pytest examples/greet/tests/ -v
```

The test file at `tests/test_greet.py` is a template covering the three layers:

- **Schema** — `function_to_schema(greet)` matches the signature.
- **Direct dispatch** — `cli.invoke([...])` returns the expected output.
- **MCP dispatch** — `_call_tool(cli, {...})` returns the expected response, and
  a missing required arg returns structured error data with `argument` context.

Copy this file next to your own `app.py` and edit the assertions.

## How this gets discovered by Claude

```bash
uv run python examples/greet/app.py --mcp-install
```

This registers the CLI with the milo gateway. See `docs/agent-quickstart.md` for
the end-to-end walkthrough.
