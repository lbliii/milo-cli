---
title: Sagas
nav_title: Sagas
description: Generator-based side effects with Call, Put, Select, Fork, Delay, Race, All, Take, and more.
weight: 20
draft: false
lang: en
tags: [sagas, effects, side-effects, concurrency]
keywords: [sagas, effects, call, put, select, fork, delay, race, all, take, debounce, retry, generator]
category: usage
icon: arrows-split
---

Sagas handle side effects in Milo — network requests, timers, file I/O, and anything else that isn't a pure state transformation. They're generator functions that yield effect descriptors, keeping your reducers pure.

## How sagas work

```mermaid
flowchart LR
    R[Reducer] -->|ReducerResult| Runner[Saga Runner]
    Runner -->|ThreadPool| Saga[Saga Generator]
    Saga -->|"yield Call(fn)"| Runner
    Runner -->|result| Saga
    Saga -->|"yield Put(action)"| Store[Store]
```

A saga is a generator that yields effect objects. The saga runner interprets each effect, executes it, and sends the result back into the generator.

```python
from milo import Call, Put, Select, Action

def fetch_data_saga():
    url = yield Select(lambda s: s["api_url"])
    data = yield Call(fetch_json, (url,))
    yield Put(Action("DATA_LOADED", payload=data))
```

Sagas run on a `ThreadPoolExecutor`, leveraging Python 3.14t free-threading for true parallelism.

## Triggering sagas from reducers

Return a `ReducerResult` to schedule sagas after a state transition:

```python
from milo import ReducerResult

def reducer(state, action):
    if action.type == "FETCH_REQUESTED":
        return ReducerResult(
            {**state, "loading": True},
            sagas=(fetch_data_saga,),
        )
    if action.type == "DATA_LOADED":
        return {**state, "loading": False, "data": action.payload}
    return state
```

:::{note}
The store dispatches the state change first, then schedules the sagas. This means your template will render the `loading: True` state before the saga begins executing.
:::

## Effect types

:::{tab-set}
:::{tab-item} Call
:icon: play

Execute a function and receive its return value:

```python
result = yield Call(my_function, (arg1, arg2), {"key": "value"})
```

The saga runner calls `my_function(arg1, arg2, key="value")` on the thread pool and sends the return value back into the generator.

:::{/tab-item}

:::{tab-item} Put

Dispatch an action back to the store:

```python
yield Put(Action("TASK_COMPLETE", payload=result))
```

:::{/tab-item}

:::{tab-item} Select

Read current state (or a slice of it):

```python
full_state = yield Select()
url = yield Select(lambda s: s["config"]["api_url"])
```

:::{/tab-item}

:::{tab-item} Fork

Launch a concurrent child saga on the thread pool:

```python
from milo import Fork

yield Fork(background_polling_saga)
```

Forked sagas run independently. They share the same store and can dispatch actions.

:::{/tab-item}

:::{tab-item} Delay

Sleep for a duration:

```python
from milo import Delay

yield Delay(2.0)  # Wait 2 seconds
```

:::{/tab-item}

:::{tab-item} Retry

Call a function with automatic retry and backoff on failure:

```python
from milo import Retry

result = yield Retry(fetch_data, args=(url,), max_attempts=3, backoff="exponential")
```

If `fetch_data` raises an exception, the saga runner retries up to `max_attempts` times with the chosen backoff strategy.

| Parameter | Default | Description |
|---|---|---|
| `fn` | (required) | The function to call |
| `args` | `()` | Positional arguments |
| `kwargs` | `{}` | Keyword arguments |
| `max_attempts` | `3` | Total attempts before propagating the error |
| `backoff` | `"exponential"` | `"exponential"`, `"linear"`, or `"fixed"` |
| `base_delay` | `1.0` | Initial delay in seconds between retries |
| `max_delay` | `30.0` | Cap on delay between retries |

:::{/tab-item}

:::{tab-item} Timeout
:icon: clock

Wrap a blocking effect with a deadline:

```python
from milo import Timeout, Call

result = yield Timeout(Call(fetch_data, args=(url,)), seconds=5)
```

Raises `TimeoutError` if the effect doesn't complete in time. Only wraps blocking effects (`Call` and `Retry`).

:::{/tab-item}

:::{tab-item} TryCall

Call a function, returning `(result, None)` on success or `(None, error)` on failure — exceptions don't crash the saga:

```python
from milo import TryCall, Put, Action

result, error = yield TryCall(fn=might_fail)
if error:
    yield Put(Action("FETCH_FAILED", payload=str(error)))
else:
    yield Put(Action("FETCH_OK", payload=result))
```

:::{/tab-item}

:::{tab-item} Race
:icon: zap

Run multiple sagas concurrently, return the first result. Losers are cancelled:

```python
from milo import Race

winner = yield Race(sagas=(fetch_primary(), fetch_fallback()))
```

If all racers fail, the first error is thrown into the parent saga.

:::{/tab-item}

:::{tab-item} All

Run multiple sagas concurrently, wait for all to complete:

```python
from milo import All

users, roles = yield All(sagas=(fetch_users(), fetch_roles()))
```

Returns a tuple of results in the same order as the input sagas. Fail-fast: if any saga raises, remaining sagas are cancelled.

:::{/tab-item}

:::{tab-item} Take
:icon: pause

Pause the saga until a matching action is dispatched:

```python
from milo import Take

action = yield Take("USER_CONFIRMED")
name = action.payload["name"]
```

Waits for *future* actions only — actions dispatched before the `Take` is yielded are not matched. An optional `timeout` (in seconds) raises `TimeoutError` if the action doesn't arrive in time:

```python
action = yield Take("USER_CONFIRMED", timeout=10.0)
```

:::{/tab-item}

:::{tab-item} Debounce
:icon: timer

Delay-then-fork: start a timer, fork `saga` when it expires. If another `Debounce` is yielded before the timer fires, the previous timer is cancelled and restarted. The parent continues immediately (non-blocking):

```python
from milo import Debounce, Take

# In a keystroke handler saga:
while True:
    key = yield Take("@@KEY")
    yield Debounce(seconds=0.3, saga=search_saga)
```

:::{/tab-item}
:::{/tab-set}

## Watcher patterns

For recurring event handling, use `TakeEvery` or `TakeLatest` instead of manual `Take` loops.

:::{tab-set}
:::{tab-item} TakeEvery

Fork a handler for every matching action. All handlers run concurrently:

```python
from milo import TakeEvery

yield TakeEvery("CLICK", handle_click)

def handle_click(action):
    url = action.payload["url"]
    result = yield Call(fetch, args=(url,))
    yield Put(Action("FETCHED", payload=result))
```

Blocks the parent saga until cancelled. Use this when every event matters (e.g., logging, side effects per click).

:::{/tab-item}

:::{tab-item} TakeLatest

Like `TakeEvery`, but cancels the previous handler when a new action arrives:

```python
from milo import TakeLatest

yield TakeLatest("SEARCH", run_search)
```

Use this for typeahead/autocomplete patterns where earlier results are obsolete.

:::{/tab-item}
:::{/tab-set}

## Composing sagas

:::{tab-set}
:::{tab-item} Sequential
:badge: yield from

Delegate to other sagas sequentially:

```python
def setup_saga():
    yield from fetch_config_saga()
    yield from fetch_user_saga()
    yield Put(Action("SETUP_COMPLETE"))
```

:::{/tab-item}

:::{tab-item} Concurrent
:badge: Fork

Run sagas in parallel on the thread pool:

```python
def parallel_setup_saga():
    yield Fork(fetch_config_saga)
    yield Fork(fetch_user_saga)
```

Under Python 3.14t free-threading, forked sagas execute with true parallelism.

:::{/tab-item}
:::{/tab-set}

:::{tip}
Keep sagas focused on coordination, not computation. If you need heavy processing, put it in a function and `Call` it — that way the saga remains readable and the function is independently testable.
:::

## Error recovery

If an unhandled exception occurs in a saga, Milo dispatches a `@@SAGA_ERROR` action instead of swallowing the error silently. Your reducer can handle it gracefully:

```python
def reducer(state, action):
    if action.type == "@@SAGA_ERROR":
        return {**state, "error": action.payload["error"]}
    return state
```

The payload contains `{"error": "message", "type": "ExceptionTypeName"}`.

:::{note}
The store continues working after a saga error — other sagas and dispatches are unaffected. This matches Bubbletea's pattern of recovering from panics in command goroutines.
:::

## Sagas vs. Commands

For one-shot effects (fetch a URL, write a file, dispatch the result), consider using [[docs/usage/commands-effects|Commands]] instead. Commands are simpler — a plain function instead of a generator — and handle the dispatch-result pattern automatically.

Use sagas when you need multi-step coordination: reading state mid-effect, retrying with backoff, forking child tasks, or sequencing multiple dependent calls.
