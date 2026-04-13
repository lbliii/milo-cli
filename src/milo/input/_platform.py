"""Platform abstraction for terminal raw mode and character reading."""

from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager


@contextmanager
def raw_mode(fd: int | None = None) -> Generator[None]:
    """Context manager that puts the terminal into raw mode.

    Restores original settings on exit.
    """
    if fd is None:
        fd = sys.stdin.fileno()

    if sys.platform == "win32":
        yield
        return

    import termios
    import tty

    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def read_char(fd: int | None = None) -> str:
    """Read a single character from the terminal.

    Must be called within a raw_mode() context.
    """
    if fd is None:
        fd = sys.stdin.fileno()

    if sys.platform == "win32":
        import msvcrt

        return msvcrt.getwch()

    import os

    return os.read(fd, 1).decode("utf-8", errors="replace")


def read_available(fd: int | None = None, max_bytes: int = 16) -> str:
    """Read all immediately available bytes (non-blocking).

    Used to consume multi-byte escape sequences after the initial escape.
    """
    if fd is None:
        fd = sys.stdin.fileno()

    if sys.platform == "win32":
        import msvcrt

        result = ""
        for _ in range(max_bytes):
            if not msvcrt.kbhit():
                break
            result += msvcrt.getwch()
        return result

    import os
    import select

    result = ""
    for _ in range(max_bytes):
        ready, _, _ = select.select([fd], [], [], 0)
        if not ready:
            break
        result += os.read(fd, 1).decode("utf-8", errors="replace")
    return result


def is_tty(fd: int | None = None) -> bool:
    """Check if fd is connected to a terminal."""
    if fd is None:
        try:
            fd = sys.stdin.fileno()
        except (AttributeError, ValueError, OSError):
            return False
    import os

    return os.isatty(fd)
