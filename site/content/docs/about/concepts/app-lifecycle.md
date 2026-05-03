---
title: App Lifecycle
description: How a Milo terminal app starts, dispatches actions, renders, and exits.
weight: 20
draft: false
lang: en
tags: [about, lifecycle, app]
keywords: [app lifecycle, event loop, reducer, render, cleanup]
category: about
icon: recycle
---

A Milo app starts a store, reads terminal input, dispatches actions, renders a
Kida template, and restores the terminal on exit.

```mermaid
flowchart LR
    Start[Start App] --> Store[Create Store]
    Store --> Input[Read Input]
    Input --> Dispatch[Dispatch Action]
    Dispatch --> Reducer[Reducer]
    Reducer --> Render[Render Template]
    Render --> Input
    Reducer --> Effects[Schedule Sagas or Cmd]
    Effects --> Dispatch
    Dispatch --> Exit[Quit and Cleanup]
```

Reducers decide state. Effects do work. The runtime owns terminal setup and
cleanup.
