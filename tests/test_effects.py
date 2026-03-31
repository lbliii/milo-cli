"""Tests for saga effects — stepping through generators manually."""

from __future__ import annotations

import pytest

from milo._types import Action, Call, Delay, Fork, Put, Select


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
