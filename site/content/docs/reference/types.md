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
| `ReducerResult(state, sagas)` | Returned by reducers to schedule side effects. |
| `FieldSpec(name, label, field_type, choices, default, validator, placeholder)` | Declarative form field configuration. |
| `FieldState(value, cursor, error, focused)` | Runtime state of a single form field. |
| `FormState(fields, specs, current, submitted)` | Runtime state of an entire form. |
| `Screen(name, template, reducer)` | A flow screen definition. |
| `Transition(from_screen, to_screen, on)` | A flow transition rule. |
| `FlowState(current_screen, screen_states)` | Runtime state of a multi-screen flow. |

## Effect types

| Type | Description |
|------|-------------|
| `Call(fn, args, kwargs)` | Call a function, receive its return value. |
| `Put(action)` | Dispatch an action to the store. |
| `Select(selector)` | Read current state or a slice. |
| `Fork(saga)` | Launch a concurrent child saga. |
| `Delay(seconds)` | Sleep for a duration. |

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
| `Reducer` | `(state, Action) -> state \| ReducerResult` |
| `Saga` | `Generator[effect, result, None]` |
| `DispatchFn` | `(Action) -> None` |
| `GetStateFn` | `() -> state` |
| `Middleware` | `(DispatchFn, GetStateFn) -> DispatchFn` |
| `FieldValidator` | `(str) -> str \| None` |

:::{note}
Protocols use structural typing — your functions and classes don't need to explicitly inherit from them. If the signature matches, it satisfies the protocol.
:::
