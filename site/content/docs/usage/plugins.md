---
title: Plugins & Hooks
nav_title: Plugins
description: Hook registry with named extension points, listeners, and Store middleware.
weight: 70
draft: false
lang: en
tags: [plugins, hooks, middleware, extensibility]
keywords: [plugins, hooks, registry, middleware, listeners, extensibility]
category: usage
icon: plug
---

Milo's plugin system uses a `HookRegistry` to define named extension points that plugins can subscribe to. Hooks can fire manually or automatically via Store middleware when matching actions are dispatched.

## HookRegistry

```python
from milo import HookRegistry

hooks = HookRegistry()
```

### Defining hooks

Define named hook points before registering listeners:

```python
hooks.define("before_build", description="Fires before the build starts")
hooks.define("after_phase", action_type="@@PHASE_COMPLETE",
             description="Fires after each build phase")
hooks.define("build_complete", description="Fires when the build finishes")
```

The `action_type` parameter links a hook to a Store action — when that action is dispatched, the hook fires automatically via middleware.

### Registering listeners

Use the `@hooks.on()` decorator or `hooks.register()`:

```python
@hooks.on("before_build")
def my_plugin(config):
    print("Building with", config)

# Or register directly
hooks.register("after_phase", my_other_function)
```

Listeners are called in registration order. Each receives keyword arguments from the invocation.

### Invoking hooks

```python
results = hooks.invoke("before_build", config=my_config)
```

Returns a list of return values from each listener.

## Store middleware

The registry generates a middleware that fires hooks when matching actions are dispatched:

```python
from milo import Store

store = Store(reducer, initial_state=None, middleware=[hooks.as_middleware()])
```

When the Store dispatches an action whose type matches a hook's `action_type`, the middleware invokes that hook with `action=` and `get_state=` keyword arguments before the reducer processes it.

```python
@hooks.on("after_phase")
def log_phase(action, get_state, **kwargs):
    state = get_state()
    print(f"Phase complete: {action.payload}")
```

## Freezing

After all plugins are registered, freeze the registry to prevent further modifications:

```python
hooks.freeze()

# These now raise PluginError:
hooks.define("new_hook")          # Error
hooks.register("before_build", fn) # Error
```

:::{note}
Freezing is optional but recommended for production. It catches accidental late registrations that could cause hard-to-debug ordering issues.
:::

## Introspection

```python
hooks.hook_names()              # ("before_build", "after_phase", "build_complete")
hooks.listeners("before_build") # (my_plugin,)
hooks.frozen                    # True
```

## Error handling

If a listener raises an exception, the `HookRegistry` wraps it in a `PluginError` with the hook name and listener identity:

```
PluginError[PLG_HOOK]: Hook 'before_build' listener 'my_plugin' raised: KeyError('missing')
```

## Example: timing plugin

```python
import time

hooks.define("build_start")
hooks.define("build_end")

_t0 = 0.0

@hooks.on("build_start")
def start_timer(**kw):
    global _t0
    _t0 = time.monotonic()

@hooks.on("build_end")
def report_time(**kw):
    elapsed = time.monotonic() - _t0
    print(f"Build took {elapsed:.2f}s")
```

:::{tip}
Combine with [[docs/usage/pipeline|Pipeline]] — define hooks for pipeline events and let plugins observe build progress without modifying the pipeline itself.
:::
