"""Tests for Bubbletea-inspired patterns: Cmd, Batch, Sequence, TickCmd,
ViewState, message filter, saga error recovery, and compact_cmds."""

from __future__ import annotations

import threading
from unittest.mock import patch

from milo._types import (
    Action,
    Batch,
    Cmd,
    Quit,
    ReducerResult,
    Sequence,
    TickCmd,
    ViewState,
    compact_cmds,
)
from milo.app import App, _TerminalRenderer
from milo.state import Store, combine_reducers

# ---------------------------------------------------------------------------
# Task 1: Saga error recovery
# ---------------------------------------------------------------------------


class TestSagaErrorRecovery:
    def test_saga_error_dispatches_saga_error_action(self):
        """Unhandled saga exceptions dispatch @@SAGA_ERROR instead of being swallowed."""

        def bad_saga():
            raise ValueError("boom")
            yield  # make it a generator

        def reducer(state, action):
            if state is None:
                return {}
            if action.type == "@@SAGA_ERROR":
                return {"error": action.payload}
            return state

        store = Store(reducer, None)
        store.run_saga(bad_saga())
        store._executor.shutdown(wait=True)

        assert store.state.get("error") is not None
        assert store.state["error"]["type"] == "ValueError"
        assert "boom" in store.state["error"]["error"]

    def test_saga_error_does_not_crash_store(self):
        """Store continues working after a saga error."""

        def bad_saga():
            raise RuntimeError("fail")
            yield

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "increment":
                return state + 1
            return state

        store = Store(reducer, None)
        store.run_saga(bad_saga())
        store._executor.shutdown(wait=True)

        # Store still works
        store.dispatch(Action("increment"))
        assert store.state == 1
        store.shutdown()


# ---------------------------------------------------------------------------
# Task 2: Message filter
# ---------------------------------------------------------------------------


class TestMessageFilter:
    def test_filter_param_stored(self):
        def my_filter(state, action):
            return action

        app = App(
            template="t.kida",
            reducer=lambda s, a: s or 0,
            initial_state=0,
            filter=my_filter,
        )
        assert app._filter is my_filter

    def test_no_filter_by_default(self):
        app = App(
            template="t.kida",
            reducer=lambda s, a: s or 0,
            initial_state=0,
        )
        assert app._filter is None


# ---------------------------------------------------------------------------
# Task 3: Lightweight Cmd effect type
# ---------------------------------------------------------------------------


class TestCmd:
    def test_cmd_executes_and_dispatches(self):
        """Cmd thunk runs on thread pool and dispatches returned Action."""

        def my_cmd():
            return Action("CMD_DONE", payload=42)

        def reducer(state, action):
            if state is None:
                return {}
            if action.type == "trigger":
                return ReducerResult(state, cmds=(Cmd(my_cmd),))
            if action.type == "CMD_DONE":
                return {"result": action.payload}
            return state

        store = Store(reducer, None)
        store.dispatch(Action("trigger"))
        store._executor.shutdown(wait=True)
        assert store.state == {"result": 42}

    def test_cmd_returning_none(self):
        """Cmd returning None dispatches nothing."""
        dispatch_count = []

        def noop_cmd():
            return None

        def reducer(state, action):
            if state is None:
                return 0
            dispatch_count.append(action.type)
            if action.type == "trigger":
                return ReducerResult(state, cmds=(Cmd(noop_cmd),))
            return state

        store = Store(reducer, None)
        store.dispatch(Action("trigger"))
        store._executor.shutdown(wait=True)
        # Only @@INIT and trigger, no extra dispatch from cmd
        assert "CMD_DONE" not in dispatch_count
        store.shutdown()

    def test_cmd_error_dispatches_cmd_error(self):
        """Cmd exceptions dispatch @@CMD_ERROR."""

        def bad_cmd():
            raise ValueError("cmd fail")

        def reducer(state, action):
            if state is None:
                return {}
            if action.type == "trigger":
                return ReducerResult(state, cmds=(Cmd(bad_cmd),))
            if action.type == "@@CMD_ERROR":
                return {"error": action.payload}
            return state

        store = Store(reducer, None)
        store.dispatch(Action("trigger"))
        store._executor.shutdown(wait=True)
        assert store.state.get("error") is not None
        assert "cmd fail" in store.state["error"]["error"]

    def test_cmd_in_quit(self):
        """Cmds in Quit are executed before quit."""

        def cleanup_cmd():
            return Action("CLEANED_UP")

        states = []

        def reducer(state, action):
            if state is None:
                return "init"
            states.append(action.type)
            if action.type == "quit":
                return Quit(state="done", cmds=(Cmd(cleanup_cmd),))
            return state

        store = Store(reducer, None)
        store.dispatch(Action("quit"))
        store._executor.shutdown(wait=True)
        assert "CLEANED_UP" in states


# ---------------------------------------------------------------------------
# Task 4: Batch and Sequence combinators
# ---------------------------------------------------------------------------


class TestBatch:
    def test_batch_runs_concurrently(self):
        """All commands in a Batch execute."""
        results = []
        lock = threading.Lock()

        def cmd_a():
            with lock:
                results.append("a")
            return Action("A_DONE")

        def cmd_b():
            with lock:
                results.append("b")
            return Action("B_DONE")

        def reducer(state, action):
            if state is None:
                return set()
            if action.type == "trigger":
                return ReducerResult(state, cmds=(Batch((Cmd(cmd_a), Cmd(cmd_b))),))
            if action.type in ("A_DONE", "B_DONE"):
                return state | {action.type}
            return state

        store = Store(reducer, None)
        store.dispatch(Action("trigger"))
        store._executor.shutdown(wait=True)
        assert "a" in results
        assert "b" in results
        assert store.state == {"A_DONE", "B_DONE"}


class TestSequence:
    def test_sequence_runs_in_order(self):
        """Commands in a Sequence execute serially."""
        order = []
        lock = threading.Lock()

        def cmd_first():
            with lock:
                order.append(1)
            return Action("FIRST")

        def cmd_second():
            with lock:
                order.append(2)
            return Action("SECOND")

        def reducer(state, action):
            if state is None:
                return []
            if action.type == "trigger":
                return ReducerResult(
                    state,
                    cmds=(Sequence((Cmd(cmd_first), Cmd(cmd_second))),),
                )
            if action.type in ("FIRST", "SECOND"):
                return [*state, action.type]
            return state

        store = Store(reducer, None)
        store.dispatch(Action("trigger"))
        store._executor.shutdown(wait=True)
        assert order == [1, 2]


class TestCompactCmds:
    def test_strips_none(self):
        cmd = Cmd(lambda: None)
        assert compact_cmds(None, cmd, None) == (cmd,)

    def test_empty(self):
        assert compact_cmds(None, None) == ()
        assert compact_cmds() == ()

    def test_single(self):
        cmd = Cmd(lambda: None)
        assert compact_cmds(cmd) == (cmd,)

    def test_multiple(self):
        a = Cmd(lambda: None)
        b = Cmd(lambda: None)
        result = compact_cmds(a, b)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Task 5: Declarative ViewState
# ---------------------------------------------------------------------------


class TestViewState:
    def test_default_values(self):
        v = ViewState()
        assert v.alt_screen is None
        assert v.cursor_visible is None
        assert v.window_title is None
        assert v.mouse_mode is None

    def test_explicit_values(self):
        v = ViewState(alt_screen=True, cursor_visible=False, window_title="My App")
        assert v.alt_screen is True
        assert v.cursor_visible is False
        assert v.window_title == "My App"

    def test_reducer_result_carries_view(self):
        view = ViewState(cursor_visible=True)
        r = ReducerResult(state=0, view=view)
        assert r.view is view

    def test_quit_carries_view(self):
        view = ViewState(alt_screen=False)
        q = Quit(state=0, view=view)
        assert q.view is view

    def test_store_tracks_view_state(self):
        """Store exposes view_state from the latest ReducerResult."""

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "show_cursor":
                return ReducerResult(state, view=ViewState(cursor_visible=True))
            return state

        store = Store(reducer, None)
        assert store.view_state is None
        store.dispatch(Action("show_cursor"))
        assert store.view_state is not None
        assert store.view_state.cursor_visible is True
        store.shutdown()


class TestTerminalRendererViewState:
    def test_apply_view_state_cursor(self):
        renderer = _TerminalRenderer()
        renderer._started = True
        renderer._view_state = ViewState(alt_screen=True, cursor_visible=False)

        with patch("sys.stdout") as mock_stdout:
            renderer.apply_view_state(ViewState(cursor_visible=True))
            written = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
            assert "\033[?25h" in written  # Show cursor

        assert renderer._view_state.cursor_visible is True

    def test_apply_view_state_no_change(self):
        renderer = _TerminalRenderer()
        renderer._started = True
        renderer._view_state = ViewState(alt_screen=True, cursor_visible=False)

        with patch("sys.stdout") as mock_stdout:
            renderer.apply_view_state(ViewState(cursor_visible=False))
            # No writes since state didn't change
            mock_stdout.write.assert_not_called()

    def test_apply_view_state_title(self):
        renderer = _TerminalRenderer()
        renderer._started = True
        renderer._view_state = ViewState(alt_screen=True, cursor_visible=False)

        with patch("sys.stdout") as mock_stdout:
            renderer.apply_view_state(ViewState(window_title="Hello"))
            written = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
            assert "Hello" in written

    def test_apply_view_state_not_started(self):
        renderer = _TerminalRenderer()
        renderer._started = False
        # Should not raise
        renderer.apply_view_state(ViewState(cursor_visible=True))


class TestCombineReducersWithCmds:
    def test_collects_cmds(self):
        """combine_reducers collects cmds from child ReducerResults."""

        def child(state, action):
            if state is None:
                return 0
            if action.type == "trigger":
                return ReducerResult(state=1, cmds=(Cmd(lambda: None),))
            return state

        combined = combine_reducers(child=child)
        result = combined({"child": 0}, Action("trigger"))
        assert isinstance(result, ReducerResult)
        assert len(result.cmds) == 1

    def test_collects_view_state(self):
        """combine_reducers propagates view state."""
        view = ViewState(cursor_visible=True)

        def child(state, action):
            if state is None:
                return 0
            if action.type == "show":
                return ReducerResult(state=1, view=view)
            return state

        combined = combine_reducers(child=child)
        result = combined({"child": 0}, Action("show"))
        assert isinstance(result, ReducerResult)
        assert result.view is view


# ---------------------------------------------------------------------------
# Task 6: Dynamic TickCmd
# ---------------------------------------------------------------------------


class TestTickCmd:
    def test_tick_cmd_schedules_tick(self):
        """TickCmd dispatches @@TICK after the interval."""
        tick_received = threading.Event()

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "start":
                return ReducerResult(state, cmds=(TickCmd(0.05),))
            if action.type == "@@TICK":
                tick_received.set()
                return state + 1
            return state

        store = Store(reducer, None)
        store.dispatch(Action("start"))
        tick_received.wait(timeout=2.0)
        store.shutdown()
        assert tick_received.is_set()
        assert store.state >= 1

    def test_tick_cmd_self_sustaining(self):
        """Returning another TickCmd from @@TICK creates a recurring loop."""
        tick_count = []
        stop = threading.Event()

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "start":
                return ReducerResult(state, cmds=(TickCmd(0.02),))
            if action.type == "@@TICK":
                tick_count.append(1)
                if len(tick_count) >= 3:
                    stop.set()
                    return state + 1
                # Keep ticking
                return ReducerResult(state + 1, cmds=(TickCmd(0.02),))
            return state

        store = Store(reducer, None)
        store.dispatch(Action("start"))
        stop.wait(timeout=2.0)
        store.shutdown()
        assert len(tick_count) >= 3

    def test_tick_cmd_dataclass(self):
        t = TickCmd(interval=0.5)
        assert t.interval == 0.5


# ---------------------------------------------------------------------------
# Task 7: Message filter application
# ---------------------------------------------------------------------------


class TestMessageFilterApplication:
    def test_filter_blocks_action(self):
        """A filter that returns None prevents the action from reaching the reducer."""

        def block_all(state, action):
            return None

        reducer_called = []

        def reducer(state, action):
            if state is None:
                return 0
            reducer_called.append(action.type)
            return state

        app = App(
            template="t.kida",
            reducer=reducer,
            initial_state=0,
            filter=block_all,
        )
        assert app._filter is block_all

    def test_filter_passes_action_through(self):
        """A filter that returns the action allows it through."""

        def passthrough(state, action):
            return action

        app = App(
            template="t.kida",
            reducer=lambda s, a: s or 0,
            initial_state=0,
            filter=passthrough,
        )
        assert app._filter is passthrough

    def test_filter_can_transform_action(self):
        """A filter can replace the action with a different one."""

        def transform(state, action):
            if action.type == "raw":
                return Action("transformed", payload=action.payload)
            return action

        app = App(
            template="t.kida",
            reducer=lambda s, a: s or 0,
            initial_state=0,
            filter=transform,
        )
        result = app._filter(0, Action("raw", payload=42))
        assert result.type == "transformed"
        assert result.payload == 42


# ---------------------------------------------------------------------------
# Task 8: ViewState merging in combine_reducers
# ---------------------------------------------------------------------------


class TestViewStateMerging:
    def test_combine_reducers_merges_view_states(self):
        """combine_reducers merges ViewState fields from multiple reducers."""

        def reducer_a(state, action):
            if state is None:
                return 0
            if action.type == "trigger":
                return ReducerResult(state=1, view=ViewState(cursor_visible=False))
            return state

        def reducer_b(state, action):
            if state is None:
                return 0
            if action.type == "trigger":
                return ReducerResult(state=2, view=ViewState(window_title="hello"))
            return state

        combined = combine_reducers(a=reducer_a, b=reducer_b)
        result = combined({"a": 0, "b": 0}, Action("trigger"))
        assert isinstance(result, ReducerResult)
        assert result.view.cursor_visible is False
        assert result.view.window_title == "hello"

    def test_later_reducer_overrides_same_field(self):
        """When two reducers set the same ViewState field, later one wins."""

        def reducer_a(state, action):
            if state is None:
                return 0
            if action.type == "trigger":
                return ReducerResult(state=1, view=ViewState(cursor_visible=False))
            return state

        def reducer_b(state, action):
            if state is None:
                return 0
            if action.type == "trigger":
                return ReducerResult(state=2, view=ViewState(cursor_visible=True))
            return state

        combined = combine_reducers(a=reducer_a, b=reducer_b)
        result = combined({"a": 0, "b": 0}, Action("trigger"))
        assert isinstance(result, ReducerResult)
        assert result.view.cursor_visible is True


# ---------------------------------------------------------------------------
# Task 9: Nested Batch and error isolation
# ---------------------------------------------------------------------------


class TestNestedBatch:
    def test_nested_batch_in_batch(self):
        """Nested Batch structures flatten correctly."""
        results = []
        lock = threading.Lock()

        def cmd_a():
            with lock:
                results.append("a")
            return None

        def cmd_b():
            with lock:
                results.append("b")
            return None

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "trigger":
                inner = Batch((Cmd(cmd_a), Cmd(cmd_b)))
                return ReducerResult(state, cmds=(Batch((inner,)),))
            return state

        store = Store(reducer, None)
        store.dispatch(Action("trigger"))
        store._executor.shutdown(wait=True)
        assert sorted(results) == ["a", "b"]


class TestBatchErrorIsolation:
    def test_batch_error_does_not_block_others(self):
        """One failing Cmd in a Batch doesn't prevent others from running."""
        results = []
        lock = threading.Lock()

        def good_cmd():
            with lock:
                results.append("good")
            return None

        def bad_cmd():
            raise ValueError("fail")

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "trigger":
                return ReducerResult(state, cmds=(Batch((Cmd(bad_cmd), Cmd(good_cmd))),))
            return state

        store = Store(reducer, None)
        store.dispatch(Action("trigger"))
        store._executor.shutdown(wait=True)
        assert "good" in results
