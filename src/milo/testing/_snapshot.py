"""Snapshot capture and comparison."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def assert_renders(
    state: Any,
    template: str | Any,
    *,
    snapshot: str | Path | None = None,
    width: int = 80,
    color: bool = False,
    update: bool = False,
    env: Any = None,
) -> str:
    """Render state through template, assert output matches snapshot.

    If snapshot is None, returns rendered string.
    If snapshot is a path and doesn't exist, creates it.
    If update=True, overwrites on mismatch.
    """
    if env is None:
        from milo.templates import get_env

        env = get_env()

    tmpl = env.get_template(template) if isinstance(template, str) else template

    rendered = tmpl.render(state=state)

    if not color:
        rendered = strip_ansi(rendered)

    if snapshot is None:
        return rendered

    snap_path = Path(snapshot)
    should_update = update or os.environ.get("MILO_UPDATE_SNAPSHOTS") == "1"

    if not snap_path.exists() or should_update:
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(rendered)
        return rendered

    expected = snap_path.read_text()
    if rendered != expected:
        raise AssertionError(
            f"Snapshot mismatch: {snap_path}\n"
            f"--- expected ---\n{expected}\n"
            f"--- actual ---\n{rendered}"
        )

    return rendered


def assert_state(
    reducer: Any,
    initial: Any,
    actions: list | tuple,
    expected: Any,
) -> None:
    """Feed actions through reducer, assert final state matches."""
    from milo._types import ReducerResult

    state = initial
    for action in actions:
        result = reducer(state, action)
        state = result.state if isinstance(result, ReducerResult) else result

    assert state == expected, f"State mismatch:\n  expected: {expected}\n  actual: {state}"


def assert_saga(
    saga: Any,
    steps: list[tuple[Any, Any]],
) -> None:
    """Step through saga, assert each yielded effect matches."""
    effect = next(saga)
    for expected_effect, send_value in steps:
        assert effect == expected_effect, (
            f"Effect mismatch:\n  expected: {expected_effect}\n  actual: {effect}"
        )
        try:
            effect = saga.send(send_value)
        except StopIteration:
            return
