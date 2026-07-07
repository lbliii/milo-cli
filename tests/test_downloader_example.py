"""Purity checks for the downloader example reducer."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from milo import Action, Key, ReducerResult, SpecialKey

_APP_PATH = Path(__file__).resolve().parents[1] / "examples" / "downloader" / "app.py"
_SPEC = importlib.util.spec_from_file_location("milo_downloader_example", _APP_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_APP = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _APP
_SPEC.loader.exec_module(_APP)

TICK_SECONDS = _APP.TICK_SECONDS
State = _APP.State
reducer = _APP.reducer


def test_downloader_elapsed_time_is_derived_from_tick_actions() -> None:
    started = reducer(
        State(),
        Action("@@KEY", payload=Key(name=SpecialKey.ENTER)),
    )
    assert isinstance(started, ReducerResult)
    assert started.state.elapsed == 0.0

    first_tick = reducer(started.state, Action("@@TICK"))
    assert isinstance(first_tick, State)
    assert first_tick.elapsed == TICK_SECONDS

    second_tick = reducer(first_tick, Action("@@TICK"))
    assert isinstance(second_tick, State)
    assert second_tick.elapsed == TICK_SECONDS * 2


def test_downloader_completion_preserves_action_derived_elapsed_time() -> None:
    state = State(phase="fetching", elapsed=1.5)
    completed = reducer(state, Action("ALL_DONE"))

    assert isinstance(completed, State)
    assert completed.phase == "done"
    assert completed.elapsed == 1.5
