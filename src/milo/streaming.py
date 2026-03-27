"""Streaming support for long-running CLI commands."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Progress:
    """Progress notification from a streaming command."""

    status: str
    step: int = 0
    total: int = 0


def consume_generator(gen: Any) -> tuple[list[Progress], Any]:
    """Consume a generator, collecting Progress yields and capturing the final value.

    Returns ``(progress_list, final_value)``.
    If the generator has no ``StopIteration.value``, final_value is ``None``.
    """
    progress: list[Progress] = []
    final_value = None

    try:
        while True:
            value = next(gen)
            if isinstance(value, Progress):
                progress.append(value)
    except StopIteration as e:
        final_value = e.value

    return progress, final_value


def is_generator_result(result: Any) -> bool:
    """Check if a call result is a generator that should be consumed for streaming."""
    return inspect.isgenerator(result)
