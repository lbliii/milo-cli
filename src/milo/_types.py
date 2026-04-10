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
        "@@PHASE_SKIPPED",
        "@@PHASE_RETRY",
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
    """Run another saga concurrently.

    By default forks are *detached*: the child gets its own cancellation
    scope and is not cancelled when the parent is.  Set ``attached=True``
    to inherit the parent's cancellation scope — cancelling the parent
    will transitively cancel the child.
    """

    saga: Callable | Generator
    attached: bool = False


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


@dataclass(frozen=True, slots=True)
class Race:
    """Run multiple sagas concurrently, return the first result.

    Losers are cancelled via their cancel events as soon as a winner
    completes.  If all racers fail, the first error is thrown into
    the parent saga::

        winner = yield Race(sagas=(fetch_primary(), fetch_fallback()))

    Raises ``StateError`` if *sagas* is empty.
    """

    sagas: tuple


@dataclass(frozen=True, slots=True)
class All:
    """Run multiple sagas concurrently, wait for all to complete.

    Returns a tuple of results in the same order as the input sagas.
    Fail-fast: if any saga raises, remaining sagas are cancelled and
    the error is thrown into the parent::

        a, b = yield All(sagas=(fetch_users(), fetch_roles()))

    An empty tuple returns ``()`` immediately.
    """

    sagas: tuple


@dataclass(frozen=True, slots=True)
class Take:
    """Pause the saga until a matching action is dispatched.

    Waits for *future* actions only — actions dispatched before the
    Take is yielded are not matched.  Returns the full ``Action``
    object so the saga can inspect both type and payload::

        action = yield Take("USER_CONFIRMED")
        name = action.payload["name"]

    An optional *timeout* (in seconds) raises ``TimeoutError`` if the
    action is not dispatched in time.
    """

    action_type: str
    timeout: float | None = None


@dataclass(frozen=True, slots=True)
class Debounce:
    """Delay-then-fork: start a timer, fork *saga* when it expires.

    If the parent saga yields another ``Debounce`` before the timer
    fires, the previous timer is cancelled and restarted.  The parent
    continues immediately (non-blocking)::

        # In a keystroke handler saga:
        while True:
            key = yield Take("@@KEY")
            yield Debounce(seconds=0.3, saga=search_saga)

    The debounced saga runs independently; use ``Take`` if the parent
    needs the result.
    """

    seconds: float
    saga: Callable


@dataclass(frozen=True, slots=True)
class TakeEvery:
    """Fork a new saga for every matching action (auto-restart pattern).

    Blocks the parent saga until cancelled.  For each dispatched action
    whose type matches *action_type*, a new saga is forked with the
    action as argument::

        # Fork a handler for every CLICK action:
        yield TakeEvery("CLICK", handle_click)

        def handle_click(action):
            url = action.payload["url"]
            result = yield Call(fetch, args=(url,))
            yield Put(Action("FETCHED", payload=result))

    The watcher loop runs until the parent saga is cancelled.
    """

    action_type: str
    saga: Callable  # (action: Action) -> Generator


@dataclass(frozen=True, slots=True)
class TakeLatest:
    """Fork a saga for the latest matching action, cancelling the previous.

    Like :class:`TakeEvery` but only the most recent saga runs — when a
    new matching action arrives, the previous fork is cancelled before
    the new one starts::

        # Only the latest search runs:
        yield TakeLatest("SEARCH", run_search)

    Useful for typeahead/autocomplete patterns where earlier results
    are obsolete.
    """

    action_type: str
    saga: Callable  # (action: Action) -> Generator


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
