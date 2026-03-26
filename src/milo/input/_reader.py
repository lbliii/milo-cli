"""KeyReader — iterator that yields Key objects from terminal input."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from types import TracebackType

from milo._errors import ErrorCode, InputError
from milo._types import Key, SpecialKey
from milo.input._platform import is_tty, raw_mode, read_available, read_char
from milo.input._sequences import CTRL_CHARS, ESCAPE_SEQUENCES


class KeyReader:
    """Iterator that yields Key objects from terminal input.

    Usage::

        with KeyReader() as keys:
            for key in keys:
                if key.name == SpecialKey.ESCAPE:
                    break
                print(key)
    """

    def __init__(self, fd: int | None = None) -> None:
        self._fd = fd if fd is not None else sys.stdin.fileno()
        self._raw_ctx = None
        self._closed = False

    def __enter__(self) -> KeyReader:
        if not is_tty(self._fd):
            raise InputError(
                ErrorCode.INP_RAW_MODE,
                "Cannot read keys: stdin is not a TTY",
            )
        self._raw_ctx = raw_mode(self._fd)
        self._raw_ctx.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._closed = True
        if self._raw_ctx is not None:
            self._raw_ctx.__exit__(exc_type, exc_val, exc_tb)

    def __iter__(self) -> Iterator[Key]:
        return self

    def __next__(self) -> Key:
        if self._closed:
            raise StopIteration
        return self.read_key()

    def read_key(self) -> Key:
        """Read and return the next keypress."""
        try:
            ch = read_char(self._fd)
        except (OSError, ValueError) as e:
            raise InputError(ErrorCode.INP_READ, str(e)) from e

        # Escape sequence
        if ch == "\x1b":
            rest = read_available(self._fd)
            seq = "\x1b" + rest
            if seq in ESCAPE_SEQUENCES:
                return ESCAPE_SEQUENCES[seq]
            if not rest:
                return Key(name=SpecialKey.ESCAPE)
            # Alt+char
            if len(rest) == 1 and rest.isprintable():
                return Key(char=rest, alt=True)
            return Key(name=SpecialKey.ESCAPE)

        # Known single-char sequences (tab, enter, backspace)
        if ch in ESCAPE_SEQUENCES:
            return ESCAPE_SEQUENCES[ch]

        # Ctrl+letter
        code = ord(ch)
        if code in CTRL_CHARS:
            return Key(char=CTRL_CHARS[code], ctrl=True)

        # Regular printable character
        if ch.isprintable():
            return Key(char=ch)

        return Key(char=ch)
