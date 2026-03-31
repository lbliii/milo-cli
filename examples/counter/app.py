"""Counter — the simplest milo app.

Demonstrates: reducer combinators, App.from_dir, template auto-discovery.

    uv run python examples/counter/app.py
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from milo import Action, App, Key, Quit, SpecialKey, quit_on


@dataclass(frozen=True, slots=True)
class State:
    count: int = 0


@quit_on(SpecialKey.ESCAPE)
def reducer(state: State | None, action: Action) -> State | Quit:
    if state is None:
        return State()
    if action.type != "@@KEY":
        return state

    key: Key = action.payload
    match key.name:
        case SpecialKey.UP:
            return replace(state, count=state.count + 1)
        case SpecialKey.DOWN:
            return replace(state, count=max(0, state.count - 1))
    if key.char == "r":
        return replace(state, count=0)
    return state


if __name__ == "__main__":
    app = App.from_dir(
        __file__,
        template="counter.kida",
        reducer=reducer,
        initial_state=State(),
        exit_template="exit.kida",
    )
    app.run()
