---
title: Live Rendering
nav_title: Live
description: In-place terminal updates via milo.live for scripts and one-shot commands.
weight: 61
draft: false
lang: en
tags: [live, rendering, spinner, streaming, kida]
keywords: [live, spinner, liverenderer, stream_to_terminal, milo.live]
category: usage
icon: activity
---

`milo.live` re-exports Kida's terminal live-rendering primitives for use
outside a full [`App`](state.md) event loop. Reach for it when you have a
straight-line script, a one-shot CLI command, or a background subroutine
that wants in-place updates without a reducer.

```python
from milo.live import LiveRenderer, Spinner, stream_to_terminal, terminal_env
```

## When to use which

| Situation                                             | Use                          |
| ----------------------------------------------------- | ---------------------------- |
| Keyboard input, persistent state, multi-screen flow   | `App` + `TickCmd`            |
| One-shot progress for a script or command             | `LiveRenderer` (context mgr) |
| Emit a template in chunks as it renders               | `stream_to_terminal`         |
| Just a spinner frame tuple                            | `Spinner.BRAILLE` / `.DOTS`  |

The App harness owns the render loop, message filter, view state, and cursor
lifecycle. `milo.live` hands you raw primitives — simpler, but you write the
loop.

## `LiveRenderer`

Context manager that overwrites its previous output on each `update()`.
Falls back to log-style appends when stdout is not a TTY.

```python
from milo.live import LiveRenderer, terminal_env

env = terminal_env()
tpl = env.from_string("{{ spinner() }} {{ label }}", name="live")

with LiveRenderer(tpl, refresh_rate=0.08) as live:
    live.start_auto(label="Working")
    do_slow_thing()
    live.update(label="Finalizing")
    finalize()
```

`LiveRenderer` auto-injects a `spinner` context variable — call it in the
template (`{{ spinner() }}`) to emit and advance a frame on each render.

`start_auto()` / `stop_auto()` run a background refresh thread so animations
keep ticking between explicit `update()` calls.

See `examples/liverender/app.py` for a runnable version.

## `Spinner`

Animated spinner with four built-in frame sets:

- `Spinner.BRAILLE` — ten-frame Braille dots (also aliased `DOTS`)
- `Spinner.LINE` — four-frame ASCII (`- \ | /`)
- `Spinner.ARROW` — eight-frame directional arrow

Use the class attributes when you just need the frame tuple (for example,
feeding `TickCmd` animation inside an `App`):

```python
# examples/spinner/app.py
from milo.live import Spinner

SPINNER = Spinner.BRAILLE  # ('⠋', '⠙', '⠹', ...)
```

Instantiate `Spinner(frames)` only when you want a stateful, advancing
spinner outside a `LiveRenderer` (which already provides one).

## `stream_to_terminal`

Render a template in chunks separated by `{% flush %}` boundaries, with a
configurable delay between chunks:

```python
from milo.live import stream_to_terminal, terminal_env

env = terminal_env()
tpl = env.from_string(
    "Starting...\n{% flush %}Step 1 done.\n{% flush %}Step 2 done.\n",
    name="stream",
)
stream_to_terminal(tpl, delay=0.3)
```

Milo's built-in pipeline defs already place `{% flush %}` boundaries between
phases, so passing a pipeline template here will stream one phase at a time.

## `terminal_env`

Returns a pre-configured Kida `Environment` with terminal autoescape — the
same autoescape milo uses internally. Prefer this over `milo.templates.get_env`
for one-off live rendering that doesn't need milo's component loader chain.
