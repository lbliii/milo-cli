---
title: Input Handling
nav_title: Input
description: Cross-platform key reader with full escape sequence support.
weight: 50
draft: false
lang: en
tags: [input, keyboard, keys, terminal]
keywords: [input, keyboard, keys, escape sequences, terminal, raw mode]
category: usage
icon: keyboard
---

Milo's input system reads raw terminal input and translates escape sequences into structured `Key` objects. It handles arrows, function keys, modifiers, and platform differences.

## KeyReader

`KeyReader` is a context manager that puts the terminal in raw mode and yields `Key` objects:

```python
from milo.input import KeyReader

with KeyReader() as keys:
    for key in keys:
        print(f"Got: {key.name or key.char}")
        if key.ctrl and key.char == "c":
            break
```

## Key objects

Each keypress produces a frozen `Key` dataclass:

```python
Key(
    char="a",       # The character (or empty for special keys)
    name=None,      # SpecialKey enum value for non-character keys
    ctrl=False,     # Ctrl modifier
    alt=False,      # Alt/Option modifier
    shift=False,    # Shift modifier
)
```

## Special keys

The `SpecialKey` enum covers all standard terminal keys:

| Category | Keys |
|----------|------|
| **Arrows** | `UP`, `DOWN`, `LEFT`, `RIGHT` |
| **Navigation** | `HOME`, `END`, `PAGE_UP`, `PAGE_DOWN` |
| **Editing** | `INSERT`, `DELETE`, `BACKSPACE` |
| **Control** | `TAB`, `ENTER`, `ESCAPE` |
| **Function** | `F1` through `F12` |

## Escape sequences

Milo includes a frozen lookup table mapping ANSI VT100/xterm escape sequences to `Key` objects. This covers:

- Plain keys (arrows, F-keys, Home, End, etc.)
- Shift+key variants
- Alt+key variants
- Ctrl+key variants

:::{dropdown} How escape sequence parsing works
:icon: info

When a raw byte stream arrives:

1. If the first byte is `\x1b` (ESC), read ahead for a complete sequence
2. Look up the sequence in the frozen table (`_sequences.py`)
3. If found, produce the matching `Key` with the correct modifiers
4. If not found, produce a `Key` with `name=ESCAPE`

The frozen lookup table is built at import time — no runtime overhead per keypress.

:::

## Platform support

:::{tab-set}
:::{tab-item} Unix / macOS

Uses `termios` + `tty` for raw mode, `select` for non-blocking reads.

```python
from milo.input._platform import raw_mode, read_char, is_tty

if is_tty():
    with raw_mode():
        ch = read_char()
```

:::{/tab-item}

:::{tab-item} Windows

Uses `msvcrt` for raw character reads.

```python
# Automatically selected on Windows — same KeyReader API
with KeyReader() as keys:
    for key in keys:
        ...
```

:::{/tab-item}
:::{/tab-set}

:::{tip}
Use `is_tty()` to check if stdin is an interactive terminal before entering raw mode. This lets your app degrade gracefully when input is piped.
:::
