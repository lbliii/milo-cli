"""Tests for state.py — Store, saga runner, combine_reducers."""

from __future__ import annotations

import threading
import time

import pytest

from milo._errors import StateError
from milo._types import Action, Call, Fork, Put, ReducerResult, Select
from milo.state import Store, combine_reducers


class TestStore:
    def test_initial_state(self):
        def reducer(state, action):
            if state is None:
                return 0
            return state

        store = Store(reducer, None)
        assert store.state == 0

    def test_dispatch(self):
        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "increment":
                return state + 1
            return state

        store = Store(reducer, None)
        store.dispatch(Action("increment"))
        assert store.state == 1
        store.shutdown()

    def test_subscribe(self):
        calls = []

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "increment":
                return state + 1
            return state

        store = Store(reducer, None)
        unsubscribe = store.subscribe(lambda: calls.append(1))
        store.dispatch(Action("increment"))
        assert len(calls) == 1

        unsubscribe()
        store.dispatch(Action("increment"))
        assert len(calls) == 1
        store.shutdown()

    def test_recording(self):
        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "increment":
                return state + 1
            return state

        store = Store(reducer, None, record=True)
        store.dispatch(Action("increment"))
        assert store.recording is not None
        # @@INIT + increment = 2 records
        assert len(store.recording) == 2
        store.shutdown()

    def test_reducer_error(self):
        def bad_reducer(state, action):
            raise ValueError("boom")

        with pytest.raises(StateError):
            Store(bad_reducer, None)

    def test_middleware(self):
        log = []

        def logging_middleware(dispatch, get_state):
            def mw_dispatch(action):
                log.append(action.type)
                dispatch(action)

            return mw_dispatch

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None, middleware=(logging_middleware,))
        store.dispatch(Action("test"))
        assert "test" in log
        store.shutdown()


class TestSagas:
    def test_call_effect(self):

        def my_fn(x):
            return x * 2

        def my_saga():
            result = yield Call(fn=my_fn, args=(21,))
            yield Put(Action("result", payload=result))

        def reducer(state, action):
            if state is None:
                return {}
            if action.type == "result":
                return {"value": action.payload}
            return state

        store = Store(reducer, None)
        store.run_saga(my_saga())
        # Give saga time to complete
        time.sleep(0.1)
        assert store.state == {"value": 42}
        store.shutdown()

    def test_select_effect(self):
        results = []

        def my_saga():
            state = yield Select()
            results.append(state)

        def reducer(state, action):
            return state or {"counter": 10}

        store = Store(reducer, None)
        store.run_saga(my_saga())
        time.sleep(0.1)
        assert results == [{"counter": 10}]
        store.shutdown()

    def test_select_with_selector(self):
        results = []

        def my_saga():
            counter = yield Select(selector=lambda s: s["counter"])
            results.append(counter)

        def reducer(state, action):
            return state or {"counter": 42}

        store = Store(reducer, None)
        store.run_saga(my_saga())
        time.sleep(0.1)
        assert results == [42]
        store.shutdown()

    def test_put_effect(self):
        def my_saga():
            yield Put(Action("set_value", payload=99))

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "set_value":
                return action.payload
            return state

        store = Store(reducer, None)
        store.run_saga(my_saga())
        time.sleep(0.1)
        assert store.state == 99
        store.shutdown()

    def test_fork_effect(self):
        results = []

        def child_saga():
            results.append("child")
            yield Put(Action("child_done"))

        def parent_saga():
            yield Fork(saga=child_saga())
            results.append("parent")

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent_saga())
        time.sleep(0.2)
        assert "parent" in results
        assert "child" in results
        store.shutdown()

    def test_reducer_result_triggers_saga(self):
        saga_ran = threading.Event()

        def my_saga():
            saga_ran.set()
            yield Put(Action("saga_done"))

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "trigger":
                return ReducerResult(state=1, sagas=(my_saga,))
            return state

        store = Store(reducer, None)
        store.dispatch(Action("trigger"))
        saga_ran.wait(timeout=1.0)
        assert saga_ran.is_set()
        store.shutdown()


class TestCombineReducers:
    def test_basic(self):
        def counter(state, action):
            if state is None:
                return 0
            if action.type == "increment":
                return state + 1
            return state

        def name(state, action):
            if state is None:
                return ""
            if action.type == "set_name":
                return action.payload
            return state

        combined = combine_reducers(counter=counter, name=name)
        state = combined(None, Action("@@INIT"))
        assert state == {"counter": 0, "name": ""}

        state = combined(state, Action("increment"))
        assert state == {"counter": 1, "name": ""}

        state = combined(state, Action("set_name", payload="Alice"))
        assert state == {"counter": 1, "name": "Alice"}

    def test_no_change_returns_same_state(self):
        def noop(state, action):
            return state or 0

        combined = combine_reducers(a=noop)
        state = combined(None, Action("@@INIT"))
        state2 = combined(state, Action("unknown"))
        assert state is state2
