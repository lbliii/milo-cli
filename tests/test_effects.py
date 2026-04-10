"""Tests for saga effects — stepping through generators manually."""

from __future__ import annotations

import threading
import time

import pytest

from milo._types import Action, Call, Delay, Fork, Put, Retry, Select, Timeout, TryCall


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
