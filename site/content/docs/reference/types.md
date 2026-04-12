---
title: Types & Protocols
nav_title: Types
description: Frozen dataclasses, enums, and protocol definitions.
weight: 30
draft: false
lang: en
tags: [reference, types, protocols]
keywords: [types, dataclasses, protocols, enums, frozen]
category: reference
icon: brackets-curly
---

Milo's type system uses frozen dataclasses for immutability and protocols for structural typing. All types use `@dataclass(frozen=True, slots=True)` for immutability and memory efficiency.

## Core types

| Type | Description |
|------|-------------|
| `Action(type, payload)` | Frozen dataclass. Dispatched to reducers. |
| `Key(char, name, ctrl, alt, shift)` | Frozen dataclass. Represents a keypress. |
| `ReducerResult(state, sagas, cmds, view)` | Returned by reducers to schedule side effects. |
| `Quit(state, code, sagas, cmds, view)` | Signal the app to exit. Return from a reducer to stop the event loop. |
| `ViewState(alt_screen, cursor_visible, window_title, mouse_mode)` | Declarative terminal state. The renderer diffs previous vs. current and applies only changes. |
| `FieldSpec(name, label, field_type, choices, default, validator, placeholder)` | Declarative form field configuration. |
| `FieldState(value, cursor, error, focused)` | Runtime state of a single form field. |
| `FormState(fields, specs, current, submitted)` | Runtime state of an entire form. |
| `Screen(name, template, reducer)` | A flow screen definition. |
| `Transition(from_screen, to_screen, on)` | A flow transition rule. |
| `FlowState(current_screen, screen_states)` | Runtime state of a multi-screen flow. |

## Saga effect types

| Type | Description |
|------|-------------|
| `Call(fn, args, kwargs)` | Call a function, receive its return value. |
| `Put(action)` | Dispatch an action to the store. |
| `Select(selector)` | Read current state or a slice. |
| `Fork(saga)` | Launch a concurrent child saga. |
| `Delay(seconds)` | Sleep for a duration. |
| `Retry(fn, args, kwargs, max_attempts, backoff, base_delay, max_delay)` | Call with retry and backoff on failure. |
| `Timeout(effect, seconds)` | Wrap a `Call` or `Retry` with a deadline. Raises `TimeoutError`. |
| `TryCall(fn, args, kwargs)` | Call a function, return `(result, None)` or `(None, error)`. |
| `Race(sagas)` | Run multiple sagas concurrently, return the first result. Losers cancelled. |
| `All(sagas)` | Run multiple sagas concurrently, wait for all. Fail-fast on error. |
| `Take(action_type, timeout)` | Pause until a matching action is dispatched. |
| `Debounce(seconds, saga)` | Delay-then-fork with cancel-and-restart on re-yield. |
| `TakeEvery(action_type, saga)` | Fork a handler for every matching action. |
| `TakeLatest(action_type, saga)` | Fork a handler for the latest matching action, cancel previous. |

## Command types

Lightweight alternatives to sagas for one-shot effects. See [[docs/usage/commands-effects|Commands]] for usage.

| Type | Description |
|------|-------------|
| `Cmd(fn)` | A thunk `() -> Action \| None`. Runs on the thread pool, dispatches the returned action. |
| `Batch(cmds)` | Run commands concurrently with no ordering guarantees. |
| `Sequence(cmds)` | Run commands serially, in order. Each result is dispatched before the next starts. |
| `TickCmd(interval)` | Schedule a single `@@TICK` after *interval* seconds. Return another from `@@TICK` to keep ticking. |
| `compact_cmds(*cmds)` | Helper: strips `None` entries from a command tuple. |

## Enums

:::{tab-set}
:::{tab-item} SpecialKey

`UP`, `DOWN`, `LEFT`, `RIGHT`, `HOME`, `END`, `PAGE_UP`, `PAGE_DOWN`, `INSERT`, `DELETE`, `BACKSPACE`, `TAB`, `ENTER`, `ESCAPE`, `F1`–`F12`

:::{/tab-item}

:::{tab-item} FieldType

`TEXT`, `PASSWORD`, `SELECT`, `CONFIRM`

:::{/tab-item}

:::{tab-item} Other

| Enum | Description |
|------|-------------|
| `AppStatus` | Application lifecycle states |
| `RenderTarget` | Render output targets |
| `ErrorCode` | All namespaced error codes |

:::{/tab-item}
:::{/tab-set}

## Protocols

| Protocol | Signature |
|----------|-----------|
| `Reducer` | `(state, Action) -> state \| ReducerResult \| Quit` |
| `Saga` | `Generator[effect, result, None]` |
| `DispatchFn` | `(Action) -> None` |
| `GetStateFn` | `() -> state` |
| `Middleware` | `(DispatchFn, GetStateFn) -> DispatchFn` |
| `FieldValidator` | `(str) -> str \| None` |

:::{note}
Protocols use structural typing — your functions and classes don't need to explicitly inherit from them. If the signature matches, it satisfies the protocol.
:::
