"""Stopwatch with laps — tick handling, growing state, formatted output.

Demonstrates: tick_rate, @@TICK dispatch, frozen tuples, computed template values.

    uv run python examples/stopwatch/app.py
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from milo import Action, App, Key, Quit, SpecialKey
from milo.templates import get_env


@dataclass(frozen=True, slots=True)
class State:
    running: bool = False
    elapsed: float = 0.0
    laps: tuple[float, ...] = ()
    lap_start: float = 0.0


TICK_INTERVAL: float = 0.05  # 50 ms per tick


def reducer(state: State | None, action: Action) -> State | Quit:
    if state is None:
        return State()

    if action.type == "@@TICK":
        if state.running:
            return replace(state, elapsed=state.elapsed + TICK_INTERVAL)
        return state

    if action.type != "@@KEY":
        return state

    key: Key = action.payload

    # Quit: Escape or q
    if key.name == SpecialKey.ESCAPE or key.char == "q":
        return Quit(state)

    # Toggle start/stop: Space
    if key.char == " ":
        return replace(state, running=not state.running)

    # Record lap: l (only while running and time has passed since last lap)
    if key.char == "l" and state.running:
        split = state.elapsed - state.lap_start
        if split > 0:
            return replace(
                state,
                laps=(*state.laps, split),
                lap_start=state.elapsed,
            )
        return state

    # Reset: r
    if key.char == "r":
        return State()

    return state


if __name__ == "__main__":
    from kida import FileSystemLoader

    templates = Path(__file__).parent / "templates"
    env = get_env(loader=FileSystemLoader(str(templates)))

    app = App(
        template="stopwatch.txt",
        reducer=reducer,
        initial_state=State(),
        env=env,
        tick_rate=TICK_INTERVAL,
        exit_template="exit.txt",
    )
    app.run()
