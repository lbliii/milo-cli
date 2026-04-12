---
title: Milo
description: Build CLIs that humans and AI agents both use natively
template: home.html
weight: 100
type: page
draft: false
lang: en
keywords: [cli, terminal, elm-architecture, free-threading, python]
category: home
cascade:
  author: lbliii

blob_background: true

cta_buttons:
  - text: Get Started
    url: /docs/get-started/
    style: primary
  - text: Docs
    url: /docs/
    style: secondary

show_recent_posts: false
---

Milo is a Python framework where every CLI is simultaneously a terminal app, a command-line tool, and an MCP server. Write one function with type annotations — Milo generates the argparse subcommand, the MCP tool schema, and the llms.txt entry automatically. Built on the Elm Architecture with [[ext:kida:|Kida]] templates and generator-based sagas, targeting Python 3.14t free-threading.

```python
from milo import App

def reducer(state, action):
    if state is None:
        return {"count": 0}
    if action.type == "@@KEY" and action.payload.char == " ":
        return {**state, "count": state["count"] + 1}
    return state

app = App(template="counter.kida", reducer=reducer, initial_state=None)
app.run()
```

## The Bengal Ecosystem

A structured reactive stack — every layer written in pure Python for 3.14t free-threading.

| | | | |
|--:|---|---|---|
| **ᓚᘏᗢ** | [Bengal](https://github.com/lbliii/bengal) | Static site generator | [Docs](https://lbliii.github.io/bengal/) |
| **∿∿** | [Purr](https://github.com/lbliii/purr) | Content runtime | — |
| **⌁⌁** | [Chirp](https://github.com/lbliii/chirp) | Web framework | [Docs](https://lbliii.github.io/chirp/) |
| **=^..^=** | [Pounce](https://github.com/lbliii/pounce) | ASGI server | [Docs](https://lbliii.github.io/pounce/) |
| **)彡** | [Kida](https://github.com/lbliii/kida) | Template engine | [Docs](https://lbliii.github.io/kida/) |
| **ฅᨐฅ** | [Patitas](https://github.com/lbliii/patitas) | Markdown parser | [Docs](https://lbliii.github.io/patitas/) |
| **⌾⌾⌾** | [Rosettes](https://github.com/lbliii/rosettes) | Syntax highlighter | [Docs](https://lbliii.github.io/rosettes/) |
| **ᗣᗣ** | **Milo** (PyPI: `milo-cli`) | CLI framework ← You are here | [Docs](https://lbliii.github.io/milo-cli/) |

Python-native. Free-threading ready. No npm required.
