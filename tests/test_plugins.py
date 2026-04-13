"""Tests for the plugin hook registry."""

from __future__ import annotations

import pytest

from milo._types import Action
from milo.plugins import HookRegistry

# ---------------------------------------------------------------------------
# Hook definition and registration
# ---------------------------------------------------------------------------


class TestHookDefinition:
    def test_define_hook(self):
        hooks = HookRegistry()
        hooks.define("before_build")
        assert "before_build" in hooks.hook_names()

    def test_define_duplicate_is_safe(self):
        hooks = HookRegistry()
        hooks.define("before_build")
        hooks.define("before_build")
        assert hooks.hook_names().count("before_build") == 1

    def test_define_with_action_type(self):
        hooks = HookRegistry()
        hooks.define("before_build", action_type="@@PIPELINE_START")
        assert "before_build" in hooks.hook_names()

    def test_register_listener(self):
        hooks = HookRegistry()
        hooks.define("before_build")

        def my_listener():
            pass

        hooks.register("before_build", my_listener)
        assert my_listener in hooks.listeners("before_build")

    def test_register_via_decorator(self):
        hooks = HookRegistry()
        hooks.define("before_build")

        @hooks.on("before_build")
        def my_listener():
            pass

        assert my_listener in hooks.listeners("before_build")

    def test_register_unknown_hook_raises(self):
        hooks = HookRegistry()
        with pytest.raises(Exception, match="Unknown hook"):
            hooks.register("nonexistent", lambda: None)

    def test_multiple_listeners(self):
        hooks = HookRegistry()
        hooks.define("before_build")
        hooks.register("before_build", lambda: "a")
        hooks.register("before_build", lambda: "b")
        assert len(hooks.listeners("before_build")) == 2


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------


class TestHookInvocation:
    def test_invoke_calls_listeners(self):
        hooks = HookRegistry()
        hooks.define("before_build")
        called = []

        @hooks.on("before_build")
        def listener(config=None):
            called.append(config)

        hooks.invoke("before_build", config="my_config")
        assert called == ["my_config"]

    def test_invoke_returns_results(self):
        hooks = HookRegistry()
        hooks.define("transform")
        hooks.register("transform", lambda value=0: value * 2)
        hooks.register("transform", lambda value=0: value + 1)
        results = hooks.invoke("transform", value=5)
        assert results == [10, 6]

    def test_invoke_preserves_order(self):
        hooks = HookRegistry()
        hooks.define("ordered")
        order = []
        hooks.register("ordered", lambda: order.append("first"))
        hooks.register("ordered", lambda: order.append("second"))
        hooks.register("ordered", lambda: order.append("third"))
        hooks.invoke("ordered")
        assert order == ["first", "second", "third"]

    def test_invoke_empty_hook(self):
        hooks = HookRegistry()
        hooks.define("empty")
        results = hooks.invoke("empty")
        assert results == []

    def test_invoke_undefined_hook(self):
        hooks = HookRegistry()
        results = hooks.invoke("nonexistent")
        assert results == []

    def test_invoke_listener_error_propagates(self):
        hooks = HookRegistry()
        hooks.define("broken")

        def bad_listener():
            raise ValueError("oops")

        hooks.register("broken", bad_listener)
        with pytest.raises(Exception, match="oops"):
            hooks.invoke("broken")

    def test_invoke_fail_fast_false_runs_all_listeners(self):
        hooks = HookRegistry()
        hooks.define("resilient")
        called = []

        def listener_a():
            called.append("a")
            raise ValueError("error a")

        def listener_b():
            called.append("b")
            raise ValueError("error b")

        hooks.register("resilient", listener_a)
        hooks.register("resilient", listener_b)
        with pytest.raises(Exception, match="2 listener error") as exc_info:
            hooks.invoke("resilient", fail_fast=False)
        assert called == ["a", "b"]
        # Aggregate error is chained from the first listener error
        assert exc_info.value.__cause__ is not None
        assert "error a" in str(exc_info.value.__cause__)

    def test_invoke_fail_fast_false_returns_results_on_success(self):
        hooks = HookRegistry()
        hooks.define("mixed")
        hooks.register("mixed", lambda: "ok")
        results = hooks.invoke("mixed", fail_fast=False)
        assert results == ["ok"]

    def test_invoke_fail_fast_true_stops_on_first_error(self):
        hooks = HookRegistry()
        hooks.define("strict")
        called = []

        def listener_a():
            called.append("a")
            raise ValueError("error a")

        def listener_b():
            called.append("b")

        hooks.register("strict", listener_a)
        hooks.register("strict", listener_b)
        with pytest.raises(Exception, match="error a"):
            hooks.invoke("strict", fail_fast=True)
        assert called == ["a"]


# ---------------------------------------------------------------------------
# Freeze
# ---------------------------------------------------------------------------


class TestFreeze:
    def test_freeze_prevents_define(self):
        hooks = HookRegistry()
        hooks.freeze()
        with pytest.raises(Exception, match="frozen"):
            hooks.define("new_hook")

    def test_freeze_prevents_register(self):
        hooks = HookRegistry()
        hooks.define("before_build")
        hooks.freeze()
        with pytest.raises(Exception, match="frozen"):
            hooks.register("before_build", lambda: None)

    def test_freeze_allows_invoke(self):
        hooks = HookRegistry()
        hooks.define("before_build")
        hooks.register("before_build", lambda: "ok")
        hooks.freeze()
        results = hooks.invoke("before_build")
        assert results == ["ok"]

    def test_frozen_property(self):
        hooks = HookRegistry()
        assert not hooks.frozen
        hooks.freeze()
        assert hooks.frozen


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class TestMiddleware:
    def test_middleware_fires_on_mapped_action(self):
        hooks = HookRegistry()
        hooks.define("on_start", action_type="@@PIPELINE_START")
        fired = []

        @hooks.on("on_start")
        def listener(action=None, get_state=None):
            fired.append(action.type)

        middleware = hooks.as_middleware()

        # Simulate Store middleware chain
        class FakeStore:
            def get_state(self):
                return {}

        dispatched = []

        def next_dispatch(action):
            dispatched.append(action)

        chain = middleware(FakeStore())(next_dispatch)
        action = Action("@@PIPELINE_START", "payload")
        chain(action)

        assert fired == ["@@PIPELINE_START"]
        assert len(dispatched) == 1
        assert dispatched[0] is action

    def test_middleware_passes_through_unmapped(self):
        hooks = HookRegistry()
        hooks.define("on_start", action_type="@@PIPELINE_START")
        fired = []

        @hooks.on("on_start")
        def listener(action=None, get_state=None):
            fired.append(action.type)

        middleware = hooks.as_middleware()

        dispatched = []

        def next_dispatch(action):
            dispatched.append(action)

        chain = middleware(object())(next_dispatch)
        action = Action("@@SOME_OTHER_ACTION")
        chain(action)

        assert fired == []
        assert len(dispatched) == 1
