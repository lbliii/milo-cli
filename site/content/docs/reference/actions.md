---
title: Built-in Actions
nav_title: Actions
description: Every action Milo dispatches automatically.
weight: 10
draft: false
lang: en
tags: [reference, actions]
keywords: [actions, events, built-in, dispatch]
category: reference
icon: lightning
---

Milo dispatches these actions automatically during the application lifecycle. Your reducers can handle any of them.

## Action reference

| Action | Trigger | Payload | Description |
|--------|---------|---------|-------------|
| `@@INIT` | Store creation | — | Dispatched once when the store is created. Use this to set initial state. |
| `@@KEY` | Keyboard input | `Key(char, name, ctrl, alt, shift)` | Dispatched for every keypress. The payload is a frozen `Key` dataclass. |
| `@@TICK` | Timer interval | — | Dispatched at the configured `tick_rate` interval. Use for animations, polling, or periodic updates. |
| `@@RESIZE` | Terminal resize | `(cols, rows)` | Dispatched when the terminal window is resized (via `SIGWINCH`). |
| `@@NAVIGATE` | Screen transition | `screen_name` | Dispatched by the flow system to move between screens. |
| `@@HOT_RELOAD` | Template file change | `file_path` | Dispatched by `DevServer` when a watched template file changes. |
| `@@EFFECT_RESULT` | Saga completion | `result` | Dispatched when a saga's `Call` effect completes. |
| `@@QUIT` | Ctrl+C | — | Dispatched when the user presses Ctrl+C. The app exits after processing this action. |
| `@@SAGA_ERROR` | Saga exception | `{error, type}` | Dispatched when an unhandled exception occurs in a saga. Payload includes the error message and exception type name. |
| `@@CMD_ERROR` | Cmd exception | `{error, type}` | Dispatched when an unhandled exception occurs in a `Cmd` thunk. Same payload shape as `@@SAGA_ERROR`. |
| `@@PIPELINE_START` | Pipeline begins | `pipeline_name` | Dispatched when a `Pipeline` starts execution. |
| `@@PIPELINE_COMPLETE` | Pipeline finishes | `pipeline_name` | Dispatched when a `Pipeline` completes all phases. |
| `@@PHASE_START` | Phase begins | `phase_name` | Dispatched when a pipeline phase starts. |
| `@@PHASE_COMPLETE` | Phase finishes | `phase_name` | Dispatched when a pipeline phase completes successfully. |
| `@@PHASE_FAILED` | Phase fails | `{name, error}` | Dispatched when a pipeline phase fails. |
| `@@PHASE_SKIPPED` | Phase skipped | `{name, error}` | Dispatched when a phase is skipped due to `PhasePolicy(on_fail="skip")`. |
| `@@PHASE_RETRY` | Phase retrying | `{name, error, attempt}` | Dispatched before a phase retry attempt. |
| `@@PHASE_LOG` | Phase output | `{name, line, stream, timestamp}` | Dispatched when `capture_output=True` and a phase writes to stdout/stderr. |

:::{tip}
All built-in action types are prefixed with `@@` to avoid collisions with your custom actions. You can access them programmatically via the `BUILTIN_ACTIONS` constant.
:::

## Custom actions

Define your own action types as plain strings:

```python
from milo import Action

Action("INCREMENT")
Action("ADD_TODO", payload="Buy milk")
Action("SET_THEME", payload="dark")
```

Action types are just strings. There's no registration step — dispatch any type and handle it in your reducer.

:::{dropdown} Action naming conventions
:icon: info

Common patterns from the Redux ecosystem:

| Pattern | Example | Use for |
|---------|---------|---------|
| `NOUN_VERB` | `TODO_ADDED` | Past-tense events |
| `VERB_NOUN` | `FETCH_DATA` | Imperative commands |
| `DOMAIN/ACTION` | `auth/LOGIN` | Namespaced actions |

Pick one convention and stick with it. Milo doesn't enforce any particular style.

:::
