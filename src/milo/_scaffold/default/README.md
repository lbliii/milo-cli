# {{name}}

A Milo CLI: one typed Python function becomes a human CLI command, an MCP tool
with a JSON Schema, and an llms.txt entry.

## Files

```text
{{name}}/
  app.py              # CLI definition and command handlers
  conftest.py         # Test path setup for the scaffold
  tests/
    test_app.py       # Schema, CLI dispatch, MCP dispatch, and verify tests
  README.md           # This guide
```

## Run the CLI

```bash
uv run --python 3.14 --with milo-cli python app.py greet --name Alice
```

Expected output:

```text
Hello, Alice!
```

Boolean defaults become flags:

```bash
uv run --python 3.14 --with milo-cli python app.py greet --name Alice --loud
```

Expected output:

```text
HELLO, ALICE!
```

Inspect the generated help:

```bash
uv run --python 3.14 --with milo-cli python app.py --help
uv run --python 3.14 --with milo-cli python app.py greet --help
```

## Inspect the Agent Contract

Generate an agent-readable command catalog:

```bash
uv run --python 3.14 --with milo-cli python app.py --llms-txt
```

Run as an MCP server over stdin/stdout:

```bash
uv run --python 3.14 --with milo-cli python app.py --mcp
```

MCP uses stdout for JSON-RPC. Do not use `print()` for progress or logs in code
that may run under `--mcp`; use `Context` output helpers or stderr boundary code.

## Test and Verify

```bash
uv run --python 3.14 --with milo-cli --with pytest pytest tests/ -v
uv run --python 3.14 --with milo-cli milo verify app.py
```

The generated test file covers four layers:

| Layer | What it checks |
|---|---|
| Schema | `function_to_schema(greet)` matches the function signature |
| Direct dispatch | `cli.invoke([...])` parses argv and returns expected output |
| MCP dispatch | `_call_tool(cli, {...})` returns content, structured `errorData`, and `server/discover` metadata |
| Verify | `milo verify app.py` passes import, schema, tools/list, discovery, and transport checks |

`milo verify` exits 0 when checks pass or only warnings are present. It exits
nonzero on failures that would make the CLI unsafe to register as an MCP tool.

## Edit Loop

1. Add or change `@cli.command(...)` functions in `app.py`.
2. Give every public parameter a type annotation.
3. Document every public parameter in the function docstring `Args:` section.
4. Return JSON-serializable values: `dict`, `list`, `str`, `int`, `float`, `bool`,
   `None`, or dataclasses built from those values.
5. Add matching tests in `tests/test_app.py`.
6. Rerun the test and verify commands below.

## CI

Use both command tests and `milo verify`:

```bash
uv run --python 3.14 --with milo-cli --with pytest pytest tests/ -v
uv run --python 3.14 --with milo-cli milo verify app.py
```

## Register with Claude

```bash
claude mcp add --transport stdio {{name}} -- \
  uv run --python 3.14 --with milo-cli python /absolute/path/to/{{name}}/app.py --mcp
```

The absolute path should point at this project's `app.py`.

## More

- [Public quickstart](https://lbliii.github.io/milo-cli/docs/get-started/quickstart/)
- [Agent quickstart](https://github.com/lbliii/milo-cli/blob/main/docs/agent-quickstart.md)
- [Testing guide](https://lbliii.github.io/milo-cli/docs/quality/testing/)
