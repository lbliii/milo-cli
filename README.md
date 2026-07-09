# ᗣᗣ Milo

[![PyPI version](https://img.shields.io/pypi/v/milo-cli.svg)](https://pypi.org/project/milo-cli/)
[![Build Status](https://github.com/lbliii/milo-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/lbliii/milo-cli/actions/workflows/ci.yml)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://pypi.org/project/milo-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**One typed Python function becomes a human CLI command, an MCP tool, and an
agent-readable discovery entry.**
([evidence: one-definition-three-surfaces](./public-claims.json))

<!--
Launch video: replace this comment with the final 60–90 second recording.
The verified shot list and clean-machine commands live in docs/launch-demo-script.md.
-->

## Prove It in 60 Seconds

With [`uv`](https://docs.astral.sh/uv/) installed, paste this into a clean
directory. `uv` downloads Python 3.14 and Milo when they are not already
available:

```bash milo-docs:skip reason=downloads-package-and-creates-project
uvx --python 3.14 --from milo-cli milo new hello_milo
uv run --python 3.14 --with milo-cli python hello_milo/app.py greet --name World
uv run --python 3.14 --with milo-cli milo verify hello_milo/app.py --transport both
```

The second command prints `Hello, World!`. The verifier
([evidence: verify-ten-check-conformance](./public-claims.json)) then exercises
import, schema generation, MCP discovery, MCP Apps tool/resource/gateway
conformance, a real subprocess JSON-RPC handshake, and the dependency-free ASGI
HTTP transport. Do not register a new tool until it reports zero failures.

Now give Claude Code the same file as a local stdio MCP server:

```bash milo-docs:skip reason=requires-claude-cli-and-user-registration
claude mcp add --transport stdio hello_milo -- \
  uv run --python 3.14 --with milo-cli python "$PWD/hello_milo/app.py" --mcp
```

Ask Claude to “use the `greet` tool to greet Ada,” or call the same function by
hand:

```bash milo-docs:skip reason=requires-prior-scaffold
uv run --python 3.14 --with milo-cli python hello_milo/app.py greet --name Ada
```

---

## What is Milo?

Milo is a Python framework where every CLI is simultaneously a terminal app, a command-line tool, and an MCP server. Write one function with type annotations and a docstring — Milo generates the argparse subcommand, the MCP tool schema, and the llms.txt entry automatically.

**Why people pick it:**

- **Every CLI is an MCP server** — `@cli.command` produces an argparse subcommand, MCP tool, and llms.txt entry from one function. AI agents discover and call your tools with zero extra code.
- **Local or hosted MCP** — run stdio with `--mcp`, embed `cli.asgi_app()` in any ASGI host, or install `milo-cli[http]` for the standalone `--mcp-http` adapter.
- **Dual-mode commands** — The same command shows an interactive UI when a human runs it, and returns structured JSON when an AI calls it via MCP.
- **Annotated schemas** — Type hints + `Annotated` constraints generate rich JSON Schema, and Milo enforces it before handlers run.
- **Streaming progress** — Commands that yield `Progress` objects stream notifications to MCP clients in real time.
- **Elm Architecture** — Immutable state, pure reducers, declarative views. Every state transition is explicit and testable.
- **Free-threading ready** — Built for Python 3.14t (PEP 703). Sagas run on `ThreadPoolExecutor` with no GIL contention. ([evidence: free-threaded-runtime](./public-claims.json))
- **One runtime dependency** — Just `kida-templates`. No click, no rich, no curses. ([evidence: one-runtime-dependency](./public-claims.json))

## Use Milo For

- **AI agent toolchains** — Every CLI doubles as an MCP server; register multiple CLIs behind a single gateway
- **Interactive CLI tools** — Wizards, installers, configuration prompts, and guided workflows
- **Dual-mode commands** — Interactive when a human runs them, structured when an AI calls them
- **Multi-screen terminal apps** — Declarative flows with `>>` operator for screen-to-screen navigation
- **Forms and data collection** — Text, select, confirm, and password fields with validation
- **Dev tools with hot reload** — `milo dev` watches templates and live-reloads on change
- **Session recording and replay** — Record user sessions to JSONL, replay for debugging or CI regression tests

---

## Installation

**Requires Python 3.14+.** If you don't have it: `uv python install 3.14`.

```bash
pip install milo-cli
```

The dependency-free ASGI app is included in the base package. Install the
optional standalone HTTP adapter only when needed:

```bash
pip install 'milo-cli[http]'
```

The PyPI package is **milo-cli**; import the **`milo`** namespace in Python. The `milo` console command is installed with the package.

---

## Quick Start

> **Coding agents**: jump to [`docs/agent-quickstart.md`](./docs/agent-quickstart.md)
> for a 5-minute walkthrough from `@cli.command` to a verified Claude MCP tool call.
> See also [`docs/testing.md`](./docs/testing.md) for the test template.

Migrating an established framework or developer CLI? Use the
[mature-CLI adoption guide](https://lbliii.github.io/milo-cli/docs/get-started/migrate-existing-cli/framework-adoption/)
to inventory compatibility, phase the cutover, and add an exact-version
downstream canary before switching entry points.

### AI-Native CLI

| Function | Description |
|----------|-------------|
| `CLI(name, description, version)` | Create a CLI application |
| `@cli.command(name, description)` | Register a typed command |
| `cli.group(name, description)` | Create a command group |
| `cli.run()` | Parse args and dispatch |
| `cli.asgi_app()` | Embed modern MCP Streamable HTTP in an ASGI host |
| `cli.call("cmd", **kwargs)` | Programmatic invocation |
| `--mcp` | Run as MCP server |
| `--mcp-http` | Run the optional standalone HTTP adapter on loopback |
| `--llms-txt` | Generate AI discovery doc |
| `--mcp-install` | Register in gateway |
| `annotations={...}` | MCP behavioral hints |
| `ui=MCPAppToolMeta("ui://...")` | Link a tool to an MCP Apps UI resource |
| `Annotated[str, MinLen(1)]` | Schema constraints |
| `Annotated[str, Positional("NAME")]` | Positional CLI presentation |
| `Option(aliases=("-n",))` | Compatible option aliases |
| `surfaces=("cli",)` | Keep long-running commands out of agent discovery |
| `terminal_renderer=...` | Human output over structured command results |

### Interactive Apps

| Function | Description |
|----------|-------------|
| `App(template, reducer, initial_state)` | Create a single-screen app |
| `App.from_flow(flow)` | Create a multi-screen app from a `Flow` |
| `form(*specs)` | Run an interactive form, return `{field: value}` |
| `FlowScreen(name, template, reducer)` | Define a named screen |
| `flow = screen_a >> screen_b` | Chain screens into a flow |
| `ctx.run_app(reducer, template, state)` | Bridge CLI commands to interactive apps |
| `quit_on`, `with_cursor`, `with_confirm` | Reducer combinator decorators |
| `Cmd(fn)`, `Batch(cmds)`, `Sequence(cmds)` | Side effects on thread pool |
| `ViewState(cursor_visible=True, ...)` | Declarative terminal state |
| `DevServer(app, watch_dirs)` | Hot-reload dev server |

---

## Features

| Feature | Description | Docs |
|---------|-------------|------|
| **MCP Server** | Every CLI serves local stdio and embeddable modern Streamable HTTP from the same command contract | [MCP →](https://lbliii.github.io/milo-cli/docs/build-clis/mcp/) |
| **MCP Gateway** | Single gateway aggregates all registered Milo CLIs for unified AI agent access | [MCP →](https://lbliii.github.io/milo-cli/docs/build-clis/mcp/) |
| **Tool Annotations** | Declare `readOnlyHint`, `destructiveHint`, `idempotentHint` per MCP spec | [MCP →](https://lbliii.github.io/milo-cli/docs/build-clis/mcp/) |
| **Streaming Progress** | Commands yield `Progress` objects; MCP clients receive real-time notifications | [MCP →](https://lbliii.github.io/milo-cli/docs/build-clis/mcp/) |
| **Schema Constraints** | `Annotated[str, MinLen(1), MaxLen(100)]` generates and enforces rich JSON Schema | [CLI →](https://lbliii.github.io/milo-cli/docs/build-clis/commands/) |
| **llms.txt** | Generate AI-readable discovery documents from CLI command definitions | [llms.txt →](https://lbliii.github.io/milo-cli/docs/build-clis/llms/) |
| **Middleware** | Intercept MCP calls and CLI commands for logging, auth, and transformation | [CLI →](https://lbliii.github.io/milo-cli/docs/build-clis/commands/) |
| **Observability** | Built-in request logging with latency stats (`milo://stats` resource) | [MCP →](https://lbliii.github.io/milo-cli/docs/build-clis/mcp/) |
| **State Management** | Redux-style `Store` with dispatch, listeners, middleware, and saga scheduling | [State →](https://lbliii.github.io/milo-cli/docs/build-apps/state/) |
| **Commands** | Lightweight `Cmd` thunks, `Batch`, `Sequence`, `TickCmd` for one-shot effects | [Commands →](https://lbliii.github.io/milo-cli/docs/build-apps/commands-effects/) |
| **Sagas** | Generator-based side effects: `Call`, `Put`, `Select`, `Fork`, `Delay`, `Retry`, `Race`, `All`, `Take`, and more | [Sagas →](https://lbliii.github.io/milo-cli/docs/build-apps/sagas/) |
| **ViewState** | Declarative terminal state (`cursor_visible`, `alt_screen`, `window_title`, `mouse_mode`) | [Commands →](https://lbliii.github.io/milo-cli/docs/build-apps/commands-effects/) |
| **Flows** | Multi-screen state machines with `>>` operator and custom transitions | [Flows →](https://lbliii.github.io/milo-cli/docs/build-apps/flows/) |
| **Forms** | Text, select, confirm, password fields with validation and TTY fallback | [Forms →](https://lbliii.github.io/milo-cli/docs/build-apps/forms/) |
| **Input Handling** | Cross-platform key reader with VT100/xterm escape sequence support (arrows, F-keys, modifiers) | [Input →](https://lbliii.github.io/milo-cli/docs/build-apps/input/) |
| **Templates** | Kida-powered terminal rendering with built-in form, field, help, and progress templates | [Templates →](https://lbliii.github.io/milo-cli/docs/build-apps/templates/) |
| **Dev Server** | `milo dev` with filesystem polling and `@@HOT_RELOAD` dispatch | [Dev →](https://lbliii.github.io/milo-cli/docs/build-apps/dev/) |
| **Session Recording** | JSONL action log with state hashes for debugging and regression testing | [Testing →](https://lbliii.github.io/milo-cli/docs/quality/testing/) |
| **Snapshot Testing** | `assert_renders`, `assert_state`, `assert_saga` for deterministic test coverage | [Testing →](https://lbliii.github.io/milo-cli/docs/quality/testing/) |
| **Pipeline** | Declarative multi-phase workflows with dependency graphs, retry policies, and output capture | [Pipeline →](https://lbliii.github.io/milo-cli/docs/quality/pipeline/) |
| **Help Rendering** | `HelpRenderer` — drop-in `argparse.HelpFormatter` using Kida templates | [Help →](https://lbliii.github.io/milo-cli/docs/build-clis/help/) |
| **Context** | Injectable output, interaction, approvals, global options, and `run_app()` bridge | [Context →](https://lbliii.github.io/milo-cli/docs/build-clis/context/) |
| **Configuration** | `Config` with validation, init scaffolding, and profile support | [Config →](https://lbliii.github.io/milo-cli/docs/about/concepts/configuration/) |
| **Shell Completions** | Generate bash/zsh/fish completions from CLI definitions | [CLI →](https://lbliii.github.io/milo-cli/docs/build-clis/commands/) |
| **Doctor Diagnostics** | `run_doctor()` validates environment, dependencies, and config health | [CLI →](https://lbliii.github.io/milo-cli/docs/build-clis/commands/) |

---

## Examples Index

Pick the example closest to your use case, copy its `app.py`, and adapt. See [examples/README.md](examples/README.md) for run commands, copy paths, and tested starting points.

For a recording-ready integration demo instead of a copy path, run the
[Waypoint showcase](showcase/waypoint/): three parallel agents journal a race
through hooks and CLI, a shell-less agent reads and picks through MCP, and a
human gets the same history as a TUI and MCP Apps DAG.

**CLIs (typed function → CLI + MCP + llms.txt)**

| What you want to build | Example | Key APIs |
|---|---|---|
| The simplest possible CLI | [examples/greet](examples/greet) | `CLI`, `@cli.command` |
| Dual-mode CLI ↔ MCP server (flagship) | [examples/deploy](examples/deploy) | `Annotated`, `MinLen`, `Context`, `Progress`, `--mcp` |
| MCP tool with a negotiated interactive UI resource | [examples/mcp_app](examples/mcp_app) | Dependency-free HTML, `ui_resource`, `MCPAppToolMeta`, structured fallback |
| Context injection, host-owned output, progress, confirms | [examples/ctxdemo](examples/ctxdemo) | `Context`, `OutputSink`, `ctx.progress`, `ctx.confirm` |
| Nested command groups (`app repo list`) | [examples/groups](examples/groups) | `cli.group()`, `walk_commands` |
| Fast startup via deferred imports | [examples/lazyapp](examples/lazyapp) | `cli.lazy_command()` |
| Production CLI with hooks, completions, doctor | [examples/devtool](examples/devtool) | `run_doctor`, `before_command`/`after_command`, did-you-mean, completions |
| AI-native CLI surfacing tools + resources | [examples/taskman](examples/taskman) | `@cli.command`, `@cli.resource`, `--format`, `--llms-txt`, `--mcp` |
| Advanced terminal reports and diagnostics | [examples/outputgallery](examples/outputgallery) | `Context.render`, Kida templates, character maps, JSON output |

**Configuration, plugins, pipelines**

| What you want to build | Example | Key APIs |
|---|---|---|
| TOML config with profiles + overlays | [examples/configapp](examples/configapp) | `Config`, `ConfigSpec`, `Config.load`, `Config.validate` |
| Plugin system with hooks + listeners | [examples/pluggable](examples/pluggable) | `HookRegistry`, `define`, `on`, `invoke` |
| Multi-phase pipeline with deps + retries | [examples/buildpipe](examples/buildpipe) | `Pipeline`, `Phase`, `PhasePolicy`, `>>` |

**Interactive TUIs (`App` + reducer)**

| What you want to build | Example | Key APIs |
|---|---|---|
| The simplest TUI | [examples/counter](examples/counter) | `App.from_dir`, reducer combinators |
| Modal input with derived filtering | [examples/todo](examples/todo) | tuple state, `quit_on`, derived views |
| Tick-driven animation | [examples/stopwatch](examples/stopwatch) | `tick_rate`, `@@TICK`, `quit_on` |
| Scrollable viewport with saga I/O | [examples/filepicker](examples/filepicker) | viewport, sagas, frozen tuples |
| Multi-screen flow with forms | [examples/wizard](examples/wizard) | `Flow`, `FlowScreen`, `make_form_reducer`, `FieldSpec` |

**Async work (sagas + Cmd pattern)**

| What you want to build | Example | Key APIs |
|---|---|---|
| Sagas for async side effects | [examples/fetcher](examples/fetcher) | `Call`, `Put`, `Select`, `Retry` |
| Parallel concurrent work | [examples/downloader](examples/downloader) | `Fork`, `Call`, `Delay`, `Timeout` |
| Bubbletea-style Cmd thunks | [examples/spinner](examples/spinner) | `Cmd`, `Batch`, `TickCmd`, `ViewState` |
| Live rendering outside an App | [examples/liverender](examples/liverender) | `milo.live.LiveRenderer`, `Spinner`, `terminal_env` |

> Don't see your use case? Run `milo new <name>` to scaffold a fresh CLI with tests, then `milo verify app.py` to confirm it works.

---

## Usage

<details>
<summary><strong>Dual-Mode Commands</strong> — Interactive for humans, structured for AI</summary>

```python
from milo import CLI, Context, Action, Quit, SpecialKey
from milo.streaming import Progress
from typing import Annotated
from milo import MinLen

cli = CLI(name="deployer", description="Deploy services")

@cli.command("deploy", description="Deploy a service", annotations={"destructiveHint": True})
def deploy(
    environment: Annotated[str, MinLen(1)],
    service: Annotated[str, MinLen(1)],
    ctx: Context = None,
) -> dict:
    """Deploy a service to an environment."""
    # Interactive mode: show confirmation UI
    if ctx and ctx.is_interactive:
        if not ctx.confirm(f"Deploy {service} to {environment}?"):
            return {"status": "cancelled"}

    # Stream progress (MCP clients see real-time notifications)
    yield Progress(status=f"Deploying {service}", step=0, total=2)
    yield Progress(status="Verifying health", step=1, total=2)

    return {"status": "deployed", "environment": environment, "service": service}
```

Run by a human: interactive confirmation, then progress output.
Called via MCP: progress notifications stream, then structured JSON result.

</details>

<details>
<summary><strong>MCP Server & Gateway</strong> — AI agent integration</summary>

Every Milo CLI is automatically an MCP server:

```bash
# Run as MCP server (stdin/stdout JSON-RPC)
myapp --mcp

# Register with an AI host directly
claude mcp add --transport stdio myapp -- \
  uv run python "$PWD/examples/deploy/app.py" --mcp
```

For multiple CLIs, register them and run a single gateway:

```bash
# Register CLIs
taskman --mcp-install
deployer --mcp-install

# Run the unified gateway
uv run python -m milo.gateway --mcp

# Or register the gateway with your AI host
claude mcp add --transport stdio milo -- uv run python -m milo.gateway --mcp
```

The gateway namespaces tools automatically (`taskman.add`, `deployer.deploy`) and
rewrites negotiated MCP Apps `ui://` links without collisions. It preserves
`outputSchema`, `structuredContent`, tool annotations, resource metadata, and
streaming `Progress` notifications across child CLIs.

Built-in `milo://stats` resource exposes request latency, error counts, and throughput.

</details>

<details>
<summary><strong>Schema Constraints</strong> — Rich validation from type hints</summary>

```python
from typing import Annotated
from milo import CLI, MinLen, MaxLen, Gt, Lt, Pattern, Description

cli = CLI(name="app")

@cli.command("create-user", description="Create a user account")
def create_user(
    name: Annotated[str, MinLen(1), MaxLen(100), Description("Full name")],
    age: Annotated[int, Gt(0), Lt(200)],
    email: Annotated[str, Pattern(r"^[^@]+@[^@]+$")],
) -> dict:
    return {"name": name, "age": age, "email": email}
```

Generates JSON Schema with `minLength`, `maxLength`, `exclusiveMinimum`, `exclusiveMaximum`, `pattern`, and `description` — AI agents validate inputs before calling.

</details>

<details>
<summary><strong>Single-Screen App</strong> — Counter with keyboard input</summary>

```python
from milo import App, Action

def reducer(state, action):
    if state is None:
        return {"count": 0}
    if action.type == "@@KEY" and action.payload.char == " ":
        return {**state, "count": state["count"] + 1}
    return state

app = App(template="counter.kida", reducer=reducer, initial_state=None)
final_state = app.run()
```

**counter.kida:**
```
Count: {{ count }}

Press SPACE to increment, Ctrl+C to quit.
```

</details>

<details>
<summary><strong>Multi-Screen Flow</strong> — Chain screens with <code>>></code></summary>

```python
from milo import App
from milo.flow import FlowScreen

welcome = FlowScreen("welcome", "welcome.kida", welcome_reducer)
config = FlowScreen("config", "config.kida", config_reducer)
confirm = FlowScreen("confirm", "confirm.kida", confirm_reducer)

flow = welcome >> config >> confirm
app = App.from_flow(flow)
app.run()
```

Navigate between screens by dispatching `@@NAVIGATE` actions from your reducers. Add custom transitions with `flow.with_transition("welcome", "confirm", on="@@SKIP")`.

</details>

<details>
<summary><strong>Interactive Forms</strong> — Collect structured input</summary>

```python
from milo import form, FieldSpec, FieldType

result = form(
    FieldSpec("name", "Your name"),
    FieldSpec("env", "Environment", field_type=FieldType.SELECT,
              choices=("dev", "staging", "prod")),
    FieldSpec("confirm", "Deploy?", field_type=FieldType.CONFIRM),
)
# result = {"name": "Alice", "env": "prod", "confirm": True}
```

Tab/Shift+Tab navigates fields. Arrow keys cycle select options. Falls back to plain `input()` prompts when stdin is not a TTY.

</details>

<details>
<summary><strong>Sagas</strong> — Generator-based side effects</summary>

```python
from milo import Call, Put, Select, ReducerResult

def fetch_saga():
    url = yield Select(lambda s: s["url"])
    data = yield Call(fetch_json, (url,))
    yield Put(Action("FETCH_DONE", payload=data))

def reducer(state, action):
    if action.type == "@@KEY" and action.payload.char == "f":
        return ReducerResult({**state, "loading": True}, sagas=(fetch_saga,))
    if action.type == "FETCH_DONE":
        return {**state, "loading": False, "data": action.payload}
    return state
```

Saga effects: `Call`, `Put`, `Select`, `Fork`, `Delay`, `Retry`, `Timeout`, `TryCall`, `Race`, `All`, `Take`, `Debounce`, `TakeEvery`, `TakeLatest`.

For one-shot effects, use `Cmd` instead — no generator needed:

```python
from milo import Cmd, ReducerResult

def fetch_status():
    return Action("STATUS", payload=urllib.request.urlopen(url).status)

def reducer(state, action):
    if action.type == "CHECK":
        return ReducerResult(state, cmds=(Cmd(fetch_status),))
    return state
```

</details>

<details>
<summary><strong>Testing Utilities</strong> — Snapshot, state, and saga assertions</summary>

```python
from milo.testing import assert_renders, assert_state, assert_saga
from milo import Action, Call

# Snapshot test: render state through template, compare to file
assert_renders({"count": 5}, "counter.kida", snapshot="tests/snapshots/count_5.txt")

# Reducer test: feed actions, assert final state
assert_state(reducer, None, [Action("@@INIT"), Action("INCREMENT")], {"count": 1})

# Saga test: step through generator, assert each yielded effect
assert_saga(my_saga(), [(Call(fetch, ("url",), {}), {"data": 42})])
```

Set `MILO_UPDATE_SNAPSHOTS=1` to regenerate snapshot files.

</details>

---

## Architecture

<details>
<summary><strong>Elm Architecture</strong> — Model-View-Update loop</summary>

```
                    ┌──────────────┐
                    │   Terminal    │
                    │   (View)     │
                    └──────┬───────┘
                           │ Key events
                           ▼
┌──────────┐    ┌──────────────────┐    ┌──────────────┐
│  Kida    │◄───│      Store       │◄───│   Reducer    │
│ Template │    │  (State Tree)    │    │  (Pure fn)   │
└──────────┘    └──────────┬───────┘    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │    Sagas     │
                    │ (Side Effects│
                    │  on ThreadPool)
                    └──────────────┘
```

1. **Model** — Immutable state (plain dicts or frozen dataclasses)
2. **View** — Kida templates render state to terminal output
3. **Update** — Pure `reducer(state, action) -> state` functions
4. **Effects** — `Cmd` thunks (one-shot) or generator-based sagas (multi-step) on `ThreadPoolExecutor`

</details>

<details>
<summary><strong>Event Loop</strong> — App lifecycle</summary>

```
App.run()
  ├── Store(reducer, initial_state)
  ├── KeyReader (raw mode, escape sequences → Key objects)
  ├── TerminalRenderer (alternate screen buffer, flicker-free updates)
  ├── Optional: tick thread (@@TICK at interval)
  ├── Optional: SIGWINCH handler (@@RESIZE)
  └── Loop:
        read key → dispatch @@KEY → reducer → re-render
        until state.submitted or @@QUIT
```

</details>

<details>
<summary><strong>Builtin Actions</strong> — Event vocabulary</summary>

| Action | Trigger | Payload |
|--------|---------|---------|
| `@@INIT` | Store creation | — |
| `@@KEY` | Keyboard input | `Key(char, name, ctrl, alt, shift)` |
| `@@TICK` | Timer interval | — |
| `@@RESIZE` | Terminal resize | `(cols, rows)` |
| `@@NAVIGATE` | Screen transition | `screen_name` |
| `@@HOT_RELOAD` | Template file change | `file_path` |
| `@@EFFECT_RESULT` | Saga completion | `result` |
| `@@QUIT` | Ctrl+C | — |

</details>

---

## Documentation

| Section | Description |
|---------|-------------|
| [About](https://lbliii.github.io/milo-cli/docs/about/) | Philosophy, architecture, concepts, and lifecycle |
| [Get Started](https://lbliii.github.io/milo-cli/docs/get-started/) | Installation and quickstart |
| [Build CLIs](https://lbliii.github.io/milo-cli/docs/build-clis/) | Commands, groups, MCP, llms.txt, context, output, and help |
| [Build Apps](https://lbliii.github.io/milo-cli/docs/build-apps/) | State, reducers, templates, input, forms, flows, sagas, and live rendering |
| [Quality](https://lbliii.github.io/milo-cli/docs/quality/) | Testing, verification, debugging, and pipelines |
| [Reference](https://lbliii.github.io/milo-cli/docs/reference/) | Schema, dispatch, error codes, actions, and types |

---

## Development

```bash
git clone https://github.com/lbliii/milo-cli.git
cd milo-cli
# Uses Python 3.14t by default (.python-version)
uv sync --group dev --python 3.14t
PYTHON_GIL=0 uv run --python 3.14t pytest tests/
make ci   # optional: ruff + ty + tests with coverage
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for repository setup, proof, changelog,
and pull-request expectations. Report suspected vulnerabilities through the
private contact in [SECURITY.md](SECURITY.md), not a public issue.

---

## The Bengal Ecosystem

A structured reactive stack — every layer written in pure Python for 3.14t free-threading.

| | | | |
|--:|---|---|---|
| **ᓚᘏᗢ** | [Bengal](https://github.com/lbliii/bengal) | Static site generator | [Docs](https://lbliii.github.io/bengal/) |
| **∿∿** | [Purr](https://github.com/lbliii/purr) | Content runtime | — |
| **⌁⌁** | [Chirp](https://github.com/lbliii/chirp) | Web framework | [Docs](https://lbliii.github.io/chirp/) |
| **=^..^=** | [Pounce](https://github.com/lbliii/pounce) | ASGI server | [Docs](https://lbliii.github.io/pounce/) |
| **)彡** | [Kida](https://github.com/lbliii/kida) | Template engine | [Docs](https://lbliii.github.io/kida/) |
| **ฅᨐฅ** | [Patitas](https://github.com/lbliii/patitas) | Markdown parser | [Docs](https://lbliii.github.io/patitas/) |
| **⌾⌾⌾** | [Rosettes](https://github.com/lbliii/rosettes) | Syntax highlighter | [Docs](https://lbliii.github.io/rosettes/) |
| **ᗣᗣ** | **Milo** (PyPI: `milo-cli`) | CLI framework ← You are here | [Docs](https://lbliii.github.io/milo-cli/) |

Python-native. Free-threading ready. No npm required.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
