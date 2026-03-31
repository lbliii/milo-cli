"""Setup wizard — multi-screen flow with forms.

Demonstrates: FlowScreen, Flow (>> operator), make_form_reducer,
quit_on combinator, App.from_dir with flows.

    uv run python examples/wizard/app.py
"""

from __future__ import annotations

from dataclasses import dataclass

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
    quit_on,
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


@quit_on("q", SpecialKey.ESCAPE)
def done_reducer(state: DoneState | None, action: Action) -> DoneState | Quit:
    if state is None:
        return DoneState()
    return state


# -- Flow ---------------------------------------------------------------------

welcome = FlowScreen(name="welcome", template="welcome.kida", reducer=welcome_reducer)
config = FlowScreen(name="config", template="config.kida", reducer=config_reducer)
done = FlowScreen(name="done", template="done.kida", reducer=done_reducer)

flow = welcome >> config >> done


if __name__ == "__main__":
    app = App.from_dir(__file__, flow=flow, exit_template="exit.kida")
    app.run()
