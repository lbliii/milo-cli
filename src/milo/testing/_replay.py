"""Action log replay (time-travel)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from milo._types import Action, ReducerResult
from milo.testing._record import SessionRecording, load_recording, state_hash


def replay(
    recording: SessionRecording | str | Path,
    reducer: Callable,
    *,
    speed: float = 1.0,
    step: bool = False,
    on_state: Callable | None = None,
    assert_hashes: bool = False,
) -> Any:
    """Replay a recorded session through a reducer.

    Returns final state. Optionally asserts state_hash matches
    at each step to detect reducer regressions.
    """
    if isinstance(recording, (str, Path)):
        recording = load_recording(recording)

    state = None
    prev_time = None

    # Init
    result = reducer(state, Action("@@INIT"))
    state = result.state if isinstance(result, ReducerResult) else result

    for record in recording.records:
        # Timing
        if prev_time is not None and speed > 0 and not step:
            delay = (record.timestamp - prev_time) / speed
            if delay > 0:
                time.sleep(delay)

        prev_time = record.timestamp

        # Apply action
        result = reducer(state, record.action)
        state = result.state if isinstance(result, ReducerResult) else result

        # Hash check
        if assert_hashes:
            actual_hash = state_hash(state)
            if actual_hash != record.state_hash:
                raise AssertionError(
                    f"State hash mismatch at action {record.action.type}: "
                    f"expected {record.state_hash}, got {actual_hash}"
                )

        # Callback
        if on_state is not None:
            on_state(state, record.action)

        # Step mode
        if step:
            input("Press Enter to continue...")

    return state
