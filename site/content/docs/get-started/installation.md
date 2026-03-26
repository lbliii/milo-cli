---
title: Install Milo
nav_title: Install
description: Install Milo using pip, uv, or from source.
weight: 10
draft: false
lang: en
tags: [onboarding, installation]
keywords: [installation, setup, python, uv, pip]
category: onboarding
---

## Requirements

:::{checklist} Before You Start
:show-progress:
- [x] Python 3.14+ installed (free-threaded build recommended)
- [ ] A terminal with TTY support
- [ ] A text editor for templates
:::{/checklist}

## Install

:::{tab-set}
:::{tab-item} uv
:icon: rocket
:badge: Recommended

```bash
uv pip install milo
```

:::{/tab-item}

:::{tab-item} pip

```bash
pip install milo
```

:::{/tab-item}

:::{tab-item} From Source
:icon: code
:badge: Development

```bash
git clone https://github.com/lbliii/milo.git
cd milo
uv sync --group dev --python 3.14t
```

:::{/tab-item}
:::{/tab-set}

## Verify

```bash
milo --version
```

:::{dropdown} Command not found?
:icon: alert

Ensure Python's bin directory is in your PATH:

```bash
# Check where milo was installed
python -m site --user-base

# Add to PATH if needed (add to your shell profile)
export PATH="$HOME/.local/bin:$PATH"
```

:::

## Free-threaded Python {#free-threading}

Milo is designed for Python 3.14t with the GIL disabled (PEP 703). For maximum concurrency with sagas, run with:

```bash
PYTHON_GIL=0 python your_app.py
```

:::{tip}
The `_Py_mod_gil = 0` marker in Milo's `__init__.py` signals to CPython that the module is safe to use without the GIL. Saga concurrency via `ThreadPoolExecutor` benefits directly from free-threading — no GIL contention on I/O-bound or CPU-bound effect handlers.
:::

## What gets installed

| Package | Role |
|---------|------|
| `milo` | Core framework — App, Store, Flow, Form, KeyReader |
| [[ext:kida:|kida-templates]] | Template engine for terminal rendering |

:::{note}
Milo has exactly **one runtime dependency** — [[ext:kida:|Kida]]. No click, no rich, no curses. The entire input, rendering, and state management stack is built-in.
:::
