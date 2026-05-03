# greet - minimal Milo CLI

The smallest Milo CLI that exercises the four public layers: schema generation,
CLI dispatch, llms.txt discovery, and MCP tool dispatch. Use this as the
starting point for a new command-first project.

## Run

```bash milo-docs:run cwd=.
uv run python examples/greet/app.py greet --name Alice
uv run python examples/greet/app.py greet --name Alice --loud
uv run python examples/greet/app.py --llms-txt
```

Run as an MCP server when you are wiring a client such as Claude Desktop:

```bash
uv run python examples/greet/app.py --mcp
```

## Test

```bash milo-docs:run cwd=.
uv run pytest examples/greet/tests/ -q
uv run milo verify examples/greet/app.py
```

The test file at `tests/test_greet.py` is a template covering the public contract:

- **Schema** — `function_to_schema(greet)` matches the signature.
- **Direct dispatch** — `cli.invoke([...])` returns the expected output.
- **Discovery** — `cli.generate_llms_txt()` includes the command contract.
- **MCP dispatch** — `_call_tool(cli, {...})` returns the expected response, and
  a missing required arg returns structured error data with `argument` context.

Copy this file next to your own `app.py` and edit the assertions.

## How this gets discovered by Claude

```bash milo-docs:skip reason=registers-user-mcp-gateway
uv run python examples/greet/app.py --mcp-install
```

This registers the CLI with the Milo gateway. See `docs/agent-quickstart.md` for
the end-to-end walkthrough.
