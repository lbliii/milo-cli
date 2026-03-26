# ᗣᗣ Milo

[![PyPI version](https://img.shields.io/pypi/v/milo.svg)](https://pypi.org/project/milo/)
[![Build Status](https://github.com/lbliii/milo/actions/workflows/tests.yml/badge.svg)](https://github.com/lbliii/milo/actions/workflows/tests.yml)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://pypi.org/project/milo/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**Template-driven CLI applications for free-threaded Python**

```python
from milo import App, Action

def reducer(state, action):
    if state is None:
        return {"count": 0}
    if action.type == "@@KEY" and action.payload.char == " ":
        return {**state, "count": state["count"] + 1}
    return state

app = App(template="counter.txt", reducer=reducer, initial_state=None)
final_state = app.run()
```

---

## What is Milo?

Milo is a framework for building interactive terminal applications in Python 3.14t. It uses the Elm Architecture (Model-View-Update) — an immutable state tree managed by pure reducer functions, a view layer driven by Kida templates, and generator-based sagas for side effects. The result is CLI apps that are predictable, testable, and free-threading ready.

**Why people pick it:**

- **Elm Architecture** — Immutable state, pure reducers, declarative views. Every state transition is explicit and testable.
- **Template-driven UI** — Render terminal output with Kida templates. Same syntax you use for HTML, now for CLI.
- **Free-threading ready** — Built for Python 3.14t (PEP 703). Sagas run on `ThreadPoolExecutor` with no GIL contention.
- **Declarative flows** — Chain multi-screen state machines with the `>>` operator. No manual navigation plumbing.
- **Built-in forms** — Text, select, confirm, and password fields with validation, keyboard navigation, and TTY fallback.
- **One runtime dependency** — Just `kida-templates`. No click, no rich, no curses.

## Use Milo For

- **Interactive CLI tools** — Wizards, installers, configuration prompts, and guided workflows
- **Multi-screen terminal apps** — Declarative flows with `>>` operator for screen-to-screen navigation
- **Forms and data collection** — Text, select, confirm, and password fields with validation
- **Dev tools with hot reload** — `milo dev` watches templates and live-reloads on change
- **Session recording and replay** — Record user sessions to JSONL, replay for debugging or CI regression tests
- **Styled terminal output** — Kida terminal templates with ANSI colors, progress bars, and live rendering

---

## Installation

```bash
pip install milo
```

Requires Python 3.14+

---

## Quick Start

| Function | Description |
|----------|-------------|
| `App(template, reducer, initial_state)` | Create a single-screen app |
| `App.from_flow(flow)` | Create a multi-screen app from a `Flow` |
| `app.run()` | Run the event loop, return final state |
| `Store(reducer, initial_state)` | Standalone state container |
| `combine_reducers(**reducers)` | Compose slice-based reducers |
| `form(*specs)` | Run an interactive form, return `{field: value}` |
| `FlowScreen(name, template, reducer)` | Define a named screen |
| `flow = screen_a >> screen_b` | Chain screens into a flow |
| `render_html(state, template)` | One-shot static HTML render |
| `DevServer(app, watch_dirs)` | Hot-reload dev server |

---

## Features

| Feature | Description | Docs |
|---------|-------------|------|
| **State Management** | Redux-style `Store` with dispatch, listeners, middleware, and saga scheduling | [State →](https://lbliii.github.io/milo/docs/usage/state/) |
| **Sagas** | Generator-based side effects: `Call`, `Put`, `Select`, `Fork`, `Delay` | [Sagas →](https://lbliii.github.io/milo/docs/usage/sagas/) |
| **Flows** | Multi-screen state machines with `>>` operator and custom transitions | [Flows →](https://lbliii.github.io/milo/docs/usage/flows/) |
| **Forms** | Text, select, confirm, password fields with validation and TTY fallback | [Forms →](https://lbliii.github.io/milo/docs/usage/forms/) |
| **Input Handling** | Cross-platform key reader with full escape sequence support (arrows, F-keys, modifiers) | [Input →](https://lbliii.github.io/milo/docs/usage/input/) |
| **Templates** | Kida-powered terminal rendering with built-in form, field, help, and progress templates | [Templates →](https://lbliii.github.io/milo/docs/usage/templates/) |
| **Dev Server** | `milo dev` with filesystem polling and `@@HOT_RELOAD` dispatch | [Dev →](https://lbliii.github.io/milo/docs/usage/dev/) |
| **Session Recording** | JSONL action log with state hashes for debugging and regression testing | [Testing →](https://lbliii.github.io/milo/docs/usage/testing/) |
| **Replay** | Time-travel debugging, speed control, step-by-step mode, CI hash assertions | [Testing →](https://lbliii.github.io/milo/docs/usage/testing/) |
| **Snapshot Testing** | `assert_renders`, `assert_state`, `assert_saga` for deterministic test coverage | [Testing →](https://lbliii.github.io/milo/docs/usage/testing/) |
| **Help Rendering** | `HelpRenderer` — drop-in `argparse.HelpFormatter` using Kida templates | [Help →](https://lbliii.github.io/milo/docs/usage/help/) |
| **Error System** | Structured error hierarchy with namespaced codes (`M-INP-001`, `M-STA-003`) | [Errors →](https://lbliii.github.io/milo/docs/reference/errors/) |

---

## Usage

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

app = App(template="counter.txt", reducer=reducer, initial_state=None)
final_state = app.run()
```

**counter.txt:**
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

welcome = FlowScreen("welcome", "welcome.txt", welcome_reducer)
config = FlowScreen("config", "config.txt", config_reducer)
confirm = FlowScreen("confirm", "confirm.txt", confirm_reducer)

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

Effects: `Call(fn, args)`, `Put(action)`, `Select(selector)`, `Fork(saga)`, `Delay(seconds)`.

</details>

<details>
<summary><strong>Middleware</strong> — Intercept and transform dispatches</summary>

```python
def logging_middleware(dispatch, get_state):
    def wrapper(action):
        print(f"Action: {action.type}")
        return dispatch(action)
    return wrapper

app = App(
    template="app.txt",
    reducer=reducer,
    initial_state=None,
    middleware=[logging_middleware],
)
```

</details>

<details>
<summary><strong>Dev Server</strong> — Hot reload templates</summary>

```bash
# Watch templates and reload on change
milo dev myapp:app --watch ./templates --poll 0.25
```

```python
from milo import App, DevServer

app = App(template="dashboard.txt", reducer=reducer, initial_state=None)
server = DevServer(app, watch_dirs=("./templates",), poll_interval=0.5)
server.run()
```

</details>

<details>
<summary><strong>Session Recording & Replay</strong> — Debug and regression testing</summary>

```python
# Record a session
app = App(template="app.txt", reducer=reducer, initial_state=None, record=True)
app.run()  # Writes to session.jsonl

# Replay for debugging
milo replay session.jsonl --speed 2.0 --diff

# CI regression: assert state hashes match
milo replay session.jsonl --assert --reducer myapp:reducer

# Step-by-step interactive replay
milo replay session.jsonl --step
```

</details>

<details>
<summary><strong>Testing Utilities</strong> — Snapshot, state, and saga assertions</summary>

```python
from milo.testing import assert_renders, assert_state, assert_saga
from milo import Action, Call

# Snapshot test: render state through template, compare to file
assert_renders({"count": 5}, "counter.txt", snapshot="tests/snapshots/count_5.txt")

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
4. **Effects** — Generator-based sagas scheduled on `ThreadPoolExecutor`

</details>

<details>
<summary><strong>Event Loop</strong> — App lifecycle</summary>

```
App.run()
  ├── Store(reducer, initial_state)
  ├── KeyReader (raw mode, escape sequences → Key objects)
  ├── LiveRenderer (kida terminal, flicker-free updates)
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
| [Get Started](https://lbliii.github.io/milo/docs/get-started/) | Installation and quickstart |
| [Usage](https://lbliii.github.io/milo/docs/usage/) | State, sagas, flows, forms, templates |
| [Testing](https://lbliii.github.io/milo/docs/usage/testing/) | Snapshots, recording, replay |
| [Reference](https://lbliii.github.io/milo/docs/reference/) | Complete API documentation |

---

## Development

```bash
git clone https://github.com/lbliii/milo.git
cd milo
# Uses Python 3.14t by default (.python-version)
uv sync --group dev --python 3.14t
PYTHON_GIL=0 uv run --python 3.14t pytest
```

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
| **ᗣᗣ** | **Milo** | CLI framework ← You are here | [Docs](https://lbliii.github.io/milo/) |

Python-native. Free-threading ready. No npm required.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
