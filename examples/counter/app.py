"""Counter — the simplest milo app.

Demonstrates: reducer, @@KEY dispatch, template rendering.

    uv run python examples/counter/app.py
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from milo import Action, App, Key, SpecialKey
from milo.templates import get_env


@dataclass(frozen=True, slots=True)
class State:
    count: int = 0
    quit: bool = False


def reducer(state: State | None, action: Action) -> State:
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
        case SpecialKey.ESCAPE:
            return replace(state, quit=True)
    if key.char == "r":
        return replace(state, count=0)
    return state


if __name__ == "__main__":
    from kida import FileSystemLoader

    templates = Path(__file__).parent / "templates"
    env = get_env(loader=FileSystemLoader(str(templates)))

    app = App(
        template="counter.txt",
        reducer=reducer,
        initial_state=State(),
        env=env,
    )
    final = app.run()
    print(f"Final count: {final.count}")
