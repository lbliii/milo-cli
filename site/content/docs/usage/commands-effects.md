---
title: Commands
nav_title: Commands
description: Lightweight Cmd thunks, Batch, Sequence, TickCmd, and ViewState for simple side effects.
weight: 25
draft: false
lang: en
tags: [commands, effects, cmd, batch, sequence, tick, view-state]
keywords: [cmd, batch, sequence, tick, viewstate, effects, side-effects]
category: usage
icon: zap
---

Commands are a lightweight alternative to [[docs/usage/sagas|sagas]] for one-shot side effects. A `Cmd` is a plain function that runs on the thread pool and optionally dispatches an action — no generators, no `yield`, no multi-step coordination.

## When to use Commands vs. Sagas

| Use Commands when... | Use Sagas when... |
|---------------------|-------------------|
| One function call, one result | Multi-step workflows |
| No need to read state mid-effect | Need `Select` to read state between steps |
| No retry or backoff logic | Need `Retry` with exponential backoff |
| Fire-and-forget or single dispatch | Need `Fork` for concurrent child tasks |

## Cmd

A `Cmd` wraps a function `() -> Action | None`. The store runs it on the thread pool and dispatches the returned action (if any).

```python
from milo import Cmd, ReducerResult, Action

def fetch_status():
    resp = urllib.request.urlopen("https://example.com")
    return Action("STATUS_OK", payload=resp.status)

def reducer(state, action):
    if action.type == "CHECK":
        return ReducerResult({**state, "checking": True}, cmds=(Cmd(fetch_status),))
    if action.type == "STATUS_OK":
        return {**state, "checking": False, "status": action.payload}
    return state
```

If the function returns `None`, nothing is dispatched. If it raises an exception, a `@@CMD_ERROR` action is dispatched with `{"error": "message", "type": "ExceptionTypeName"}`.

## Batch

Run multiple commands concurrently with no ordering guarantees:

```python
from milo import Batch, Cmd, ReducerResult

def reducer(state, action):
    if action.type == "REFRESH_ALL":
        return ReducerResult(
            state,
            cmds=(Batch((Cmd(fetch_users), Cmd(fetch_posts), Cmd(fetch_stats))),),
        )
    return state
```

All three commands execute on the thread pool in parallel. Each dispatches its result independently.

## Sequence

Run commands serially — each result is dispatched before the next command starts:

```python
from milo import Sequence, Cmd, ReducerResult

def reducer(state, action):
    if action.type == "DEPLOY":
        return ReducerResult(
            state,
            cmds=(Sequence((Cmd(validate), Cmd(build), Cmd(publish))),),
        )
    return state
```

`validate` runs first. Once it finishes and its result is dispatched, `build` starts. Then `publish`.

## Nesting

`Batch` and `Sequence` compose recursively:

```python
# Validate first, then build and test in parallel, then publish
Sequence((
    Cmd(validate),
    Batch((Cmd(build), Cmd(test))),
    Cmd(publish),
))
```

## compact_cmds

Helper to clean up command tuples by stripping `None` entries:

```python
from milo import compact_cmds, Cmd

cmds = compact_cmds(
    Cmd(fetch_users) if needs_users else None,
    Cmd(fetch_posts) if needs_posts else None,
)
# Returns () if both are None, (Cmd(...),) if one, or both
return ReducerResult(state, cmds=cmds)
```

## TickCmd

Schedule a single `@@TICK` action after an interval. Return another `TickCmd` from your `@@TICK` handler to keep the loop going — omit it to stop:

```python
from milo import TickCmd, ReducerResult

def reducer(state, action):
    if action.type == "START_POLLING":
        return ReducerResult(
            {**state, "polling": True},
            cmds=(TickCmd(2.0),),  # First tick in 2 seconds
        )
    if action.type == "@@TICK" and state["polling"]:
        # Do work, then schedule next tick
        return ReducerResult(
            {**state, "poll_count": state["poll_count"] + 1},
            cmds=(TickCmd(2.0),),  # Keep ticking
        )
    if action.type == "STOP_POLLING":
        return {**state, "polling": False}  # No TickCmd = stop
    return state
```

:::{tip}
`TickCmd` gives you per-component, dynamic tick control — different rates for different features, start and stop based on state. The `App(tick_rate=...)` parameter is still available as a simpler always-on alternative.
:::

## ViewState

Declare terminal features from your reducer instead of managing them imperatively. The renderer diffs previous vs. current `ViewState` and applies only the changes:

```python
from milo import ViewState, ReducerResult

def reducer(state, action):
    if action.type == "EDIT_MODE":
        return ReducerResult(
            {**state, "mode": "edit"},
            view=ViewState(cursor_visible=True, window_title="Editing"),
        )
    if action.type == "VIEW_MODE":
        return ReducerResult(
            {**state, "mode": "view"},
            view=ViewState(cursor_visible=False, window_title="Viewing"),
        )
    return state
```

| Field | Type | Description |
|-------|------|-------------|
| `alt_screen` | `bool \| None` | Enter/leave alternate screen buffer |
| `cursor_visible` | `bool \| None` | Show/hide the terminal cursor |
| `window_title` | `str \| None` | Set the terminal window title |
| `mouse_mode` | `bool \| None` | Enable/disable mouse event reporting |

Fields set to `None` (the default) are left unchanged — only explicitly set fields trigger terminal escape sequences.

`ViewState` works on both `ReducerResult` and `Quit`:

```python
# Show cursor before exiting so the terminal is clean
return Quit(state, view=ViewState(cursor_visible=True))
```
