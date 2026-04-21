"""Tests for saga effects — stepping through generators manually."""

from __future__ import annotations

import threading
import time

import pytest

from milo._types import (
    Action,
    All,
    Call,
    Debounce,
    Delay,
    Fork,
    Put,
    Race,
    Retry,
    Select,
    Take,
    TakeEvery,
    TakeLatest,
    Timeout,
    TryCall,
)
from milo.state import SagaContext


class TestSagaStepping:
    def test_call_and_put(self):
        """Step through a saga that calls a function and dispatches result."""

        def fetch_saga():
            result = yield Call(fn=lambda: 42)
            yield Put(Action("done", payload=result))

        gen = fetch_saga()
        effect = next(gen)
        assert isinstance(effect, Call)

        effect = gen.send(42)
        assert effect == Put(Action("done", payload=42))

    def test_select_state(self):
        """Step through a saga that reads state."""

        def read_saga():
            state = yield Select()
            yield Put(Action("got_state", payload=state))

        gen = read_saga()
        effect = next(gen)
        assert isinstance(effect, Select)
        assert effect.selector is None

        effect = gen.send({"count": 5})
        assert effect == Put(Action("got_state", payload={"count": 5}))

    def test_select_with_selector(self):
        """Step through a saga with a selector function."""

        def read_count_saga():
            count = yield Select(selector=lambda s: s["count"])
            yield Put(Action("got_count", payload=count))

        gen = read_count_saga()
        effect = next(gen)
        assert isinstance(effect, Select)

        # Simulate: selector applied to state
        state = {"count": 10, "name": "test"}
        value = effect.selector(state)
        effect = gen.send(value)
        assert effect == Put(Action("got_count", payload=10))

    def test_multi_step_saga(self):
        """Step through a complex multi-step saga."""

        def deploy_saga(env: str):
            yield Put(Action("deploy_started"))
            status = yield Call(fn=lambda: "ok")
            if status == "ok":
                yield Put(Action("deploy_succeeded", payload=env))
            else:
                yield Put(Action("deploy_failed"))

        gen = deploy_saga("prod")

        e1 = next(gen)
        assert e1 == Put(Action("deploy_started"))

        e2 = next(gen)
        assert isinstance(e2, Call)

        e3 = gen.send("ok")
        assert e3 == Put(Action("deploy_succeeded", payload="prod"))

    def test_fork_effect(self):
        """Verify fork yields correctly."""

        def child():
            yield Put(Action("child_done"))

        def parent():
            yield Fork(saga=child())
            yield Put(Action("parent_continues"))

        gen = parent()
        e1 = next(gen)
        assert isinstance(e1, Fork)

        e2 = next(gen)
        assert e2 == Put(Action("parent_continues"))

    def test_delay_effect(self):
        """Verify delay effect is yielded correctly."""

        def delayed_saga():
            yield Delay(seconds=1.0)
            yield Put(Action("after_delay"))

        gen = delayed_saga()
        e1 = next(gen)
        assert e1 == Delay(seconds=1.0)

        e2 = next(gen)
        assert e2 == Put(Action("after_delay"))


class TestRetryEffect:
    def test_retry_dataclass(self):
        from milo._types import Retry

        r = Retry(fn=lambda: 1, max_attempts=5, backoff="linear")
        assert r.max_attempts == 5
        assert r.backoff == "linear"
        assert r.base_delay == 1.0

    def test_retry_in_saga(self):
        from milo._types import Retry
        from milo.state import Store

        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "success"

        results = []

        def saga():
            result = yield Retry(flaky, max_attempts=5, base_delay=0.01)
            results.append(result)

        def reducer(state, action):
            return state

        store = Store(reducer, {})
        store.run_saga(saga())
        store._executor.shutdown(wait=True)

        assert results == ["success"]
        assert call_count == 3

    def test_retry_exhausted(self):
        from milo.state import _execute_retry

        call_count = 0

        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError, match="fail"):
            _execute_retry(always_fails, (), {}, 3, "fixed", 0.01, 1.0)
        assert call_count == 3

    def test_retry_exponential_backoff(self):
        from milo.state import _execute_retry

        attempts = []

        def fail_twice():
            attempts.append(1)
            if len(attempts) < 3:
                raise ValueError("not yet")
            return "ok"

        result = _execute_retry(fail_twice, (), {}, 5, "exponential", 0.01, 1.0)
        assert result == "ok"
        assert len(attempts) == 3


class TestTimeoutEffect:
    def test_timeout_dataclass(self):
        t = Timeout(effect=Call(fn=lambda: 1), seconds=5.0)
        assert t.seconds == 5.0
        assert isinstance(t.effect, Call)

    def test_timeout_completes_in_time(self):
        from milo.state import Store

        results = []

        def saga():
            result = yield Timeout(Call(fn=lambda: 42), seconds=5.0)
            results.append(result)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        store._executor.shutdown(wait=True)

        assert results == [42]

    def test_timeout_fires(self):
        from milo.state import Store

        errors = []

        def saga():
            result = yield Timeout(Call(fn=lambda: time.sleep(10)), seconds=0.1)
            errors.append(("unexpected", result))

        def reducer(state, action):
            if action.type == "@@SAGA_ERROR":
                errors.append(action.payload)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        store._executor.shutdown(wait=True)

        assert len(errors) == 1
        assert errors[0]["type"] == "TimeoutError"

    def test_timeout_caught_by_saga(self):
        from milo.state import Store

        results = []

        def saga():
            try:
                yield Timeout(Call(fn=lambda: time.sleep(10)), seconds=0.1)
            except TimeoutError:
                results.append("caught")
            results.append("continued")

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        store._executor.shutdown(wait=True)

        assert results == ["caught", "continued"]

    def test_timeout_with_retry(self):
        from milo.state import Store

        errors = []

        def slow_fn():
            time.sleep(10)
            return "never"

        def saga():
            yield Timeout(
                Retry(fn=slow_fn, max_attempts=3, base_delay=0.01),
                seconds=0.2,
            )

        def reducer(state, action):
            if action.type == "@@SAGA_ERROR":
                errors.append(action.payload)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        store._executor.shutdown(wait=True)

        assert len(errors) == 1
        assert errors[0]["type"] == "TimeoutError"

    def test_timeout_stepping(self):
        """Step through a saga that yields Timeout — verify the type."""

        def saga():
            result = yield Timeout(Call(fn=lambda: 1), seconds=3.0)
            yield Put(Action("done", payload=result))

        gen = saga()
        effect = next(gen)
        assert isinstance(effect, Timeout)
        assert isinstance(effect.effect, Call)
        assert effect.seconds == 3.0


class TestTryCallEffect:
    def test_trycall_dataclass(self):
        tc = TryCall(fn=lambda: 1)
        assert tc.args == ()
        assert tc.kwargs == {}

    def test_trycall_success(self):
        from milo.state import Store

        results = []

        def saga():
            result, error = yield TryCall(fn=lambda: 42)
            results.append((result, error))

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        store._executor.shutdown(wait=True)

        assert results == [(42, None)]

    def test_trycall_failure(self):
        from milo.state import Store

        results = []

        def failing():
            raise ValueError("boom")

        def saga():
            result, error = yield TryCall(fn=failing)
            results.append((result, type(error).__name__, str(error)))

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        store._executor.shutdown(wait=True)

        assert len(results) == 1
        assert results[0] == (None, "ValueError", "boom")

    def test_trycall_does_not_dispatch_saga_error(self):
        """TryCall errors should NOT dispatch @@SAGA_ERROR."""
        from milo.state import Store

        errors = []

        def failing():
            raise RuntimeError("handled")

        def saga():
            _result, error = yield TryCall(fn=failing)
            yield Put(Action("handled", payload=str(error)))

        def reducer(state, action):
            if action.type == "@@SAGA_ERROR":
                errors.append(action.payload)
            if action.type == "handled":
                return {"handled": action.payload}
            return state or {}

        store = Store(reducer, None)
        store.run_saga(saga())
        store._executor.shutdown(wait=True)

        assert errors == []
        assert store.state == {"handled": "handled"}

    def test_trycall_with_args(self):
        from milo.state import Store

        results = []

        def add(a, b):
            return a + b

        def saga():
            result, _error = yield TryCall(fn=add, args=(3, 4))
            results.append(result)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        store._executor.shutdown(wait=True)

        assert results == [7]

    def test_trycall_stepping(self):
        """Step through manually to verify effect type."""

        def saga():
            result, _error = yield TryCall(fn=lambda: 99)
            yield Put(Action("done", payload=result))

        gen = saga()
        effect = next(gen)
        assert isinstance(effect, TryCall)

        # Simulate store sending (result, None) back
        effect = gen.send((99, None))
        assert effect == Put(Action("done", payload=99))


class TestSagaCancellation:
    def test_cancel_stops_saga(self):
        from milo.state import Store

        results = []
        cancel = threading.Event()

        def saga():
            results.append("started")
            yield Delay(seconds=0.05)
            results.append("after_delay_1")
            yield Delay(seconds=10)  # Should never reach here
            results.append("after_delay_2")

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga(), cancel=cancel)
        time.sleep(0.1)
        cancel.set()
        store._executor.shutdown(wait=True)

        assert "started" in results
        assert "after_delay_2" not in results

    def test_cancel_dispatches_saga_cancelled(self):
        from milo.state import Store

        actions = []
        cancel = threading.Event()

        def saga():
            yield Delay(seconds=0.05)
            yield Delay(seconds=10)

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga(), cancel=cancel)
        time.sleep(0.1)
        cancel.set()
        store._executor.shutdown(wait=True)

        assert "@@SAGA_CANCELLED" in actions

    def test_fork_returns_cancel_handle(self):
        """Fork should send a cancel Event back to the parent saga."""

        results = []

        def child():
            yield Put(Action("child_running"))
            yield Delay(seconds=10)

        def parent():
            cancel_handle = yield Fork(saga=child())
            results.append(cancel_handle)

        gen = parent()
        effect = next(gen)
        assert isinstance(effect, Fork)

        # Simulate store sending cancel event back
        import contextlib

        cancel = threading.Event()
        with contextlib.suppress(StopIteration):
            gen.send(cancel)

        assert len(results) == 1
        assert isinstance(results[0], threading.Event)

    def test_cancel_forked_saga(self):
        from milo.state import Store

        actions = []
        done = threading.Event()

        def child():
            yield Delay(seconds=0.05)
            yield Delay(seconds=10)
            # Should not reach here
            done.set()

        def parent():
            child_cancel = yield Fork(saga=child())
            yield Delay(seconds=0.15)
            child_cancel.set()
            yield Delay(seconds=0.15)  # Give child time to process cancel

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert "@@SAGA_CANCELLED" in actions
        assert not done.is_set()


class TestRaceEffect:
    def test_race_dataclass(self):
        r = Race(sagas=(lambda: None, lambda: None))
        assert len(r.sagas) == 2

    def test_race_dataclass_frozen(self):
        r = Race(sagas=())
        with pytest.raises(AttributeError):
            r.sagas = ()  # type: ignore[misc]

    def test_race_basic(self):
        """First saga to complete wins."""
        from milo.state import Store

        results = []

        def fast():
            yield Delay(seconds=0.05)
            return "fast"

        def slow():
            yield Delay(seconds=5.0)
            return "slow"

        def parent():
            winner = yield Race(sagas=(fast(), slow()))
            results.append(winner)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert results == ["fast"]

    def test_race_loser_cancelled(self):
        """Losing sagas should be cancelled."""
        from milo.state import Store

        actions = []

        def fast():
            yield Delay(seconds=0.05)
            return "fast"

        def slow():
            yield Delay(seconds=0.05)
            yield Delay(seconds=10.0)  # Should be cancelled before this completes
            return "slow"

        def parent():
            yield Race(sagas=(fast(), slow()))

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert "@@SAGA_CANCELLED" in actions

    def test_race_with_failing_saga(self):
        """If the first to finish raises, that error propagates."""
        from milo.state import Store

        errors = []

        def fail_fast():
            yield Delay(seconds=0.05)
            raise ValueError("boom")

        def slow():
            yield Delay(seconds=5.0)
            return "slow"

        def parent():
            try:
                yield Race(sagas=(fail_fast(), slow()))
            except ValueError as e:
                errors.append(str(e))

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        # The error from fail_fast propagates as @@SAGA_ERROR since
        # it's thrown into the parent which catches it
        # But the capturing wrapper catches and stores the error
        # The parent saga gets the error thrown into it
        assert errors == ["boom"]

    def test_race_single_saga(self):
        """Race with one saga just returns its result."""
        from milo.state import Store

        results = []

        def only():
            yield Delay(seconds=0.05)
            return "only"

        def parent():
            winner = yield Race(sagas=(only(),))
            results.append(winner)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.3)
        store._executor.shutdown(wait=True)

        assert results == ["only"]

    def test_race_empty_raises(self):
        """Race with no sagas raises StateError."""
        from milo.state import Store

        errors = []

        def parent():
            yield Race(sagas=())

        def reducer(state, action):
            if action.type == "@@SAGA_ERROR":
                errors.append(action.payload)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        store._executor.shutdown(wait=True)

        assert len(errors) == 1
        assert "at least one saga" in errors[0]["error"]


class TestAllEffect:
    def test_all_dataclass(self):
        a = All(sagas=(lambda: None, lambda: None))
        assert len(a.sagas) == 2

    def test_all_dataclass_frozen(self):
        a = All(sagas=())
        with pytest.raises(AttributeError):
            a.sagas = ()  # type: ignore[misc]

    def test_all_effect_basic(self):
        """All waits for all sagas and returns results in order."""
        from milo.state import Store

        results = []

        def saga_a():
            yield Delay(seconds=0.05)
            return "a"

        def saga_b():
            yield Delay(seconds=0.1)
            return "b"

        def parent():
            result = yield All(sagas=(saga_a(), saga_b()))
            results.append(result)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert results == [("a", "b")]

    def test_all_effect_one_failure_cancels_rest(self):
        """If one saga fails, the rest are cancelled and error propagates."""
        from milo.state import Store

        errors = []
        actions = []

        def good():
            yield Delay(seconds=5.0)
            return "good"

        def bad():
            yield Delay(seconds=0.05)
            raise ValueError("bad")

        def parent():
            try:
                yield All(sagas=(good(), bad()))
            except ValueError as e:
                errors.append(str(e))

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert errors == ["bad"]
        assert "@@SAGA_CANCELLED" in actions

    def test_all_effect_empty(self):
        """All with empty tuple returns empty tuple immediately."""
        from milo.state import Store

        results = []

        def parent():
            result = yield All(sagas=())
            results.append(result)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        store._executor.shutdown(wait=True)

        assert results == [()]

    def test_all_effect_single_saga(self):
        """All with one saga wraps result in 1-tuple."""
        from milo.state import Store

        results = []

        def only():
            yield Delay(seconds=0.05)
            return "only"

        def parent():
            result = yield All(sagas=(only(),))
            results.append(result)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.3)
        store._executor.shutdown(wait=True)

        assert results == [("only",)]

    def test_all_effect_preserves_order(self):
        """Results are ordered by input position, not completion time."""
        from milo.state import Store

        results = []

        def slow():
            yield Delay(seconds=0.15)
            return "slow"

        def fast():
            yield Delay(seconds=0.05)
            return "fast"

        def parent():
            result = yield All(sagas=(slow(), fast()))
            results.append(result)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert results == [("slow", "fast")]


class TestTakeEffect:
    def test_take_dataclass(self):
        t = Take(action_type="@@KEY")
        assert t.action_type == "@@KEY"
        assert t.timeout is None

    def test_take_dataclass_with_timeout(self):
        t = Take(action_type="@@KEY", timeout=5.0)
        assert t.timeout == 5.0

    def test_take_dataclass_frozen(self):
        t = Take(action_type="@@KEY")
        with pytest.raises(AttributeError):
            t.action_type = "other"  # type: ignore[misc]

    def test_take_basic(self):
        """Take pauses saga until matching action is dispatched."""
        from milo.state import Store

        results = []

        def saga():
            action = yield Take("USER_CONFIRMED")
            results.append(action.payload)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        time.sleep(0.1)
        # Saga should be blocked
        assert results == []

        store.dispatch(Action("USER_CONFIRMED", payload="yes"))
        time.sleep(0.1)
        store._executor.shutdown(wait=True)

        assert results == ["yes"]

    def test_take_with_timeout(self):
        """Take with timeout returns action if dispatched in time."""
        from milo.state import Store

        results = []

        def saga():
            action = yield Take("FAST_ACTION", timeout=2.0)
            results.append(action.payload)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        time.sleep(0.05)
        store.dispatch(Action("FAST_ACTION", payload="got it"))
        time.sleep(0.1)
        store._executor.shutdown(wait=True)

        assert results == ["got it"]

    def test_take_timeout_fires(self):
        """Take raises TimeoutError when action isn't dispatched in time."""
        from milo.state import Store

        errors = []

        def saga():
            try:
                yield Take("NEVER_COMES", timeout=0.1)
            except TimeoutError as e:
                errors.append(str(e))

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert len(errors) == 1
        assert "NEVER_COMES" in errors[0]
        assert "timed out" in errors[0]

    def test_take_ignores_past_actions(self):
        """Take waits for future actions only, not already-dispatched ones."""
        from milo.state import Store

        results = []

        def saga():
            # Dispatch happens before Take
            yield Put(Action("EARLY_ACTION", payload="early"))
            yield Delay(seconds=0.05)
            # Now take — should NOT match the already-dispatched action
            try:
                yield Take("EARLY_ACTION", timeout=0.15)
                results.append("matched")
            except TimeoutError:
                results.append("timed_out")

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(saga())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert results == ["timed_out"]

    def test_take_multiple_waiters(self):
        """Multiple sagas can Take the same action type."""
        from milo.state import Store

        results = []

        def waiter(name):
            action = yield Take("SHARED_EVENT")
            results.append((name, action.payload))

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(waiter("a"))
        store.run_saga(waiter("b"))
        time.sleep(0.1)
        store.dispatch(Action("SHARED_EVENT", payload="hello"))
        time.sleep(0.2)
        store._executor.shutdown(wait=True)

        assert len(results) == 2
        assert ("a", "hello") in results
        assert ("b", "hello") in results


class TestDebounceEffect:
    def test_debounce_dataclass(self):
        d = Debounce(seconds=0.3, saga=lambda: None)
        assert d.seconds == 0.3

    def test_debounce_dataclass_frozen(self):
        d = Debounce(seconds=0.3, saga=lambda: None)
        with pytest.raises(AttributeError):
            d.seconds = 1.0  # type: ignore[misc]

    def test_debounce_basic(self):
        """Debounce fires the inner saga after the delay."""
        from milo.state import Store

        actions = []

        def inner_saga():
            yield Put(Action("DEBOUNCED_FIRE"))

        def parent():
            yield Debounce(seconds=0.1, saga=inner_saga)
            yield Delay(seconds=0.3)  # Wait for debounce to fire

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert "DEBOUNCED_FIRE" in actions

    def test_debounce_retrigger_resets_timer(self):
        """Re-yielding Debounce cancels previous timer and starts new one."""
        from milo.state import Store

        actions = []

        def inner_saga():
            yield Put(Action("DEBOUNCED_FIRE"))

        def parent():
            # First debounce — 0.2s
            yield Debounce(seconds=0.2, saga=inner_saga)
            # Wait a bit, then retrigger before first fires
            yield Delay(seconds=0.05)
            # Second debounce — resets the timer
            yield Debounce(seconds=0.2, saga=inner_saga)
            # Wait long enough for second to fire
            yield Delay(seconds=0.5)

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(1.0)
        store._executor.shutdown(wait=True)

        # Should fire exactly once (first timer cancelled, second fires)
        fire_count = actions.count("DEBOUNCED_FIRE")
        assert fire_count == 1

    def test_debounce_cancelled_on_saga_exit(self):
        """Pending debounce is cancelled when parent saga ends."""
        from milo.state import Store

        actions = []

        def inner_saga():
            yield Put(Action("SHOULD_NOT_FIRE"))

        def parent():
            yield Debounce(seconds=0.3, saga=inner_saga)
            # Parent exits immediately — debounce should be cancelled

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        assert "SHOULD_NOT_FIRE" not in actions


class TestSagaContext:
    def test_basic_creation(self):
        ctx = SagaContext()
        assert len(ctx.saga_id) == 12
        assert not ctx.is_cancelled
        assert ctx.parent is None
        assert ctx.children == []

    def test_child_inherits_cancel(self):
        parent = SagaContext()
        child = parent.child()
        assert child.parent is parent
        assert child in parent.children
        assert not child.is_cancelled

    def test_cancel_tree_propagates(self):
        root = SagaContext()
        child1 = root.child()
        child2 = root.child()
        grandchild = child1.child()

        root.cancel_tree()

        assert root.is_cancelled
        assert child1.is_cancelled
        assert child2.is_cancelled
        assert grandchild.is_cancelled

    def test_detached_child_independent(self):
        parent = SagaContext()
        detached = parent.detached_child()

        parent.cancel_tree()

        assert parent.is_cancelled
        assert not detached.is_cancelled

    def test_custom_saga_id(self):
        ctx = SagaContext(saga_id="my-saga")
        assert ctx.saga_id == "my-saga"

    def test_cancel_child_does_not_cancel_parent(self):
        parent = SagaContext()
        child = parent.child()

        child.cancel_tree()

        assert child.is_cancelled
        assert not parent.is_cancelled

    def test_run_saga_returns_context(self):
        from milo.state import Store

        def saga():
            yield Put(Action("done"))

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(saga())
        assert isinstance(ctx, SagaContext)
        store._executor.shutdown(wait=True)

    def test_saga_error_includes_saga_id(self):
        from milo.state import Store

        errors = []

        def bad_saga():
            raise ValueError("boom")
            yield  # makes it a generator

        def reducer(state, action):
            if action.type == "@@SAGA_ERROR":
                errors.append(action.payload)
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(bad_saga())
        store._executor.shutdown(wait=True)

        assert len(errors) == 1
        assert errors[0]["saga_id"] == ctx.saga_id
        assert errors[0]["type"] == "ValueError"

    def test_saga_cancelled_includes_saga_id(self):
        from milo.state import Store

        payloads = []

        def long_saga():
            yield Delay(seconds=10)

        def reducer(state, action):
            if action.type == "@@SAGA_CANCELLED":
                payloads.append(action.payload)
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(long_saga())
        time.sleep(0.1)
        ctx.cancel.set()
        store._executor.shutdown(wait=True)

        assert len(payloads) == 1
        assert payloads[0]["saga_id"] == ctx.saga_id


class TestForkAttached:
    def test_detached_fork_not_cancelled_by_parent(self):
        """Default (detached) fork is NOT cancelled when parent is cancelled."""
        from milo.state import Store

        results = []
        cancel = threading.Event()

        def child():
            yield Delay(seconds=0.15)
            results.append("child_completed")
            yield Put(Action("child_done"))

        def parent():
            yield Fork(saga=child())  # detached by default
            yield Delay(seconds=10)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent(), cancel=cancel)
        time.sleep(0.05)
        cancel.set()  # Cancel parent
        time.sleep(0.3)
        store._executor.shutdown(wait=True)

        # Child should still complete because it's detached
        assert "child_completed" in results

    def test_attached_fork_cancelled_by_parent(self):
        """Attached fork IS cancelled when parent is cancelled."""
        from milo.state import Store

        results = []
        actions = []

        def child():
            yield Delay(seconds=0.05)
            yield Delay(seconds=10)  # Should be cancelled before this completes
            results.append("child_completed")

        def parent():
            yield Fork(saga=child(), attached=True)
            yield Delay(seconds=10)

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(parent())
        time.sleep(0.15)
        ctx.cancel_tree()  # Cancel parent AND attached children
        time.sleep(0.3)
        store._executor.shutdown(wait=True)

        assert "child_completed" not in results
        assert "@@SAGA_CANCELLED" in actions


class TestRaceCancellationPropagation:
    def test_race_parent_cancel_propagates_to_children(self):
        """Cancelling parent while Race is running cancels all Race children."""
        from milo.state import Store

        actions = []

        def slow_a():
            yield Delay(seconds=10)
            return "a"

        def slow_b():
            yield Delay(seconds=10)
            return "b"

        def parent():
            try:  # noqa: SIM105
                yield Race(sagas=(slow_a(), slow_b()))
            except Exception:
                pass

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(parent())
        time.sleep(0.15)
        ctx.cancel_tree()
        time.sleep(0.3)
        store._executor.shutdown(wait=True)

        # Parent + at least one child should have been cancelled
        cancel_count = actions.count("@@SAGA_CANCELLED")
        assert cancel_count >= 1


class TestAllCancellationPropagation:
    def test_all_parent_cancel_propagates_to_children(self):
        """Cancelling parent while All is running cancels all children."""
        from milo.state import Store

        actions = []

        def slow_a():
            yield Delay(seconds=10)
            return "a"

        def slow_b():
            yield Delay(seconds=10)
            return "b"

        def parent():
            try:  # noqa: SIM105
                yield All(sagas=(slow_a(), slow_b()))
            except Exception:
                pass

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(parent())
        time.sleep(0.15)
        ctx.cancel_tree()
        time.sleep(0.3)
        store._executor.shutdown(wait=True)

        cancel_count = actions.count("@@SAGA_CANCELLED")
        assert cancel_count >= 1


# ---------------------------------------------------------------------------
# Composition tests — nested effect patterns
# ---------------------------------------------------------------------------


class TestEffectComposition:
    def test_race_inside_all(self):
        """All containing two Race effects — both races resolve, All collects results."""
        from milo.state import Store

        results = []

        def race_ab():
            def fast():
                yield Delay(seconds=0.05)
                return "fast_a"

            def slow():
                yield Delay(seconds=5.0)
                return "slow_a"

            winner = yield Race(sagas=(fast(), slow()))
            return winner

        def race_cd():
            def fast():
                yield Delay(seconds=0.05)
                return "fast_b"

            def slow():
                yield Delay(seconds=5.0)
                return "slow_b"

            winner = yield Race(sagas=(fast(), slow()))
            return winner

        def parent():
            a, b = yield All(sagas=(race_ab(), race_cd()))
            results.append((a, b))

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(1.0)
        store._executor.shutdown(wait=True)

        assert results == [("fast_a", "fast_b")]

    def test_all_inside_race(self):
        """Race between two All effects — first All to complete wins."""
        from milo.state import Store

        results = []

        def fast_pair():
            def a():
                yield Delay(seconds=0.05)
                return "a"

            def b():
                yield Delay(seconds=0.05)
                return "b"

            pair = yield All(sagas=(a(), b()))
            return pair

        def slow_pair():
            def c():
                yield Delay(seconds=5.0)
                return "c"

            def d():
                yield Delay(seconds=5.0)
                return "d"

            pair = yield All(sagas=(c(), d()))
            return pair

        def parent():
            winner = yield Race(sagas=(fast_pair(), slow_pair()))
            results.append(winner)

        def reducer(state, action):
            return state or 0

        # Use extra workers to prevent pool starvation when Race+All nest
        store = Store(reducer, None, max_workers=8)
        store.run_saga(parent())
        time.sleep(1.0)
        store._executor.shutdown(wait=True)

        assert results == [("a", "b")]

    def test_fork_inside_race(self):
        """Race where one racer forks a child — fork should be cancelled when race completes."""
        from milo.state import Store

        actions = []

        def forker():
            def child():
                yield Delay(seconds=0.05)
                yield Delay(seconds=10.0)  # Should be cancelled
                yield Put(Action("CHILD_SURVIVED"))

            yield Fork(saga=child(), attached=True)
            yield Delay(seconds=5.0)
            return "forker"

        def fast():
            yield Delay(seconds=0.1)
            return "fast"

        def parent():
            winner = yield Race(sagas=(forker(), fast()))
            yield Put(Action("WINNER", payload=winner))

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(1.0)
        store._executor.shutdown(wait=True)

        assert "WINNER" in actions
        assert "CHILD_SURVIVED" not in actions

    def test_take_inside_all(self):
        """All with multiple sagas waiting for different actions via Take."""
        from milo.state import Store

        results = []

        def waiter_a():
            action = yield Take("EVENT_A", timeout=2.0)
            return action.payload

        def waiter_b():
            action = yield Take("EVENT_B", timeout=2.0)
            return action.payload

        def parent():
            # Fork a saga that dispatches the events after a short delay
            def dispatcher():
                yield Delay(seconds=0.1)
                yield Put(Action("EVENT_A", payload="hello"))
                yield Put(Action("EVENT_B", payload="world"))

            yield Fork(saga=dispatcher())
            a, b = yield All(sagas=(waiter_a(), waiter_b()))
            results.append((a, b))

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        time.sleep(1.0)
        store._executor.shutdown(wait=True)

        assert results == [("hello", "world")]

    def test_debounce_with_take_pattern(self):
        """Keystroke search pattern: Take + Debounce in a loop."""
        from milo.state import Store

        actions = []

        def search_saga():
            yield Put(Action("SEARCH_EXECUTED"))

        def parent():
            # Simulate: receive 3 rapid keys, debounce should fire once
            for _ in range(3):
                yield Take("@@KEY", timeout=2.0)
                yield Debounce(seconds=0.5, saga=search_saga)
            # Wait for debounce to fire
            yield Delay(seconds=1.0)

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        store.run_saga(parent())
        # Dispatch 3 rapid key events
        time.sleep(0.05)
        store.dispatch(Action("@@KEY", payload="a"))
        time.sleep(0.02)
        store.dispatch(Action("@@KEY", payload="b"))
        time.sleep(0.02)
        store.dispatch(Action("@@KEY", payload="c"))
        time.sleep(1.5)
        store._executor.shutdown(wait=True)

        # Debounce should have fired exactly once (last one)
        search_count = actions.count("SEARCH_EXECUTED")
        assert search_count == 1


class TestTakeEveryEffect:
    def test_take_every_forks_for_each_action(self):
        """TakeEvery('CLICK', handler) forks 3 handlers when 3 CLICK actions dispatched."""
        from milo.state import Store

        results = []

        def handle_click(action):
            results.append(action.payload)
            yield Put(Action("CLICK_HANDLED", payload=action.payload))

        def watcher():
            yield TakeEvery("CLICK", handle_click)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(watcher())
        time.sleep(0.1)

        store.dispatch(Action("CLICK", payload="btn1"))
        time.sleep(0.05)
        store.dispatch(Action("CLICK", payload="btn2"))
        time.sleep(0.05)
        store.dispatch(Action("CLICK", payload="btn3"))
        time.sleep(0.3)

        ctx.cancel_tree()
        time.sleep(0.2)
        store._executor.shutdown(wait=True)

        assert sorted(results) == ["btn1", "btn2", "btn3"]

    def test_take_every_cancel_stops_watching(self):
        """Cancelling the parent stops the TakeEvery watcher loop."""
        from milo.state import Store

        actions = []

        def handler(action):
            yield Put(Action("HANDLED"))

        def watcher():
            yield TakeEvery("EVT", handler)

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(watcher())
        time.sleep(0.1)

        store.dispatch(Action("EVT", payload=1))
        time.sleep(0.15)

        # Cancel the watcher — give extra time for free-threaded builds (3.14t)
        # where the watcher poll loop (0.1s intervals) needs to observe cancellation
        ctx.cancel_tree()
        time.sleep(0.5)

        # Dispatch after cancel — should NOT be handled
        handled_before = actions.count("HANDLED")
        store.dispatch(Action("EVT", payload=2))
        time.sleep(0.5)
        store._executor.shutdown(wait=True)

        handled_after = actions.count("HANDLED")
        assert handled_before == 1
        assert handled_after == handled_before  # No new handlers after cancel

    def test_take_every_ignores_unrelated_actions(self):
        """TakeEvery only forks for matching action types."""
        from milo.state import Store

        results = []

        def handler(action):
            results.append(action.type)
            yield Put(Action("HANDLED"))

        def watcher():
            yield TakeEvery("TARGET", handler)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(watcher())
        time.sleep(0.1)

        store.dispatch(Action("OTHER", payload="x"))
        store.dispatch(Action("TARGET", payload="y"))
        store.dispatch(Action("OTHER", payload="z"))
        time.sleep(0.3)

        ctx.cancel_tree()
        time.sleep(0.2)
        store._executor.shutdown(wait=True)

        assert results == ["TARGET"]


class TestTakeLatestEffect:
    def test_take_latest_cancels_previous(self):
        """TakeLatest cancels previous handler when new action arrives, only last completes."""
        from milo.state import Store

        completed = []

        def handler(action):
            yield Delay(seconds=0.5)
            completed.append(action.payload)

        def watcher():
            yield TakeLatest("SEARCH", handler)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None, max_workers=8)
        ctx = store.run_saga(watcher())
        time.sleep(0.15)

        # Dispatch with enough gap for TakeLatest to re-register its waiter
        store.dispatch(Action("SEARCH", payload="first"))
        time.sleep(0.15)
        store.dispatch(Action("SEARCH", payload="second"))
        time.sleep(0.15)
        store.dispatch(Action("SEARCH", payload="third"))
        # Wait for the last handler to complete
        time.sleep(0.8)

        ctx.cancel_tree()
        time.sleep(0.2)
        store._executor.shutdown(wait=True)

        # Only the last one should have completed
        assert completed == ["third"]

    def test_take_latest_cancel_stops_watching(self):
        """Cancelling the parent stops TakeLatest and cancels the active fork."""
        from milo.state import Store

        actions = []

        def handler(action):
            yield Delay(seconds=0.5)
            yield Put(Action("COMPLETED"))

        def watcher():
            yield TakeLatest("EVT", handler)

        def reducer(state, action):
            actions.append(action.type)
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(watcher())
        time.sleep(0.1)

        store.dispatch(Action("EVT", payload=1))
        time.sleep(0.1)

        # Cancel before handler completes
        ctx.cancel_tree()
        time.sleep(0.7)
        store._executor.shutdown(wait=True)

        assert "COMPLETED" not in actions

    def test_take_latest_single_action_completes(self):
        """With only one action, TakeLatest lets it complete normally."""
        from milo.state import Store

        results = []

        def handler(action):
            yield Delay(seconds=0.05)
            results.append(action.payload)

        def watcher():
            yield TakeLatest("DO", handler)

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None)
        ctx = store.run_saga(watcher())
        time.sleep(0.1)

        store.dispatch(Action("DO", payload="only"))
        time.sleep(0.3)

        ctx.cancel_tree()
        time.sleep(0.2)
        store._executor.shutdown(wait=True)

        assert results == ["only"]


class TestConfigurablePool:
    def test_custom_max_workers(self):
        """Store accepts max_workers parameter."""
        from milo.state import Store

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None, max_workers=8)
        assert store._max_workers == 8
        assert store._executor._max_workers == 8
        store._executor.shutdown(wait=True)

    def test_default_max_workers(self):
        """Default max_workers is auto-sized by kida's RENDER profile."""
        import os

        from kida import WorkloadType, get_optimal_workers

        from milo.state import Store

        def reducer(state, action):
            return state or 0

        expected = get_optimal_workers(os.cpu_count() or 4, workload_type=WorkloadType.RENDER)
        store = Store(reducer, None)
        assert store._max_workers == expected
        assert store._executor._max_workers == expected
        store._executor.shutdown(wait=True)

    def test_pool_pressure_callback_fires(self):
        """on_pool_pressure fires when active tasks exceed threshold."""
        from milo.state import Store

        pressure_calls = []

        def on_pressure(active, max_w):
            pressure_calls.append((active, max_w))

        def reducer(state, action):
            return state or 0

        # max_workers=2, threshold=0.5 → fires when active >= 1
        store = Store(
            reducer,
            None,
            max_workers=2,
            on_pool_pressure=on_pressure,
            pool_pressure_threshold=0.5,
        )

        barrier = threading.Event()

        def blocking_saga():
            yield Call(fn=lambda: barrier.wait(timeout=5))

        # Launch 2 sagas that block
        store.run_saga(blocking_saga())
        store.run_saga(blocking_saga())
        time.sleep(0.2)

        barrier.set()
        time.sleep(0.2)
        store._executor.shutdown(wait=True)

        # Should have fired at least once (when active >= 1)
        assert len(pressure_calls) >= 1
        # Each call should have (active_count, max_workers=2)
        for active, max_w in pressure_calls:
            assert max_w == 2
            assert active >= 1

    def test_pool_active_property(self):
        """pool_active reports currently running tasks."""
        from milo.state import Store

        def reducer(state, action):
            return state or 0

        store = Store(reducer, None, max_workers=4)

        barrier = threading.Event()

        def blocking_saga():
            def block():
                barrier.wait(timeout=5)

            yield Call(fn=block)

        # Launch 3 blocking sagas
        store.run_saga(blocking_saga())
        store.run_saga(blocking_saga())
        store.run_saga(blocking_saga())
        time.sleep(0.2)

        snapshot = store.pool_active

        barrier.set()
        time.sleep(0.3)
        store._executor.shutdown(wait=True)

        # While blocked, should have had 3 active tasks
        assert snapshot >= 3
        # After completion, should be 0
        assert store.pool_active == 0

    def test_pool_pressure_callback_error_swallowed(self):
        """Errors in on_pool_pressure callback are swallowed, not propagated."""
        from milo.state import Store

        def bad_callback(active, max_w):
            raise RuntimeError("callback boom")

        def reducer(state, action):
            return state or 0

        store = Store(
            reducer,
            None,
            max_workers=2,
            on_pool_pressure=bad_callback,
            pool_pressure_threshold=0.0,  # Always fires
        )

        results = []

        def simple_saga():
            result = yield Call(fn=lambda: 42)
            results.append(result)

        store.run_saga(simple_saga())
        time.sleep(0.3)
        store._executor.shutdown(wait=True)

        # Saga should still complete despite callback error
        assert results == [42]
