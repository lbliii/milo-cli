---
title: State Management
nav_title: State
description: Redux-style Store with dispatch, listeners, middleware, and saga scheduling.
weight: 10
draft: false
lang: en
tags: [state, store, reducer, middleware]
keywords: [state, store, redux, reducer, dispatch, middleware]
category: usage
icon: database
---

Milo uses a centralized `Store` that holds the entire application state. State changes happen through pure reducer functions, making every transition explicit and testable.

## Store

The `Store` is the single source of truth for your application's state.

```python
from milo import Store, Action

def reducer(state, action):
    if state is None:
        return {"count": 0}
    if action.type == "INCREMENT":
        return {**state, "count": state["count"] + 1}
    return state

store = Store(reducer, initial_state=None)
store.dispatch(Action("INCREMENT"))
print(store.get_state())  # {"count": 1}
```

The store:

- Serializes dispatches through a threading lock
- Notifies listeners after each state change
- Schedules sagas on a `ThreadPoolExecutor` when reducers return `ReducerResult`

:::{note}
The store's dispatch lock ensures actions are processed one at a time, even under free-threading. This gives you sequential consistency without sacrificing saga parallelism.
:::

## Reducers

A reducer is a pure function: `(state, action) -> state`. It receives the current state and an action, and returns the next state. Reducers must not mutate state — always return a new dict or dataclass.

```python
def todo_reducer(state, action):
    if state is None:
        return {"todos": [], "filter": "all"}
    if action.type == "ADD_TODO":
        return {**state, "todos": [*state["todos"], action.payload]}
    if action.type == "SET_FILTER":
        return {**state, "filter": action.payload}
    return state
```

:::{warning}
Never mutate state directly. `state["count"] += 1` breaks the Elm Architecture contract — listeners won't fire correctly, and session replay will produce different results.
:::

## Actions

Actions are frozen dataclasses with a `type` string and an optional `payload`.

```python
from milo import Action

action = Action("ADD_TODO", payload="Buy milk")
action = Action("@@KEY", payload=key)  # Built-in key action
```

Milo dispatches several [[docs/reference/actions|built-in actions]] automatically: `@@INIT`, `@@KEY`, `@@TICK`, `@@RESIZE`, `@@QUIT`, `@@NAVIGATE`, `@@HOT_RELOAD`, and `@@EFFECT_RESULT`.

## Combining reducers

For larger apps, split state into slices with `combine_reducers`:

:::{tab-set}
:::{tab-item} Combined
:badge: Recommended

```python
from milo import combine_reducers

reducer = combine_reducers(counter=counter_reducer, ui=ui_reducer)
# State shape: {"counter": 0, "ui": {"theme": "dark"}}
```

:::{/tab-item}

:::{tab-item} Slice reducers

```python
def counter_reducer(state, action):
    if state is None:
        return 0
    if action.type == "INCREMENT":
        return state + 1
    return state

def ui_reducer(state, action):
    if state is None:
        return {"theme": "dark"}
    return state
```

:::{/tab-item}
:::{/tab-set}

Each sub-reducer manages its own slice of state. `combine_reducers` routes actions to all sub-reducers and assembles the combined state.

## Middleware

Middleware wraps the dispatch function to intercept, transform, or log actions.

```python
def logging_middleware(dispatch, get_state):
    def wrapper(action):
        print(f"[{action.type}] {action.payload}")
        return dispatch(action)
    return wrapper

store = Store(reducer, initial_state=None, middleware=[logging_middleware])
```

Middleware signature: `(dispatch_fn, get_state_fn) -> dispatch_fn`. Middleware composes left-to-right — the first middleware in the list wraps the outermost dispatch.

:::{dropdown} Common middleware patterns
:icon: code

**Timing middleware** — measure reducer performance:

```python
import time

def timing_middleware(dispatch, get_state):
    def wrapper(action):
        start = time.perf_counter()
        result = dispatch(action)
        elapsed = time.perf_counter() - start
        if elapsed > 0.016:  # Slower than 60fps
            print(f"Slow dispatch: {action.type} took {elapsed:.3f}s")
        return result
    return wrapper
```

**Filter middleware** — ignore actions conditionally:

```python
def ignore_ticks(dispatch, get_state):
    def wrapper(action):
        if action.type == "@@TICK" and get_state().get("paused"):
            return  # Swallow tick while paused
        return dispatch(action)
    return wrapper
```

:::

## Listeners

Subscribe to state changes:

```python
def on_change(state):
    print(f"State changed: {state}")

store.subscribe(on_change)
```

:::{tip}
Listeners fire after every dispatch. For expensive operations (API calls, file writes), trigger them from [[docs/usage/sagas|sagas]] instead — sagas run on the thread pool and won't block rendering.
:::
