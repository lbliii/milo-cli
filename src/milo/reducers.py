"""Composable reducer combinators for common interaction patterns.

Decorators that wrap reducers to handle boilerplate key handling —
quit on escape, cursor navigation, enter to confirm — so the inner
reducer only contains app-specific logic.

Usage::

    @quit_on("q", SpecialKey.ESCAPE)
    @with_cursor("items", wrap=True)
    @with_confirm()
    def reducer(state, action):
        # only app-specific logic here
        ...
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from milo._types import Action, Key, Quit, ReducerResult, SpecialKey


def _match_key(key: Key, target: str | SpecialKey) -> bool:
    """Check if a Key matches a target (char string or SpecialKey)."""
    if isinstance(target, SpecialKey):
        return key.name == target
    return key.char == target


def _unwrap_state(result: Any) -> Any:
    """Extract plain state from a ReducerResult if needed."""
    if isinstance(result, ReducerResult):
        return result.state
    return result


def quit_on(*keys: str | SpecialKey) -> Callable:
    """Decorator: return Quit(state) when any of the specified keys are pressed.

    Keys can be character strings (``"q"``) or SpecialKey enums
    (``SpecialKey.ESCAPE``).  The inner reducer runs first so it can
    perform app-specific quit logic (e.g. setting flags); if it already
    returned ``Quit``, the wrapper passes it through unchanged.

    Usage::

        @quit_on("q", SpecialKey.ESCAPE)
        def reducer(state, action):
            ...
    """

    def decorator(reducer: Callable) -> Callable:
        def wrapped(state: Any, action: Action) -> Any:
            result = reducer(state, action)
            if isinstance(result, Quit) or result is None:
                return result
            if action.type == "@@KEY":
                key: Key = action.payload
                if any(_match_key(key, k) for k in keys):
                    return Quit(_unwrap_state(result))
            return result

        return wrapped

    return decorator


def with_cursor(
    items_field: str,
    cursor_field: str = "cursor",
    *,
    wrap: bool = False,
) -> Callable:
    """Decorator: add up/down arrow cursor navigation over a list field.

    Expects *state* to be a frozen dataclass with an attribute named
    *items_field* (the sequence) and *cursor_field* (an ``int``).
    Handles ``SpecialKey.UP`` and ``SpecialKey.DOWN``, clamping or
    wrapping as configured.

    The inner reducer runs first.  If it returns ``Quit`` or
    ``ReducerResult``, the wrapper does not interfere.

    Usage::

        @with_cursor("entries", wrap=True)
        def reducer(state, action):
            ...
    """

    def decorator(reducer: Callable) -> Callable:
        def wrapped(state: Any, action: Action) -> Any:
            result = reducer(state, action)
            if isinstance(result, (Quit, ReducerResult)) or result is None:
                return result
            if action.type != "@@KEY":
                return result
            key: Key = action.payload
            items = getattr(result, items_field, ())
            count = len(items)
            if count == 0:
                return result
            cursor = getattr(result, cursor_field, 0)
            if key.name == SpecialKey.UP:
                cursor = (cursor - 1) % count if wrap else max(0, cursor - 1)
                return replace(result, **{cursor_field: cursor})
            if key.name == SpecialKey.DOWN:
                cursor = (cursor + 1) % count if wrap else min(count - 1, cursor + 1)
                return replace(result, **{cursor_field: cursor})
            return result

        return wrapped

    return decorator


def with_confirm(key: str | SpecialKey = SpecialKey.ENTER) -> Callable:
    """Decorator: return Quit(state) when the confirm key is pressed.

    Useful for selection-style apps where pressing Enter chooses the
    current item.  The inner reducer runs first; if it already returned
    ``Quit``, the wrapper does nothing.

    Usage::

        @with_confirm()
        @with_cursor("items")
        @quit_on("q", SpecialKey.ESCAPE)
        def reducer(state, action):
            ...
    """

    def decorator(reducer: Callable) -> Callable:
        def wrapped(state: Any, action: Action) -> Any:
            result = reducer(state, action)
            if isinstance(result, Quit) or result is None:
                return result
            if action.type == "@@KEY" and _match_key(action.payload, key):
                return Quit(_unwrap_state(result))
            return result

        return wrapped

    return decorator
