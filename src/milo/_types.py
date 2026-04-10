"""Frozen dataclasses, enums, and type aliases — no internal imports."""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


class SpecialKey(Enum):
    ENTER = auto()
    TAB = auto()
    BACKSPACE = auto()
    DELETE = auto()
    ESCAPE = auto()
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    HOME = auto()
    END = auto()
    PAGE_UP = auto()
    PAGE_DOWN = auto()
    INSERT = auto()
    F1 = auto()
    F2 = auto()
    F3 = auto()
    F4 = auto()
    F5 = auto()
    F6 = auto()
    F7 = auto()
    F8 = auto()
    F9 = auto()
    F10 = auto()
    F11 = auto()
    F12 = auto()


@dataclass(frozen=True, slots=True)
class Key:
    """Single keypress."""

    char: str = ""
    name: SpecialKey | None = None
    ctrl: bool = False
    alt: bool = False
    shift: bool = False


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Action:
    """Event dispatched to a reducer."""

    type: str
    payload: Any = None


BUILTIN_ACTIONS: frozenset[str] = frozenset(
    {
        "@@INIT",
        "@@KEY",
        "@@TICK",
        "@@RESIZE",
        "@@EFFECT_RESULT",
        "@@QUIT",
        "@@NAVIGATE",
        "@@HOT_RELOAD",
        "@@PIPELINE_START",
        "@@PIPELINE_COMPLETE",
        "@@PHASE_START",
        "@@PHASE_COMPLETE",
        "@@PHASE_FAILED",
        "@@SAGA_ERROR",
        "@@SAGA_CANCELLED",
        "@@CMD_ERROR",
    }
)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class AppStatus(Enum):
    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPED = auto()


class RenderTarget(Enum):
    TERMINAL = auto()
    HTML = auto()


# ---------------------------------------------------------------------------
# Screens / Flows
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Screen:
    """Named screen config: template name + reducer reference."""

    name: str
    template: str
    reducer: Callable  # Reducer protocol


@dataclass(frozen=True, slots=True)
class Transition:
    """Flow edge between screens."""

    from_screen: str
    to_screen: str
    on_action: str


# ---------------------------------------------------------------------------
# Fields / Forms
# ---------------------------------------------------------------------------


class FieldType(Enum):
    TEXT = auto()
    SELECT = auto()
    CONFIRM = auto()
    PASSWORD = auto()


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Declarative field configuration."""

    name: str
    label: str
    field_type: FieldType = FieldType.TEXT
    choices: tuple[str, ...] = ()
    default: Any = None
    validator: Callable | None = None
    placeholder: str = ""


@dataclass(frozen=True, slots=True)
class FieldState:
    """Runtime state for a single field."""

    value: Any = ""
    cursor: int = 0
    error: str = ""
    focused: bool = False
    selected_index: int = 0


@dataclass(frozen=True, slots=True)
class FormState:
    """Full form state."""

    fields: tuple[FieldState, ...] = ()
    specs: tuple[FieldSpec, ...] = ()
    active_index: int = 0
    submitted: bool = False


# ---------------------------------------------------------------------------
# Effects (sagas)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Call:
    """Call a function, resume saga with its return value."""

    fn: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Put:
    """Dispatch an action back to the store."""

    action: Action


@dataclass(frozen=True, slots=True)
class Select:
    """Read current state, resume saga with it."""

    selector: Callable | None = None


@dataclass(frozen=True, slots=True)
class Fork:
    """Run another saga concurrently."""

    saga: Callable | Generator


@dataclass(frozen=True, slots=True)
class Delay:
    """Sleep for N seconds."""

    seconds: float


@dataclass(frozen=True, slots=True)
class Retry:
    """Call a function with retry and backoff on failure.

    Usage in a saga::

        result = yield Retry(fetch_data, args=(url,), max_attempts=3, backoff="exponential")
    """

    fn: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    max_attempts: int = 3
    backoff: str = "exponential"  # "exponential", "linear", "fixed"
    base_delay: float = 1.0
    max_delay: float = 30.0


@dataclass(frozen=True, slots=True)
class Timeout:
    """Wrap a blocking effect with a deadline.

    Usage in a saga::

        result = yield Timeout(Call(fetch_data, args=(url,)), seconds=5)

    Raises ``TimeoutError`` if the effect doesn't complete in time.
    Only wraps blocking effects (``Call`` and ``Retry``).
    """

    effect: Call | Retry
    seconds: float


@dataclass(frozen=True, slots=True)
class TryCall:
    """Call a function, returning (result, None) on success or (None, error) on failure.

    Unlike ``Call``, exceptions do not crash the saga::

        result, error = yield TryCall(fn=might_fail)
        if error:
            yield Put(Action("FETCH_FAILED", payload=str(error)))
        else:
            yield Put(Action("FETCH_OK", payload=result))
    """

    fn: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Commands (lightweight alternative to sagas)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cmd:
    """Lightweight command: a thunk that returns an Action (or None).

    Simpler than sagas for one-shot effects::

        def fetch_cmd():
            data = fetch_json(url)
            return Action("FETCH_DONE", payload=data)

        return ReducerResult(state, cmds=(Cmd(fetch_cmd),))
    """

    fn: Callable  # () -> Action | None


@dataclass(frozen=True, slots=True)
class Batch:
    """Run commands concurrently with no ordering guarantees.

    Usage::

        return ReducerResult(state, cmds=(Batch(cmd_a, cmd_b, cmd_c),))
    """

    cmds: tuple[Cmd | Batch | Sequence, ...]


@dataclass(frozen=True, slots=True)
class Sequence:
    """Run commands serially, in order.

    Each command's result is dispatched before the next starts::

        return ReducerResult(state, cmds=(Sequence(cmd_a, cmd_b),))
    """

    cmds: tuple[Cmd | Batch | Sequence, ...]


@dataclass(frozen=True, slots=True)
class TickCmd:
    """Schedule a single @@TICK after *interval* seconds.

    Return from a reducer to start ticking. Return another TickCmd
    when you receive @@TICK to keep the loop going; omit to stop::

        case "@@TICK":
            if state.loading:
                return ReducerResult(new_state, cmds=(TickCmd(0.15),))
            return new_state
    """

    interval: float


def compact_cmds(*cmds: Cmd | Batch | Sequence | TickCmd | None) -> tuple:
    """Strip None entries and simplify command tuples.

    Returns an empty tuple for no commands, a single-element tuple for one,
    and the full tuple otherwise.  Avoids unnecessary allocations for the
    common zero-or-one-command case.
    """
    live = tuple(c for c in cmds if c is not None)
    return live


# ---------------------------------------------------------------------------
# View state (declarative terminal configuration)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ViewState:
    """Declarative terminal state returned alongside rendered content.

    The renderer diffs previous vs. current ViewState and applies only
    the changes.  Attach to ReducerResult to control terminal features
    from your reducer::

        return ReducerResult(state, view=ViewState(cursor_visible=True))
    """

    alt_screen: bool | None = None
    cursor_visible: bool | None = None
    window_title: str | None = None
    mouse_mode: bool | None = None


# ---------------------------------------------------------------------------
# Reducer result (state + optional sagas + optional cmds)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReducerResult:
    """Reducer can return this to trigger side effects."""

    state: Any
    sagas: tuple[Callable, ...] = ()
    cmds: tuple[Cmd | Batch | Sequence | TickCmd, ...] = ()
    view: ViewState | None = None


@dataclass(frozen=True, slots=True)
class Quit:
    """Signal the app to exit. Return from a reducer to stop the event loop."""

    state: Any
    code: int = 0
    sagas: tuple[Callable, ...] = ()
    cmds: tuple[Cmd | Batch | Sequence | TickCmd, ...] = ()
    view: ViewState | None = None
