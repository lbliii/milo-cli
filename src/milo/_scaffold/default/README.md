# {{name}}

A milo CLI: one typed function, three protocols (CLI, MCP server, llms.txt).

## Run

```bash
# CLI
uv run python app.py greet --name Alice
uv run python app.py greet --name Alice --loud

# llms.txt (agent-readable catalog)
uv run python app.py --llms-txt

# MCP server (stdin/stdout JSON-RPC, for Claude et al.)
uv run python app.py --mcp
```

## Test

```bash
uv run pytest tests/ -v
```

The test file covers three layers — schema, direct dispatch, MCP dispatch.
Add commands by adding `@cli.command(...)` functions to `app.py`, then add
matching tests in `tests/test_app.py`.

## Register with Claude

```bash
claude mcp add {{name}} -- uv run python /absolute/path/to/app.py --mcp
```

See the milo agent quickstart for the full walkthrough.
