"""Tests for flow.py — declarative screen state machine."""

from __future__ import annotations

import pytest

from milo._errors import FlowError
from milo._types import Action, Quit, ReducerResult
from milo.flow import Flow, FlowScreen, FlowState


def noop_reducer(state, action):
    if state is None:
        return {"screen": "initialized"}
    return state


def counter_reducer(state, action):
    if state is None:
        return 0
    if action.type == "increment":
        return state + 1
    return state


class TestFlowScreen:
    def test_rshift_creates_flow(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        flow = a >> b
        assert isinstance(flow, Flow)
        assert len(flow.screens) == 2
        assert len(flow.transitions) == 1

    def test_chain_three(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        c = FlowScreen("c", "c.txt", noop_reducer)
        flow = a >> b >> c
        assert len(flow.screens) == 3
        assert len(flow.transitions) == 2


class TestFlow:
    def test_from_screens(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        c = FlowScreen("c", "c.txt", noop_reducer)
        flow = Flow.from_screens(a, b, c)
        assert len(flow.screens) == 3
        assert len(flow.transitions) == 2

    def test_from_screens_requires_two(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        with pytest.raises(FlowError):
            Flow.from_screens(a)

    def test_with_transition(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        flow = (a >> b).with_transition("b", "a", on="@@BACK")
        assert len(flow.transitions) == 2

    def test_with_transition_invalid_screen(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        flow = a >> b
        with pytest.raises(FlowError):
            flow.with_transition("c", "a", on="@@BACK")

    def test_template_map(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        flow = a >> b
        assert flow.template_map == {"a": "a.txt", "b": "b.txt"}


class TestFlowReducer:
    def test_init(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        flow = a >> b
        reducer = flow.build_reducer()
        state = reducer(None, Action("@@INIT"))
        assert isinstance(state, FlowState)
        assert state.current_screen == "a"
        assert "a" in state.screen_states
        assert "b" in state.screen_states

    def test_navigate(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        flow = a >> b
        reducer = flow.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action("@@NAVIGATE", payload="b"))
        assert state.current_screen == "b"

    def test_action_routes_to_current_screen(self):
        a = FlowScreen("a", "a.txt", counter_reducer)
        b = FlowScreen("b", "b.txt", counter_reducer)
        flow = a >> b
        reducer = flow.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action("increment"))
        assert state.screen_states["a"] == 1
        assert state.screen_states["b"] == 0

    def test_screen_state_preserved(self):
        a = FlowScreen("a", "a.txt", counter_reducer)
        b = FlowScreen("b", "b.txt", counter_reducer)
        flow = a >> b
        reducer = flow.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action("increment"))  # a: 1
        state = reducer(state, Action("@@NAVIGATE", payload="b"))
        state = reducer(state, Action("increment"))  # b: 1
        assert state.screen_states["a"] == 1  # Preserved
        assert state.screen_states["b"] == 1

    def test_custom_transition(self):
        a = FlowScreen("a", "a.txt", noop_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        flow = (a >> b).with_transition("b", "a", on="go_back")
        reducer = flow.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action("@@NAVIGATE", payload="b"))
        assert state.current_screen == "b"
        state = reducer(state, Action("go_back"))
        assert state.current_screen == "a"

    def test_propagates_reducer_result_sagas(self):
        """ReducerResult sagas from screen reducers should propagate."""

        def saga_reducer(state, action):
            if state is None:
                return 0
            if action.type == "trigger":
                return ReducerResult(state=1, sagas=(lambda: iter([]),))
            return state

        a = FlowScreen("a", "a.txt", saga_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        flow = a >> b
        reducer = flow.build_reducer()
        state = reducer(None, Action("@@INIT"))
        result = reducer(state, Action("trigger"))
        assert isinstance(result, ReducerResult)
        assert result.sagas

    def test_propagates_quit_from_screen(self):
        """Quit from a screen reducer should propagate through the flow."""

        def quit_reducer(state, action):
            if state is None:
                return 0
            if action.type == "quit":
                return Quit(state=99, code=1)
            return state

        a = FlowScreen("a", "a.txt", quit_reducer)
        b = FlowScreen("b", "b.txt", noop_reducer)
        flow = a >> b
        reducer = flow.build_reducer()
        state = reducer(None, Action("@@INIT"))
        result = reducer(state, Action("quit"))
        assert isinstance(result, Quit)
        assert result.code == 1
        assert isinstance(result.state, FlowState)
        assert result.state.screen_states["a"] == 99
