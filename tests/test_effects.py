"""Tests for saga effects — stepping through generators manually."""

from __future__ import annotations

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
