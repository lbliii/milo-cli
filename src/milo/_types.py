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

    saga: Generator


@dataclass(frozen=True, slots=True)
class Delay:
    """Sleep for N seconds."""

    seconds: float


# ---------------------------------------------------------------------------
# Reducer result (state + optional sagas)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReducerResult:
    """Reducer can return this to trigger side effects."""

    state: Any
    sagas: tuple[Callable, ...] = ()
