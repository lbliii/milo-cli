# Testing a milo CLI

A milo CLI has four test layers, each short. The template at
[`examples/greet/tests/test_greet.py`](../examples/greet/tests/test_greet.py)
shows the command-level layers. New projects from `milo new` include all four.
Copy the file into your CLI's `tests/` directory and edit the imports and
assertions — the structure is the same for every CLI.

## Layer 1 — Schema

The JSON Schema generated from your function's type hints must match what MCP
clients will see. Most schema drift is caught here.

```python milo-docs:compile
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

```python milo-docs:compile
def test_greet_argv():
    result = cli.invoke(["greet", "--name", "Alice"])
    assert result.exit_code == 0
    assert "Hello, Alice!" in result.output
```

For direct calls that bypass argv parsing, use `cli.call_raw(name, **kwargs)`.

Host integrations can test output and approval behavior without patching
`sys.stdin` or `sys.stderr` by passing a context to `call()`:

```python milo-docs:compile
import io

from milo import CLI, Context

cli = CLI(name="hosted")

@cli.command("deploy")
def deploy(ctx: Context = None) -> bool:
    ctx.info("requested")
    return ctx.confirm("Approve?")

output = io.StringIO()
ctx = Context(
    color=False,
    output_sink=output,
    interactive=False,
    confirm_strategy=lambda _message, *, default=False: True,
)

assert cli.call("deploy", ctx=ctx) is True
assert output.getvalue() == "info: requested\n"
```

Use `NullOutputSink()` instead when the host intentionally discards all
diagnostics and progress.

## Layer 3 — MCP dispatch

Verify that the JSON-RPC `tools/call` path returns what agents expect, including
error data when a required argument is missing.

```python milo-docs:compile
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

## Layer 4 — `milo verify`

Run the same self-diagnosis that agent quickstarts and scaffolded projects use.
This checks imports, CLI discovery, schema generation, MCP `tools/list`, and a
subprocess MCP handshake. It also negotiates MCP Apps in-process and over
JSON-RPC, reads every `ui://` resource, and proves tool/resource links survive
the gateway projection. Failures use the stable `mcp_apps_in_process`,
`mcp_apps_gateway`, and `mcp_apps_transport` check names.

Milo validates MCP Apps URI, MIME/profile, metadata, and text/base64 transport
shape. It does not parse application HTML. A warning still exits 0; any failed
conformance check exits 1 and includes the next repair action.

```python milo-docs:compile
from pathlib import Path

from milo.verify import verify


def test_milo_verify_passes():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    report = verify(str(app_path))
    assert report.exit_code == 0, report.format()
```

## When to use `assert_renders` / `assert_state` / `assert_saga`

For interactive apps (forms, wizards, TUIs), use the helpers in
[`milo.testing`](../src/milo/testing/). They let you feed actions to a reducer
and snapshot-test the rendered output. These are for *interactive* state, not
CLI dispatch — Layers 1-3 cover schema, direct dispatch, and MCP dispatch.

## Running tests

```bash milo-docs:skip reason=includes-full-ci-and-recursive-docs-check
# Full suite
make test

# A single example
uv run pytest examples/greet/tests/ -v

# Verify an agent-facing CLI
uv run milo verify examples/greet/app.py

# Verify built-in templates and tagged docs snippets
make docs-test

# Verify release version, tag, changelog, and release-note alignment
make release-status

# With coverage (project enforces 80% floor)
make test-cov
```

For normal `src/` changes, CI requires a new non-empty `changelog.d/*.md`
fragment. For a release-cut PR, apply the `skip-changelog` label after
fragments have been compiled into `CHANGELOG.md` and the new
`site/content/releases/<version>.md` file. `make release-status` is the
release-side guard that catches leftover or empty fragments before publishing.

## Free-threading (Python 3.14t)

Milo runs its test suite with `PYTHON_GIL=0` on 3.14t builds so threading bugs
surface in CI. If your CLI adds mutable global state, add a test that exercises
concurrent calls — see `tests/test_effects_stress.py` and `tests/test_state.py`
for patterns.
