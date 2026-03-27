---
title: Dev Server
nav_title: Dev
description: Hot-reload dev server with filesystem polling and @@HOT_RELOAD dispatch.
weight: 70
draft: false
lang: en
tags: [dev, hot-reload, development]
keywords: [dev server, hot reload, development, watch, polling]
category: usage
icon: arrow-clockwise
---

Milo includes a lightweight dev server that watches template files and live-reloads your app when they change. No `watchdog` dependency — just filesystem polling.

## CLI usage

```bash
milo dev myapp:app
milo dev myapp:app --watch ./templates --poll 0.25
```

The `myapp:app` argument follows the `module:attribute` convention. Milo imports the module and looks up the `App` instance.

## Programmatic usage

```python
from milo import App, DevServer

app = App(template="dashboard.kida", reducer=reducer, initial_state=None)
server = DevServer(app, watch_dirs=("./templates",), poll_interval=0.5)
server.run()
```

## How it works

```mermaid
flowchart LR
    FS[Filesystem] -->|poll mtime| DS[DevServer]
    DS -->|"@@HOT_RELOAD"| Store
    Store --> Reducer
    Reducer --> Render[Re-render]
```

:::{steps}
:::{step} Poll
:description: DevServer watches directories for *.kida changes

The server polls watched directories at a configurable interval, comparing file mtimes.

:::{/step}

:::{step} Detect
:description: When a template file changes

When a file's mtime changes, DevServer dispatches `@@HOT_RELOAD` with the changed file path.

:::{/step}

:::{step} Reload
:description: Template environment re-reads the file

Your reducer can handle `@@HOT_RELOAD` to trigger re-rendering or state updates. The template environment re-reads the file on next render.

:::{/step}
:::{/steps}

The polling approach has no native dependencies and works identically across macOS, Linux, and Windows.

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `watch_dirs` | `()` | Directories to watch for template changes |
| `poll_interval` | `0.5` | Seconds between filesystem polls |

:::{tip}
Set `--poll 0.1` for faster feedback during active template iteration. The default `0.5s` is a good balance between responsiveness and CPU usage.
:::
