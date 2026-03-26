"""Setup wizard — multi-screen flow with forms.

Demonstrates: FlowScreen, Flow (>> operator), make_form_reducer, Quit.

    uv run python examples/wizard/app.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from milo import (
    Action,
    App,
    FieldSpec,
    FieldType,
    FlowScreen,
    Key,
    Put,
    Quit,
    ReducerResult,
    SpecialKey,
    make_form_reducer,
)

# -- Screen 1: Welcome -------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WelcomeState:
    pass


def _navigate_saga():
    yield Put(Action("@@NAVIGATE"))


def welcome_reducer(state: WelcomeState | None, action: Action) -> WelcomeState | ReducerResult:
    if state is None:
        return WelcomeState()
    if action.type == "@@KEY":
        key: Key = action.payload
        if key.name == SpecialKey.ENTER:
            return ReducerResult(state=state, sagas=(_navigate_saga,))
    return state


# -- Screen 2: Config (form) -------------------------------------------------

config_reducer = make_form_reducer(
    FieldSpec(name="name", label="Project name", placeholder="my-app"),
    FieldSpec(
        name="language",
        label="Language",
        field_type=FieldType.SELECT,
        choices=("Python", "TypeScript", "Go", "Rust"),
    ),
    FieldSpec(
        name="git_init",
        label="Initialize git?",
        field_type=FieldType.CONFIRM,
        default=True,
    ),
    navigate_on_submit=True,
)


# -- Screen 3: Done ----------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DoneState:
    pass


def done_reducer(state: DoneState | None, action: Action) -> DoneState | Quit:
    if state is None:
        return DoneState()
    if action.type == "@@KEY":
        key: Key = action.payload
        if key.char == "q" or key.name == SpecialKey.ESCAPE:
            return Quit(state)
    return state


# -- Flow ---------------------------------------------------------------------

welcome = FlowScreen(name="welcome", template="welcome.txt", reducer=welcome_reducer)
config = FlowScreen(name="config", template="config.txt", reducer=config_reducer)
done = FlowScreen(name="done", template="done.txt", reducer=done_reducer)

flow = welcome >> config >> done


if __name__ == "__main__":
    from kida import FileSystemLoader

    from milo.templates import get_env

    templates = Path(__file__).parent / "templates"
    env = get_env(loader=FileSystemLoader(str(templates)))

    app = App.from_flow(flow, env=env, exit_template="exit.txt")
    app.run()
