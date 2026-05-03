---
title: Thread Safety
description: How Milo approaches free-threaded Python and shared mutable state.
weight: 25
draft: false
lang: en
tags: [about, concurrency, free-threading]
keywords: [thread safety, free-threading, python 3.14t, reducers, sagas]
category: about
icon: cpu
---

Milo is designed for Python 3.14t with `PYTHON_GIL=0`.

The core rule is simple: reducers do not mutate shared state or perform I/O.
Effects run in sagas, `Cmd` thunks, command handlers, or explicit boundary code.

Important boundaries:

- Reducers are pure functions.
- State should be immutable or treated as immutable.
- Store dispatch serializes action processing.
- Sagas and commands run on an executor and report back through actions.
- Terminal cleanup belongs to the app runtime, not reducers.

See [[docs/about/concepts/app-lifecycle|App Lifecycle]] for the runtime flow.
