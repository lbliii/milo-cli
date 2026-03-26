"""Input handling — key reading and escape sequence parsing."""

from milo._types import Key, SpecialKey
from milo.input._reader import KeyReader

__all__ = ["Key", "KeyReader", "SpecialKey"]
