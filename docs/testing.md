# Testing a milo CLI

A milo CLI has three test layers, each short. The template at
[`examples/greet/tests/test_greet.py`](../examples/greet/tests/test_greet.py)
shows all three. Copy the file next to your own CLI and edit the assertions —
the structure is the same for every CLI.

## Layer 1 — Schema

The JSON Schema generated from your function's type hints must match what MCP
clients will see. Most schema drift is caught here.

```python
from milo.schema import function_to_schema

def test_schema_matches_signature():
    schema = function_to_schema(my_command)
    assert schema["required"] == ["env"]
    assert schema["properties"]["env"]["type"] == "string"
```

See also `form_schema(*specs)` if your CLI drives an interactive form — it
returns a JSON Schema describing the form without running the TUI.

## Layer 2 — Direct dispatch

Verify that the function runs correctly when invoked through the CLI argv parser.
Use `cli.invoke(argv)` — it returns an `InvokeResult` with `output`, `exit_code`,
`result`, `stderr`, and `exception`. This is the test your CI should rely on most.

```python
def test_greet_argv():
    result = cli.invoke(["greet", "--name", "Alice"])
    assert result.exit_code == 0
    assert "Hello, Alice!" in result.output
```

For direct calls that bypass argv parsing, use `cli.call_raw(name, **kwargs)`.

## Layer 3 — MCP dispatch

Verify that the JSON-RPC `tools/call` path returns what agents expect, including
error data when a required argument is missing.

```python
from milo.mcp import _call_tool

def test_mcp_dispatch():
    result = _call_tool(cli, {"name": "greet", "arguments": {"name": "Agent"}})
    assert result["content"][0]["text"] == "Hello, Agent!"
    assert "isError" not in result

def test_mcp_missing_arg_has_argument_context():
    result = _call_tool(cli, {"name": "greet", "arguments": {}})
    assert result["isError"] is True
    assert result["errorData"]["argument"] == "name"
```

`errorData` is the structured diagnostic — when your handler raises a
`MiloError` with `argument=` and `constraint=` kwargs, those surface in the
response so agents can repair the call automatically.

## When to use `assert_renders` / `assert_state` / `assert_saga`

For interactive apps (forms, wizards, TUIs), use the helpers in
[`milo.testing`](../src/milo/testing/). They let you feed actions to a reducer
and snapshot-test the rendered output. These are for *interactive* state, not
CLI dispatch — the three layers above cover dispatch.

## Running tests

```bash
# Full suite
make test

# A single example
uv run pytest examples/greet/tests/ -v

# With coverage (project enforces 80% floor)
make test-cov
```

## Free-threading (Python 3.14t)

Milo runs its test suite with `PYTHON_GIL=0` on 3.14t builds so threading bugs
surface in CI. If your CLI adds mutable global state, add a test that exercises
concurrent calls — see `tests/test_freethreading.py` for patterns.
