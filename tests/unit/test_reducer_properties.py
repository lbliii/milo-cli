"""Property proof for pure cursor reducer invariants."""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import given
from hypothesis import strategies as st

from milo import Action, Key, SpecialKey
from milo.reducers import with_cursor


@dataclass(frozen=True, slots=True)
class CursorState:
    items: tuple[int, ...]
    cursor: int


@given(
    size=st.integers(min_value=0, max_value=30),
    moves=st.lists(st.sampled_from((SpecialKey.UP, SpecialKey.DOWN)), max_size=80),
    wrap=st.booleans(),
)
def test_cursor_navigation_preserves_items_and_bounds(
    size: int,
    moves: list[SpecialKey],
    wrap: bool,
) -> None:
    initial_cursor = 0 if size == 0 else size // 2
    initial = CursorState(items=tuple(range(size)), cursor=initial_cursor)

    @with_cursor("items", wrap=wrap)
    def reducer(state: CursorState, _action: Action) -> CursorState:
        return state

    result = initial
    expected = initial_cursor
    for move in moves:
        result = reducer(result, Action("@@KEY", payload=Key(name=move)))
        if size == 0:
            expected = 0
        elif move is SpecialKey.UP:
            expected = (expected - 1) % size if wrap else max(0, expected - 1)
        else:
            expected = (expected + 1) % size if wrap else min(size - 1, expected + 1)

    assert result.cursor == expected
    assert result.items == initial.items
    assert initial.cursor == initial_cursor
    if size:
        assert 0 <= result.cursor < size
    else:
        assert result.cursor == 0
