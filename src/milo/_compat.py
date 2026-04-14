"""Cross-platform compatibility helpers.

Centralizes all platform-specific code so the rest of milo
can remain platform-agnostic.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path

_IS_WINDOWS = sys.platform == "win32"


# ---------------------------------------------------------------------------
# VT / ANSI support
# ---------------------------------------------------------------------------

_vt_enabled = False


def enable_vt_processing() -> None:
    """Enable virtual-terminal processing on Windows.

    Calls ``SetConsoleMode`` with ``ENABLE_VIRTUAL_TERMINAL_PROCESSING``
    so that ANSI escape sequences are interpreted by cmd.exe and
    PowerShell.  No-op on Unix and when stdout is not a real console.
    """
    global _vt_enabled
    if not _IS_WINDOWS or _vt_enabled:
        return
    try:
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        STD_OUTPUT_HANDLE = -11  # noqa: N806
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004  # noqa: N806

        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.wintypes.DWORD()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        _vt_enabled = True
    except Exception:  # noqa: S110
        pass  # Not a real console — ANSI may or may not work


# ---------------------------------------------------------------------------
# Data / config directories
# ---------------------------------------------------------------------------


def data_dir() -> Path:
    """Return the platform-appropriate milo data directory.

    * Windows: ``%LOCALAPPDATA%/milo``  (e.g. ``C:\\Users\\alice\\AppData\\Local\\milo``)
    * Unix:    ``~/.milo``
    """
    if _IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "milo"
    return Path.home() / ".milo"


# ---------------------------------------------------------------------------
# Terminal resize monitoring
# ---------------------------------------------------------------------------


def watch_terminal_resize(callback: Callable[[int, int], None]) -> Callable[[], None]:
    """Register *callback(cols, rows)* to fire on terminal resize.

    On Unix this installs a ``SIGWINCH`` handler.
    On Windows it spawns a daemon thread that polls ``os.get_terminal_size()``.

    Returns a *stop* callable that unregisters the handler / stops the
    polling thread.
    """
    if _IS_WINDOWS:
        return _poll_resize(callback)
    return _sigwinch_resize(callback)


def _sigwinch_resize(callback: Callable[[int, int], None]) -> Callable[[], None]:
    """Unix: use SIGWINCH."""
    import signal

    original = signal.getsignal(signal.SIGWINCH)

    def _handler(_signum: int, _frame: object) -> None:
        try:
            cols, rows = os.get_terminal_size()
            callback(cols, rows)
        except OSError:
            pass

    signal.signal(signal.SIGWINCH, _handler)

    def _stop() -> None:
        signal.signal(signal.SIGWINCH, original)

    return _stop


def _poll_resize(
    callback: Callable[[int, int], None],
    interval: float = 0.5,
) -> Callable[[], None]:
    """Windows: poll terminal size in a daemon thread."""
    stop_event = threading.Event()

    def _loop() -> None:
        try:
            prev = os.get_terminal_size()
        except OSError:
            return
        while not stop_event.is_set():
            stop_event.wait(interval)
            if stop_event.is_set():
                break
            try:
                cur = os.get_terminal_size()
            except OSError:
                continue  # silent: terminal may be detached
            if cur != prev:
                prev = cur
                callback(cur.columns, cur.lines)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()

    return stop_event.set


# ---------------------------------------------------------------------------
# Shell detection
# ---------------------------------------------------------------------------


def default_shell() -> str:
    """Detect the user's shell.

    On Windows, checks for PowerShell first, then falls back to ``cmd``.
    On Unix, reads ``$SHELL`` and maps to bash/zsh/fish.
    """
    if _IS_WINDOWS:
        # PowerShell sets PSModulePath; plain cmd does not
        if os.environ.get("PSMODULEPATH"):
            return "powershell"
        return "cmd"

    shell_path = os.environ.get("SHELL", "")
    if "zsh" in shell_path:
        return "zsh"
    if "fish" in shell_path:
        return "fish"
    return "bash"
