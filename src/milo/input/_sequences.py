"""Frozen escape sequence lookup table."""

from __future__ import annotations

from milo._types import Key, SpecialKey

# Map escape sequences to Key objects
ESCAPE_SEQUENCES: dict[str, Key] = {
    # Arrow keys
    "\x1b[A": Key(name=SpecialKey.UP),
    "\x1b[B": Key(name=SpecialKey.DOWN),
    "\x1b[C": Key(name=SpecialKey.RIGHT),
    "\x1b[D": Key(name=SpecialKey.LEFT),
    # Home / End
    "\x1b[H": Key(name=SpecialKey.HOME),
    "\x1b[F": Key(name=SpecialKey.END),
    "\x1b[1~": Key(name=SpecialKey.HOME),
    "\x1b[4~": Key(name=SpecialKey.END),
    # Page Up / Down
    "\x1b[5~": Key(name=SpecialKey.PAGE_UP),
    "\x1b[6~": Key(name=SpecialKey.PAGE_DOWN),
    # Insert / Delete
    "\x1b[2~": Key(name=SpecialKey.INSERT),
    "\x1b[3~": Key(name=SpecialKey.DELETE),
    # Function keys
    "\x1bOP": Key(name=SpecialKey.F1),
    "\x1bOQ": Key(name=SpecialKey.F2),
    "\x1bOR": Key(name=SpecialKey.F3),
    "\x1bOS": Key(name=SpecialKey.F4),
    "\x1b[15~": Key(name=SpecialKey.F5),
    "\x1b[17~": Key(name=SpecialKey.F6),
    "\x1b[18~": Key(name=SpecialKey.F7),
    "\x1b[19~": Key(name=SpecialKey.F8),
    "\x1b[20~": Key(name=SpecialKey.F9),
    "\x1b[21~": Key(name=SpecialKey.F10),
    "\x1b[23~": Key(name=SpecialKey.F11),
    "\x1b[24~": Key(name=SpecialKey.F12),
    # Shift+arrow
    "\x1b[1;2A": Key(name=SpecialKey.UP, shift=True),
    "\x1b[1;2B": Key(name=SpecialKey.DOWN, shift=True),
    "\x1b[1;2C": Key(name=SpecialKey.RIGHT, shift=True),
    "\x1b[1;2D": Key(name=SpecialKey.LEFT, shift=True),
    # Alt+arrow
    "\x1b[1;3A": Key(name=SpecialKey.UP, alt=True),
    "\x1b[1;3B": Key(name=SpecialKey.DOWN, alt=True),
    "\x1b[1;3C": Key(name=SpecialKey.RIGHT, alt=True),
    "\x1b[1;3D": Key(name=SpecialKey.LEFT, alt=True),
    # Ctrl+arrow
    "\x1b[1;5A": Key(name=SpecialKey.UP, ctrl=True),
    "\x1b[1;5B": Key(name=SpecialKey.DOWN, ctrl=True),
    "\x1b[1;5C": Key(name=SpecialKey.RIGHT, ctrl=True),
    "\x1b[1;5D": Key(name=SpecialKey.LEFT, ctrl=True),
    # Tab and Enter
    "\t": Key(name=SpecialKey.TAB),
    "\r": Key(name=SpecialKey.ENTER),
    "\n": Key(name=SpecialKey.ENTER),
    # Backspace variants
    "\x7f": Key(name=SpecialKey.BACKSPACE),
    "\x08": Key(name=SpecialKey.BACKSPACE),
}

# Control character to ctrl+letter mapping (ctrl+a = 0x01, ctrl+z = 0x1a)
CTRL_CHARS: dict[int, str] = {i: chr(i + 96) for i in range(1, 27)}
