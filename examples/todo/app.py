"""Todo list — an advanced milo app.

Demonstrates: modal input (normal vs add mode), tuple-based collections,
derived filtering, quit_on combinator, App.from_dir.

    uv run python examples/todo/app.py
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, auto

from milo import Action, App, Key, Quit, SpecialKey

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class Mode(Enum):
    NORMAL = auto()
    ADDING = auto()


class Filter(Enum):
    ALL = auto()
    ACTIVE = auto()
    COMPLETED = auto()


@dataclass(frozen=True, slots=True)
class Todo:
    text: str
    done: bool = False


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class State:
    todos: tuple[Todo, ...] = ()
    cursor: int = 0
    mode: Mode = Mode.NORMAL
    filter: Filter = Filter.ALL
    input_text: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filtered_indices(state: State) -> tuple[int, ...]:
    """Return indices into state.todos that match the active filter."""
    match state.filter:
        case Filter.ALL:
            return tuple(range(len(state.todos)))
        case Filter.ACTIVE:
            return tuple(i for i, t in enumerate(state.todos) if not t.done)
        case Filter.COMPLETED:
            return tuple(i for i, t in enumerate(state.todos) if t.done)


def _clamp_cursor(state: State) -> State:
    """Ensure cursor stays within the filtered view bounds."""
    visible = _filtered_indices(state)
    if not visible:
        return replace(state, cursor=0)
    return replace(state, cursor=max(0, min(state.cursor, len(visible) - 1)))


# ---------------------------------------------------------------------------
# Reducer
#
# Note: This reducer uses quit_on for the normal-mode quit keys, but
# handles cursor navigation manually because the filtered view means
# the list length changes dynamically.  with_cursor works best when
# the items field directly drives the cursor bounds.
# ---------------------------------------------------------------------------


def reducer(state: State | None, action: Action) -> State | Quit:
    if state is None:
        return State()

    if action.type != "@@KEY":
        return state

    key: Key = action.payload

    # ---- Adding mode ----
    if state.mode == Mode.ADDING:
        if key.name == SpecialKey.ESCAPE:
            # Cancel add
            return replace(state, mode=Mode.NORMAL, input_text="")

        if key.name == SpecialKey.ENTER:
            # Confirm add
            text = state.input_text.strip()
            if not text:
                return replace(state, mode=Mode.NORMAL, input_text="")
            new_todos = (*state.todos, Todo(text=text))
            new_state = replace(
                state,
                todos=new_todos,
                mode=Mode.NORMAL,
                input_text="",
            )
            # Move cursor to the new item in the filtered view
            visible = _filtered_indices(new_state)
            return replace(new_state, cursor=max(0, len(visible) - 1))

        if key.name == SpecialKey.BACKSPACE:
            return replace(state, input_text=state.input_text[:-1])

        if key.char and key.char.isprintable() and not key.ctrl:
            return replace(state, input_text=state.input_text + key.char)

        return state

    # ---- Normal mode ----

    # Quit
    if key.name == SpecialKey.ESCAPE or key.char == "q":
        return Quit(state)

    # Navigation
    if key.name == SpecialKey.UP:
        return replace(state, cursor=max(0, state.cursor - 1))

    if key.name == SpecialKey.DOWN:
        visible = _filtered_indices(state)
        limit = max(0, len(visible) - 1)
        return replace(state, cursor=min(limit, state.cursor + 1))

    # Add mode
    if key.char == "a":
        return replace(state, mode=Mode.ADDING, input_text="")

    # Toggle complete
    if key.char == " ":
        visible = _filtered_indices(state)
        if not visible:
            return state
        idx = visible[state.cursor]
        todo = state.todos[idx]
        toggled = replace(todo, done=not todo.done)
        new_todos = (*state.todos[:idx], toggled, *state.todos[idx + 1:])
        new_state = replace(state, todos=new_todos)
        return _clamp_cursor(new_state)

    # Delete
    if key.char == "d" or key.name == SpecialKey.DELETE:
        visible = _filtered_indices(state)
        if not visible:
            return state
        idx = visible[state.cursor]
        new_todos = state.todos[:idx] + state.todos[idx + 1 :]
        new_state = replace(state, todos=new_todos)
        return _clamp_cursor(new_state)

    # Filter switching
    if key.char == "1":
        return _clamp_cursor(replace(state, filter=Filter.ALL))
    if key.char == "2":
        return _clamp_cursor(replace(state, filter=Filter.ACTIVE))
    if key.char == "3":
        return _clamp_cursor(replace(state, filter=Filter.COMPLETED))

    return state


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App.from_dir(
        __file__,
        template="todo.kida",
        reducer=reducer,
        initial_state=State(
            todos=(
                Todo(text="Read the milo docs"),
                Todo(text="Build a todo app", done=True),
                Todo(text="Push to main"),
            ),
        ),
        exit_template="exit.kida",
    )

    # Expose filtering helper to templates
    app._env.globals["filtered_todos"] = lambda state: [
        state.todos[i] for i in _filtered_indices(state)
    ]

    app.run()
