"""Tests for reducer combinators."""

from __future__ import annotations

from dataclasses import dataclass, replace

from milo._types import Action, Key, Quit, ReducerResult, SpecialKey
from milo.reducers import quit_on, with_confirm, with_cursor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ListState:
    items: tuple[str, ...] = ("a", "b", "c")
    cursor: int = 0
    selected: str = ""


def noop_reducer(state, action):
    if state is None:
        return ListState()
    return state


def key_action(char: str = "", name: SpecialKey | None = None) -> Action:
    return Action("@@KEY", payload=Key(char=char, name=name))


# ---------------------------------------------------------------------------
# quit_on
# ---------------------------------------------------------------------------


class TestQuitOn:
    def test_quit_on_char(self):
        @quit_on("q")
        def reducer(state, action):
            return state

        state = ListState()
        result = reducer(state, key_action("q"))
        assert isinstance(result, Quit)
        assert result.state is state

    def test_quit_on_special_key(self):
        @quit_on(SpecialKey.ESCAPE)
        def reducer(state, action):
            return state

        state = ListState()
        result = reducer(state, key_action(name=SpecialKey.ESCAPE))
        assert isinstance(result, Quit)

    def test_quit_on_multiple_keys(self):
        @quit_on("q", SpecialKey.ESCAPE)
        def reducer(state, action):
            return state

        state = ListState()
        assert isinstance(reducer(state, key_action("q")), Quit)
        assert isinstance(reducer(state, key_action(name=SpecialKey.ESCAPE)), Quit)

    def test_no_quit_on_other_key(self):
        @quit_on("q")
        def reducer(state, action):
            return state

        state = ListState()
        result = reducer(state, key_action("a"))
        assert result is state

    def test_passthrough_non_key_action(self):
        @quit_on("q")
        def reducer(state, action):
            return state

        state = ListState()
        result = reducer(state, Action("@@TICK"))
        assert result is state

    def test_passthrough_init(self):
        @quit_on("q")
        def reducer(state, action):
            if state is None:
                return ListState()
            return state

        result = reducer(None, Action("@@INIT"))
        assert isinstance(result, ListState)

    def test_inner_reducer_still_runs_for_non_quit_keys(self):
        @quit_on("q")
        def reducer(state, action):
            if action.type == "@@KEY" and action.payload.char == "x":
                return replace(state, selected="x")
            return state

        state = ListState()
        result = reducer(state, key_action("x"))
        assert result.selected == "x"

    def test_inner_reducer_runs_before_quit(self):
        """Inner reducer's state modifications are preserved in the Quit."""

        @quit_on("q")
        def reducer(state, action):
            if action.type == "@@KEY" and action.payload.char == "q":
                return replace(state, selected="quitting")
            return state

        state = ListState()
        result = reducer(state, key_action("q"))
        assert isinstance(result, Quit)
        assert result.state.selected == "quitting"

    def test_inner_quit_preserved(self):
        """If inner reducer already returns Quit, quit_on passes it through."""

        @quit_on("q")
        def reducer(state, action):
            return Quit(state, code=42)

        state = ListState()
        result = reducer(state, key_action("q"))
        assert isinstance(result, Quit)
        assert result.code == 42


# ---------------------------------------------------------------------------
# with_cursor
# ---------------------------------------------------------------------------


class TestWithCursor:
    def test_move_down(self):
        @with_cursor("items")
        def reducer(state, action):
            if state is None:
                return ListState()
            return state

        state = ListState(cursor=0)
        result = reducer(state, key_action(name=SpecialKey.DOWN))
        assert result.cursor == 1

    def test_move_up(self):
        @with_cursor("items")
        def reducer(state, action):
            return state

        state = ListState(cursor=2)
        result = reducer(state, key_action(name=SpecialKey.UP))
        assert result.cursor == 1

    def test_clamp_at_top(self):
        @with_cursor("items")
        def reducer(state, action):
            return state

        state = ListState(cursor=0)
        result = reducer(state, key_action(name=SpecialKey.UP))
        assert result.cursor == 0

    def test_clamp_at_bottom(self):
        @with_cursor("items")
        def reducer(state, action):
            return state

        state = ListState(cursor=2)
        result = reducer(state, key_action(name=SpecialKey.DOWN))
        assert result.cursor == 2

    def test_wrap_mode(self):
        @with_cursor("items", wrap=True)
        def reducer(state, action):
            return state

        state = ListState(cursor=0)
        result = reducer(state, key_action(name=SpecialKey.UP))
        assert result.cursor == 2  # wraps to last

        state = ListState(cursor=2)
        result = reducer(state, key_action(name=SpecialKey.DOWN))
        assert result.cursor == 0  # wraps to first

    def test_empty_items(self):
        @with_cursor("items")
        def reducer(state, action):
            return state

        state = ListState(items=())
        result = reducer(state, key_action(name=SpecialKey.DOWN))
        assert result.cursor == 0

    def test_custom_cursor_field(self):
        @dataclass(frozen=True)
        class CustomState:
            entries: tuple[str, ...] = ("a", "b", "c")
            pos: int = 0

        @with_cursor("entries", cursor_field="pos")
        def reducer(state, action):
            return state

        state = CustomState()
        result = reducer(state, key_action(name=SpecialKey.DOWN))
        assert result.pos == 1

    def test_passthrough_non_arrow_keys(self):
        @with_cursor("items")
        def reducer(state, action):
            if action.type == "@@KEY" and action.payload.char == "x":
                return replace(state, selected="x")
            return state

        state = ListState()
        result = reducer(state, key_action("x"))
        assert result.selected == "x"
        assert result.cursor == 0

    def test_passthrough_quit(self):
        @with_cursor("items")
        def reducer(state, action):
            return Quit(state)

        state = ListState()
        result = reducer(state, key_action(name=SpecialKey.DOWN))
        assert isinstance(result, Quit)

    def test_passthrough_reducer_result(self):
        def my_saga():
            yield

        @with_cursor("items")
        def reducer(state, action):
            return ReducerResult(state, sagas=(my_saga,))

        state = ListState()
        result = reducer(state, key_action(name=SpecialKey.DOWN))
        assert isinstance(result, ReducerResult)

    def test_passthrough_non_key_action(self):
        @with_cursor("items")
        def reducer(state, action):
            return state

        state = ListState(cursor=0)
        result = reducer(state, Action("@@TICK"))
        assert result.cursor == 0


# ---------------------------------------------------------------------------
# with_confirm
# ---------------------------------------------------------------------------


class TestWithConfirm:
    def test_confirm_on_enter(self):
        @with_confirm()
        def reducer(state, action):
            return state

        state = ListState(cursor=1)
        result = reducer(state, key_action(name=SpecialKey.ENTER))
        assert isinstance(result, Quit)
        assert result.state.cursor == 1

    def test_confirm_custom_key(self):
        @with_confirm(" ")
        def reducer(state, action):
            return state

        state = ListState()
        result = reducer(state, key_action(" "))
        assert isinstance(result, Quit)

    def test_no_confirm_on_other_key(self):
        @with_confirm()
        def reducer(state, action):
            return state

        state = ListState()
        result = reducer(state, key_action("x"))
        assert result is state

    def test_passthrough_existing_quit(self):
        @with_confirm()
        def reducer(state, action):
            return Quit(state, code=42)

        state = ListState()
        result = reducer(state, key_action(name=SpecialKey.ENTER))
        assert isinstance(result, Quit)
        assert result.code == 42  # inner quit preserved

    def test_unwraps_reducer_result(self):
        def my_saga():
            yield

        @with_confirm()
        def reducer(state, action):
            return ReducerResult(state, sagas=(my_saga,))

        state = ListState()
        result = reducer(state, key_action(name=SpecialKey.ENTER))
        assert isinstance(result, Quit)
        assert result.state is state


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


class TestComposition:
    def test_full_stack(self):
        """All three combinators work together."""

        @with_confirm()
        @with_cursor("items", wrap=True)
        @quit_on("q", SpecialKey.ESCAPE)
        def reducer(state, action):
            if state is None:
                return ListState()
            return state

        state = ListState()

        # Navigate down
        result = reducer(state, key_action(name=SpecialKey.DOWN))
        assert result.cursor == 1

        # Navigate up
        result = reducer(result, key_action(name=SpecialKey.UP))
        assert result.cursor == 0

        # Quit on q
        result = reducer(state, key_action("q"))
        assert isinstance(result, Quit)

        # Quit on escape
        result = reducer(state, key_action(name=SpecialKey.ESCAPE))
        assert isinstance(result, Quit)

        # Confirm on enter
        state_at_1 = ListState(cursor=1)
        result = reducer(state_at_1, key_action(name=SpecialKey.ENTER))
        assert isinstance(result, Quit)
        assert result.state.cursor == 1

        # Init passthrough
        result = reducer(None, Action("@@INIT"))
        assert isinstance(result, ListState)

    def test_inner_reducer_logic_preserved(self):
        """App-specific logic in the inner reducer still works."""

        @with_confirm()
        @with_cursor("items")
        @quit_on(SpecialKey.ESCAPE)
        def reducer(state, action):
            if state is None:
                return ListState()
            if action.type == "@@KEY" and action.payload.char == "d":
                # Delete current item
                items = list(state.items)
                if items:
                    items.pop(state.cursor)
                return replace(
                    state, items=tuple(items), cursor=min(state.cursor, max(0, len(items) - 1))
                )
            return state

        state = ListState(items=("a", "b", "c"), cursor=1)
        result = reducer(state, key_action("d"))
        assert result.items == ("a", "c")
        assert result.cursor == 1
